import random
from dataclasses import dataclass
from scipy.spatial import Delaunay
import numpy as np
import math
from scipy.optimize import minimize
from itertools import product
try:
    import svgwrite
except ImportError:  # pragma: no cover - optional at runtime for mobile builds
    svgwrite = None

try:
    from cairosvg import svg2png
except ImportError:  # pragma: no cover - optional at runtime for mobile builds
    svg2png = None


STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_WARNING = "warning"
STATUS_UNKNOWN = "unknown"
STATUS_NOT_RUN = "not_run"


@dataclass(frozen=True)
class VertexLocalDiagnostic:
    vertex_index: int
    on_edge: bool
    degree: int
    even_degree_ok: bool
    kawasaki_ok: bool
    kawasaki_even_sum: float | None
    kawasaki_odd_sum: float | None
    kawasaki_error: float | None
    maekawa_ok: bool | None
    maekawa_mountains: int | None
    maekawa_valleys: int | None
    maekawa_balance: int | None
    message: str = ""


@dataclass(frozen=True)
class FoldAssignmentDiagnostic:
    assigned_fold_count: int
    unassigned_fold_count: int
    maekawa_failures: tuple[int, ...]
    underdetermined: bool


@dataclass(frozen=True)
class GlobalDiagnostic:
    status: str
    used_exact_faces: bool
    used_reference_pattern: bool
    uses_provisional_signs: bool
    uses_approximate_cycles: bool
    cycle_drift: float | None
    crossing_fold_pairs: tuple[tuple[int, int], ...] = ()
    face_count: int | None = None
    message: str = ""
    basis: str = "local_only"
    method: str = "local_only"
    heuristic_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatternDiagnosticReport:
    local_status: str
    global_status: str
    preview_status: str
    fold_assignment_status: str
    vertex_diagnostics: tuple[VertexLocalDiagnostic, ...]
    fold_assignment: FoldAssignmentDiagnostic
    global_diagnostic: GlobalDiagnostic
    summary: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssignmentSearchResult:
    success: bool
    message: str
    assigned_fold_count: int
    unassigned_fold_count: int
    group_count: int


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_on_segment(a, b, p, epsilon):
    return (
        min(a[0], b[0]) - epsilon <= p[0] <= max(a[0], b[0]) + epsilon
        and min(a[1], b[1]) - epsilon <= p[1] <= max(a[1], b[1]) + epsilon
    )


def _segments_intersect(a0, a1, b0, b1, epsilon):
    o1 = _orientation(a0, a1, b0)
    o2 = _orientation(a0, a1, b1)
    o3 = _orientation(b0, b1, a0)
    o4 = _orientation(b0, b1, a1)

    if abs(o1) <= epsilon and _point_on_segment(a0, a1, b0, epsilon):
        return True
    if abs(o2) <= epsilon and _point_on_segment(a0, a1, b1, epsilon):
        return True
    if abs(o3) <= epsilon and _point_on_segment(b0, b1, a0, epsilon):
        return True
    if abs(o4) <= epsilon and _point_on_segment(b0, b1, a1, epsilon):
        return True

    return (o1 > epsilon) != (o2 > epsilon) and (o3 > epsilon) != (o4 > epsilon)


class Vertex():
    """A vertex is a point in the crease pattern.
    """

    def __init__(self, x, y):
        self.d = 0 # degree zero by default
        self.adj = set() # adjacent folds
        self.adjv = set() # adjacent vertices
        self.x = x
        self.y = y

class Fold():
    """A fold is a line segment between two vertices.
       It is either a mountain or a valley (0 or 1)
       Or unknown (-1)
    """
    def __init__(self, v1, v2, type):
        self.v1 = v1
        self.v2 = v2
        self.type = type

class CreasePattern():
    """A crease pattern is a graph with vertices and folds between them
    """

    def __init__(self):
        self.side = 1 #default side length
        self.vertices = []
        self.folds = set()

    def normalize(self):
        # scale the crease pattern so that the vertices are in the range [0, 1]
        # do this by dividing by the side length

        for v in self.vertices:
            v.x /= self.side
            v.y /= self.side

        self.side = 1

    def scale(self, n):
        # scale the crease pattern by n
        for v in self.vertices:
            v.x *= n
            v.y *= n
        self.side *= n

    def add_vertex(self, x, y):
        # if the vertex is already in the crease pattern, don't add it
        for v in self.vertices:
            if v.x == x and v.y == y:
                return
        self.vertices.append(Vertex(x, y))

    def add_foldf(self, f):
        # if the fold is already in the crease pattern, don't add it
        for f2 in self.folds:
            if (f2.v1 == f.v1 and f2.v2 == f.v2) or (f2.v1 == f.v2 and f2.v2 == f.v1):
                return
        # if the vertices are not in the crease pattern, add them
        if f.v1 not in self.vertices:
            self.vertices.append(f.v1)
        if f.v2 not in self.vertices:
            self.vertices.append(f.v2)
        self.folds.add(f)
        f.v1.d += 1
        f.v1.adj.add(f)
        f.v1.adjv.add(f.v2)
        f.v2.d += 1
        f.v2.adj.add(f)
        f.v2.adjv.add(f.v1)

    def add_fold(self, v1, v2, type=-1):
        # if the fold is already in the crease pattern, don't add it
        for f in self.folds:
            if (f.v1 == v1 and f.v2 == v2) or (f.v1 == v2 and f.v2 == v1):
                return
        # if the vertices are not in the crease pattern, add them
        if v1 not in self.vertices:
            self.vertices.append(v1)
        if v2 not in self.vertices:
            self.vertices.append(v2)
        f = Fold(v1, v2, type)
        self.folds.add(f)
        v1.d += 1
        v1.adj.add(f)
        v1.adjv.add(v2)
        v2.d += 1
        v2.adj.add(f)
        v2.adjv.add(v1)

    def add_random_vertex(self):
        self.add_vertex(random.randint(0, self.side), random.randint(0, self.side))

    def add_random_vertex_on_edge(self):
        # add a vertex on the edge of the square
        x = random.randint(0, self.side)
        y = random.randint(0, self.side)
        if x == 0 or x == self.side:
            y = random.randint(0, self.side)
        else:
            y = 0
        self.vertices.add(Vertex(x, y))

    def add_square_vertices(self):
        # add the vertices of the square
        self.add_vertex(0, 0)
        self.add_vertex(self.side, 0)
        self.add_vertex(self.side, self.side)
        self.add_vertex(0, self.side)

    def push_to_edge(self, x):
        # if a vertex is within x of an edge, push it to the edge
        for v in self.vertices:
            if v.x < x:
                v.x = 0
            if v.x > self.side - x:
                v.x = self.side
            if v.y < x:
                v.y = 0
            if v.y > self.side - x:
                v.y = self.side
        # if any folds are on the edge, remove them
        set_copy = self.folds.copy()
        for f in set_copy:
            if self.on_edge(f.v1) and self.on_edge(f.v2):
                self.remove_fold(f)

    def triangulate(self):
        # perform Delaunay triangulation
        vertices = list(self.vertices)
        points = []
        for v in vertices:
            points.append([v.x, v.y])
        points = np.array(points)
        tri = Delaunay(points)
        # add folds with default to nothing
        for t in tri.simplices:
            self.add_fold(vertices[t[0]], vertices[t[1]], -1)
            self.add_fold(vertices[t[1]], vertices[t[2]], -1)
            self.add_fold(vertices[t[2]], vertices[t[0]], -1)

    def remove_fold(self, f):
        # remove a fold from the crease pattern
        self.folds.remove(f)
        f.v1.d -= 1
        f.v2.d -= 1
        f.v1.adj.remove(f)
        f.v2.adj.remove(f)
        # if the vertices are now degree zero, remove them
        if f.v1.d == 0:
            self.vertices.remove(f.v1)
        if f.v2.d == 0:
            self.vertices.remove(f.v2)

    def remove_vertex(self, v):
        # remove a vertex from the crease pattern
        # first, remove the adjacent folds
        adj = v.adj.copy()
        for f in adj:
            self.remove_fold(f)
        # then, remove the vertex
        self.vertices.remove(v)

    def remove_edge_folds(self):
        # remove folds that are on the edge of the square
        set_copy = self.folds.copy()
        for f in set_copy:
            if f.v1.x == 0 and f.v2.x == 0:
                self.remove_fold(f)
            if f.v1.x == self.side and f.v2.x == self.side:
                self.remove_fold(f)
            if f.v1.y == 0 and f.v2.y == 0:
                self.remove_fold(f)
            if f.v1.y == self.side and f.v2.y == self.side:
                self.remove_fold(f)

    def on_edge(self, v):
        # check if a vertex is on the edge of the square
        if v.x == 0 or v.x == self.side or v.y == 0 or v.y == self.side:
            return True
        return False

    def on_edge_fold(self, f):
        # check if a fold lies on the edge of the square
        return self.on_edge(f.v1) and self.on_edge(f.v2)

    def on_corner(self, v):
        # check if a vertex is on a corner of the square
        if (v.x == 0 or v.x == self.side) and (v.y == 0 or v.y == self.side):
            return True
        return False

    def evenize_vertices(self):
        # make the vertices have even degree by removing edges
        # There must be an even number of odd vertices

        # first, get a list of the vertices that have odd degree
        odd_vertices = []
        for v in self.vertices:
            if v.d % 2 == 1:
                odd_vertices.append(v)

        # loop until there are no odd vertices
        while len(odd_vertices) > 0:
            # pick the first odd vertex
            v = odd_vertices[0]
            # find the next closest odd vertex using BFS

            # first, initialize the queue
            queue = []
            queue.append(v)
            # initialize the set of visited vertices
            visited = set()
            visited.add(v)
            # initialize the dictionary of parents
            parents = {}
            parents[v] = None
            # search for the next closest odd vertex
            found = False
            while len(queue) > 0:
                # get the next vertex
                v = queue.pop(0)
                # check if it is odd
                if v.d % 2 == 1 and v != odd_vertices[0]:
                    found = True
                    break
                # add the adjacent vertices to the queue
                for f in v.adj:
                    if f.v1 == v:
                        v2 = f.v2
                    else:
                        v2 = f.v1
                    if v2 not in visited:
                        queue.append(v2)
                        visited.add(v2)
                        parents[v2] = v
            # get the path from the first odd vertex to the next closest odd vertex
            path = []
            if found:
                while v is not None:
                    path.append(v)
                    v = parents[v]
            # remove the edges along the path
            for i in range(len(path)-1):
                # make a copy of the set of adjacent folds
                # because we can't modify the set while iterating over it
                adj = path[i].adj.copy()
                for f in adj:
                    if f.v1 == path[i+1] or f.v2 == path[i+1]:
                        self.remove_fold(f)
            # update the list of odd vertices
            odd_vertices = []
            for v in self.vertices:
                if v.d % 2 == 1:
                    odd_vertices.append(v)

    def even_degree(self):
        # check if all vertices have even degree
        for v in self.none_edge_vertices():
            if v.d % 2 == 1:
                return False
        return True

    def clockwise_neighbors(self, v):
        # return list of vertices adjacent to v in clockwise order

        # first, get a list of the vertices adjacent to v
        adj = []
        for f in v.adj:
            if f.v1 == v:
                adj.append(f.v2)
            else:
                adj.append(f.v1)

        # next, sort them in clockwise order
        # use atan2 to get the angle of each vertex relative to v
        angles = []
        for v2 in adj:
            angles.append(math.atan2(v2.y - v.y, v2.x - v.x) + math.pi)
        # sort the vertices by angle
        adj = [x for _,x in sorted(zip(angles, adj), key=lambda x: x[0])]
        return adj

    def adjacent_angles(self, v):
        # return list of angles between adjacent vertices in clockwise order
        # if the angle would be negative, add 2pi
        angles = []
        adj = self.clockwise_neighbors(v)
        for i in range(len(adj)):
            v1 = adj[i]
            v2 = adj[(i+1)%len(adj)]
            angle = math.atan2(v2.y - v.y, v2.x - v.x) - math.atan2(v1.y - v.y, v1.x - v.x)
            if angle < 0:
                angle += 2*math.pi
            angles.append(angle)
        return angles

    def none_edge_vertices(self):
        # return list of vertices that are not on the edge of the square
        vertices = []
        for v in self.vertices:
            if not self.on_edge(v):
                vertices.append(v)
        return vertices

    def l2_regularization(self, x, alpha):
        # Calculate the L2 regularization term
        reg_term = 0.5 * alpha * np.sum(x**2)
        return reg_term

    def objective(self, on_edge):
        # the objective is to minimize the sum of the squares of the distances between the guess and the actual coordinates
        # we only care about the vertices that are not on the edge of the square
        # x is a guess

        # get the indices in self.vertices of the vertices that are not on the edge of the square
        on_edge_indices = []
        for i in range(len(on_edge)):
            if on_edge[i]:
                on_edge_indices.append(i)

        # make a list of coordinates for each vertex to match the format of x
        coords = []
        for v in self.vertices:
            coords.append(v.x)
            coords.append(v.y)

        W = 1
        def fun(X):
            sum = 0
            for i in range(len(self.vertices)):
                if i in on_edge_indices:
                    W = 1000000
                else:
                    W = 1
                sum += W * ((X[2*i] - coords[2*i])**2 + (X[2*i+1]- coords[2*i+1])**2)
            res = self.l2_regularization(sum, .1)
            return res
        return fun

    def make_constraints(self, parity, vi1, vi2, indices):
        def fun(X):
            v_coords = [X[vi1], X[vi2]]
            # get the coordinates of the adjacent vertices indexed from x
            adj_coords = []
            for i in indices:
                adj_coords.append(X[i])
            # so adj_coords is a list of the coordinates of the adjacent vertices
            # x, y, x, y, x, y, ...
            # then we get the coordinates of the vertex from X

            # get the angles between adjacent vertices in clockwise order
            angles = []
            for i in range(0, len(indices), 2):
                x1 = adj_coords[i]
                y1 = adj_coords[i+1]
                x2 = adj_coords[(i+2)%len(adj_coords)]
                y2 = adj_coords[(i+3)%len(adj_coords)]

                angle = math.atan2(y2 - v_coords[1], x2 - v_coords[0]) - math.atan2(y1 - v_coords[1], x1 - v_coords[0])
                if angle < 0:
                    angle += 2*math.pi
                angles.append(angle)
            # sum of even angles should be pi
            s = 0
            for i in range(len(angles)):
                if i % 2 == parity:
                    s += angles[i]
            return s - math.pi
        return fun

    def generate_constraints(self):
        # generate constraints for scipy.optimize.minimize
        # the sum of the even angles around the vertex should be pi
        # the sum of the odd angles around the vertex should be pi as well
        # this should take in a list of coordinates of vertices
        # then, it should generate constraints for each vertex using the coordinates and the adjacent vertices

        # get the vertices that are not on the edge of the square
        vertices = self.vertices

        # generate constraints
        constraints = []

        for i in range(len(vertices)):
            v = vertices[i]
            vi1 = 2*i
            vi2 = 2*i+1

            # get the indices of the adjacent vertices
            indices = []
            for v2 in self.clockwise_neighbors(v):
                indices.append(2*self.vertices.index(v2))
                indices.append(2*self.vertices.index(v2)+1)

            constraint2 = self.make_constraints(1, vi1, vi2, indices)

            if not self.on_edge(v):
                # add the constraints only if the vertex is not on the edge of the square
                constraints.append({'type': 'eq', 'fun': constraint2})
        return constraints


    def optimize(self):
        # initial guess is current coordinates of vertices
        # constraints are that the even angles around each vertex are pi
        # and the odd angles are pi as well

        # first, normalize the crease pattern
        self.normalize()
        # generate initial guess
        x0 = []
        # note which vertices are not on the edge of the square
        on_edge = []
        for v in self.vertices:
            x0.append(v.x)
            x0.append(v.y)
            if self.on_edge(v):
                on_edge.append(True)
            else:
                on_edge.append(False)

        # minimize
        myconstraints = self.generate_constraints()
        # Keep the optimizer quiet in the terminal; the GUI surfaces the
        # relevant loss and iteration diagnostics directly.
        res = minimize(
            self.objective(on_edge),
            x0,
            constraints=myconstraints,
            method='SLSQP',
            options={'disp': False},
        )
        # update the coordinates of the vertices
        for i in range(len(self.vertices)):
            self.vertices[i].x = res.x[2*i]
            self.vertices[i].y = res.x[2*i+1]

        # by default, push all vertices to the edge of the square with a 1% tolerance
        self.push_to_edge(0.001*self.side)

        return res

    def clear(self):
        # remove all vertices and folds
        self.vertices = []
        self.folds = set()

    def clone(self):
        clone = CreasePattern()
        clone.side = self.side
        vertex_map = {}
        for vertex in self.vertices:
            cloned_vertex = Vertex(vertex.x, vertex.y)
            clone.vertices.append(cloned_vertex)
            vertex_map[vertex] = cloned_vertex

        for fold in self.folds:
            clone.add_fold(vertex_map[fold.v1], vertex_map[fold.v2], fold.type)
        return clone

    def to_data(self):
        vertex_index = {vertex: index for index, vertex in enumerate(self.vertices)}
        folds = []
        for fold in self.folds:
            folds.append(
                {
                    "v1": int(vertex_index[fold.v1]),
                    "v2": int(vertex_index[fold.v2]),
                    "type": int(fold.type),
                }
            )

        folds.sort(key=lambda item: (min(item["v1"], item["v2"]), max(item["v1"], item["v2"])))
        return {
            "side": float(self.side),
            "vertices": [{"x": float(vertex.x), "y": float(vertex.y)} for vertex in self.vertices],
            "folds": folds,
        }

    @classmethod
    def from_data(cls, data):
        pattern = cls()
        pattern.side = data.get("side", 1)

        vertices = []
        for vertex_data in data.get("vertices", []):
            vertex = Vertex(vertex_data["x"], vertex_data["y"])
            pattern.vertices.append(vertex)
            vertices.append(vertex)

        for fold_data in data.get("folds", []):
            v1 = vertices[fold_data["v1"]]
            v2 = vertices[fold_data["v2"]]
            pattern.add_fold(v1, v2, fold_data.get("type", -1))

        return pattern

    def vertex_index_map(self):
        return {vertex: index for index, vertex in enumerate(self.vertices)}

    def fold_index_map(self):
        vertex_index = self.vertex_index_map()
        ordered = sorted(
            self.folds,
            key=lambda fold: tuple(sorted((vertex_index[fold.v1], vertex_index[fold.v2]))),
        )
        return {fold: index for index, fold in enumerate(ordered)}

    def maekawa_counts(self, v):
        mountains = 0
        valleys = 0
        assigned = False
        for f in v.adj:
            if f.type == 0:
                mountains += 1
                assigned = True
            elif f.type == 1:
                valleys += 1
                assigned = True
        if not assigned:
            return None
        return mountains, valleys

    def maekawa_balance(self, v):
        counts = self.maekawa_counts(v)
        if counts is None:
            return None
        mountains, valleys = counts
        return mountains - valleys

    def kawasaki_sums(self, v):
        if self.on_edge(v):
            return None
        angles = self.adjacent_angles(v)
        if len(angles) % 2 == 1:
            return None
        return sum(angles[::2]), sum(angles[1::2])

    def kawasaki_error(self, v, tolerance=1e-6):
        if self.on_edge(v):
            return 0.0
        sums = self.kawasaki_sums(v)
        if sums is None:
            return float("inf")
        even_sum, odd_sum = sums
        return max(abs(even_sum - math.pi), abs(odd_sum - math.pi))

    def crossing_fold_pairs(self, epsilon=None):
        if epsilon is None:
            epsilon = max(1e-6 * float(self.side or 1.0), 1e-6)
        index_map = self.fold_index_map()
        crossings = []
        ordered_folds = sorted(self.folds, key=lambda fold: index_map[fold])
        for index, first in enumerate(ordered_folds):
            a0 = (float(first.v1.x), float(first.v1.y))
            a1 = (float(first.v2.x), float(first.v2.y))
            for second in ordered_folds[index + 1 :]:
                if len({first.v1, first.v2, second.v1, second.v2}) < 4:
                    continue
                b0 = (float(second.v1.x), float(second.v1.y))
                b1 = (float(second.v2.x), float(second.v2.y))
                if _segments_intersect(a0, a1, b0, b1, epsilon):
                    crossings.append((index_map[first], index_map[second]))
        return tuple(crossings)

    def analyze_local(self, tolerance=1e-6):
        diagnostics = []
        vertex_index = self.vertex_index_map()
        for vertex in self.vertices:
            on_edge = self.on_edge(vertex)
            even_degree_ok = vertex.d % 2 == 0
            kawasaki_even_sum = None
            kawasaki_odd_sum = None
            kawasaki_error = None
            kawasaki_ok = True if on_edge else False
            if not on_edge:
                sums = self.kawasaki_sums(vertex)
                if sums is not None:
                    kawasaki_even_sum, kawasaki_odd_sum = sums
                    kawasaki_error = max(
                        abs(kawasaki_even_sum - math.pi),
                        abs(kawasaki_odd_sum - math.pi),
                    )
                    kawasaki_ok = kawasaki_error <= tolerance

            maekawa_counts = self.maekawa_counts(vertex)
            maekawa_ok = None
            maekawa_mountains = None
            maekawa_valleys = None
            maekawa_balance = None
            if maekawa_counts is not None:
                maekawa_mountains, maekawa_valleys = maekawa_counts
                maekawa_balance = maekawa_mountains - maekawa_valleys
                maekawa_ok = on_edge or abs(maekawa_balance) == 2

            messages = []
            if not on_edge and not even_degree_ok:
                messages.append("Interior vertex has odd degree.")
            if not on_edge and not kawasaki_ok:
                messages.append("Kawasaki balance failed.")
            if maekawa_ok is False:
                messages.append("Assigned folds violate Maekawa.")

            diagnostics.append(
                VertexLocalDiagnostic(
                    vertex_index=vertex_index[vertex],
                    on_edge=on_edge,
                    degree=vertex.d,
                    even_degree_ok=even_degree_ok,
                    kawasaki_ok=kawasaki_ok,
                    kawasaki_even_sum=kawasaki_even_sum,
                    kawasaki_odd_sum=kawasaki_odd_sum,
                    kawasaki_error=kawasaki_error,
                    maekawa_ok=maekawa_ok,
                    maekawa_mountains=maekawa_mountains,
                    maekawa_valleys=maekawa_valleys,
                    maekawa_balance=maekawa_balance,
                    message=" ".join(messages),
                )
            )
        return tuple(diagnostics)

    def analyze_assignments(self):
        assigned_fold_count = sum(1 for fold in self.folds if fold.type in (0, 1))
        unassigned_fold_count = sum(1 for fold in self.folds if fold.type == -1)
        maekawa_failures = []
        for diagnostic in self.analyze_local():
            if diagnostic.on_edge:
                continue
            if diagnostic.maekawa_ok is False:
                maekawa_failures.append(diagnostic.vertex_index)
        return FoldAssignmentDiagnostic(
            assigned_fold_count=assigned_fold_count,
            unassigned_fold_count=unassigned_fold_count,
            maekawa_failures=tuple(maekawa_failures),
            underdetermined=unassigned_fold_count > 0,
        )

    def analyze_pattern(self, tolerance=1e-6):
        vertex_diagnostics = self.analyze_local(tolerance=tolerance)
        assignment = self.analyze_assignments()
        interior_vertices = [item for item in vertex_diagnostics if not item.on_edge]

        local_failures = [
            item
            for item in interior_vertices
            if (not item.even_degree_ok) or (not item.kawasaki_ok)
        ]
        local_status = STATUS_PASS if not local_failures else STATUS_FAIL

        if assignment.maekawa_failures:
            fold_assignment_status = STATUS_FAIL
        elif assignment.assigned_fold_count == 0:
            fold_assignment_status = STATUS_NOT_RUN
        elif assignment.underdetermined:
            fold_assignment_status = STATUS_WARNING
        else:
            fold_assignment_status = STATUS_PASS

        crossing_pairs = self.crossing_fold_pairs()
        if crossing_pairs:
            global_status = STATUS_FAIL
            global_message = "Crossing folds were detected."
        elif not self.folds:
            global_status = STATUS_NOT_RUN
            global_message = "No interior folds are available for global analysis."
        elif fold_assignment_status == STATUS_NOT_RUN:
            global_status = STATUS_UNKNOWN
            global_message = "Assign folds before claiming global flat-foldability."
        else:
            global_status = STATUS_UNKNOWN
            global_message = "Only local conditions are certified at this stage."

        summary = []
        if local_failures:
            first = local_failures[0]
            summary.append(f"Vertex {first.vertex_index} fails a local condition.")
        elif assignment.maekawa_failures:
            summary.append(
                f"Assigned folds violate Maekawa at vertex {assignment.maekawa_failures[0]}."
            )
        elif crossing_pairs:
            first_a, first_b = crossing_pairs[0]
            summary.append(f"Folds {first_a} and {first_b} cross geometrically.")
        elif not self.folds:
            summary.append("No interior folds are present yet.")
        elif assignment.underdetermined:
            summary.append("Some folds are still unassigned.")
        else:
            summary.append("Local diagnostics look consistent.")

        return PatternDiagnosticReport(
            local_status=local_status,
            global_status=global_status,
            preview_status=STATUS_NOT_RUN,
            fold_assignment_status=fold_assignment_status,
            vertex_diagnostics=vertex_diagnostics,
            fold_assignment=assignment,
            global_diagnostic=GlobalDiagnostic(
                status=global_status,
                used_exact_faces=False,
                used_reference_pattern=False,
                uses_provisional_signs=False,
                uses_approximate_cycles=False,
                cycle_drift=None,
                crossing_fold_pairs=crossing_pairs,
                face_count=None,
                message=global_message,
            ),
            summary=tuple(summary),
        )

    def maekawa(self, v):
        # check if v satisfies Maekawa's theorem, that the number of mountain folds is equal to the number of valley folds +- 2
        # first, get the number of mountain and valley folds
        balance = self.maekawa_balance(v)
        if balance is None:
            return False
        return balance in (-2, 2)

    def kawasaki(self, v, tolerance=1e-6):
        # check Kawasaki's theorem at a single interior vertex
        if self.on_edge(v):
            return True
        return self.kawasaki_error(v, tolerance=tolerance) <= tolerance

    def locally_flat_foldable(self, tolerance=1e-6):
        # local flat-foldability needs even degree and Kawasaki at every interior vertex
        for v in self.none_edge_vertices():
            if v.d % 2 == 1:
                return False
            if not self.kawasaki(v, tolerance=tolerance):
                return False
        return True

    def clockwise_folds(self, v):
        # return folds incident to v in clockwise order
        adj_folds = []
        for neighbor in self.clockwise_neighbors(v):
            for fold in neighbor.adj:
                if fold.v1 == v or fold.v2 == v:
                    adj_folds.append(fold)
                    break
        return adj_folds

    def _assignment_signature(self):
        vertex_index = self.vertex_index_map()
        ordered = sorted(
            self.folds,
            key=lambda fold: tuple(sorted((vertex_index[fold.v1], vertex_index[fold.v2]))),
        )
        return tuple(fold.type for fold in ordered)

    def _interior_vertices_satisfy_maekawa(self):
        for vertex in self.none_edge_vertices():
            if not self.maekawa(vertex):
                return False
        return True

    def _apply_fold_updates(self, updates):
        for fold, fold_type in updates.items():
            fold.type = fold_type

    def _obtuse_monochrome_glitches(self, v, tolerance=1e-9):
        if self.on_edge(v):
            return tuple()

        folds = self.clockwise_folds(v)
        angles = self.adjacent_angles(v)
        if len(folds) < 3 or len(angles) != len(folds):
            return tuple()

        threshold = (math.pi / 2.0) + tolerance
        glitches = []
        for index in range(len(angles)):
            if angles[index] <= threshold or angles[(index + 1) % len(angles)] <= threshold:
                continue

            left = folds[index]
            middle = folds[(index + 1) % len(folds)]
            right = folds[(index + 2) % len(folds)]
            if (
                left.type not in (0, 1)
                or middle.type not in (0, 1)
                or right.type not in (0, 1)
            ):
                continue

            if left.type == right.type and middle.type != left.type:
                glitches.append((left, middle, right))

        return tuple(glitches)

    def _count_obtuse_monochrome_glitches(self):
        total = 0
        for vertex in self.none_edge_vertices():
            total += len(self._obtuse_monochrome_glitches(vertex))
        return total

    def _maekawa_preserving_glitch_fix(self, vertex, left, middle, right):
        candidates = (
            {middle: left.type},
            {left: middle.type, right: middle.type},
        )
        valid_updates = []

        for updates in candidates:
            original = {fold: fold.type for fold in updates}
            self._apply_fold_updates(updates)
            if self.maekawa(vertex) and self._interior_vertices_satisfy_maekawa():
                valid_updates.append(dict(updates))
            self._apply_fold_updates(original)

        if len(valid_updates) == 1:
            return valid_updates[0]
        return None

    def repair_obtuse_monochrome_glitches(self):
        repairs = 0
        seen_signatures = {self._assignment_signature()}

        while True:
            current_glitch_count = self._count_obtuse_monochrome_glitches()
            if current_glitch_count == 0:
                break

            best_updates = None
            best_glitch_count = None
            best_update_size = None
            best_signature = None

            for vertex in self.none_edge_vertices():
                for left, middle, right in self._obtuse_monochrome_glitches(vertex):
                    updates = self._maekawa_preserving_glitch_fix(
                        vertex,
                        left,
                        middle,
                        right,
                    )
                    if updates is None:
                        continue

                    original = {fold: fold.type for fold in updates}
                    self._apply_fold_updates(updates)
                    candidate_signature = self._assignment_signature()
                    candidate_glitch_count = self._count_obtuse_monochrome_glitches()
                    self._apply_fold_updates(original)

                    if candidate_signature in seen_signatures:
                        continue

                    if (
                        best_glitch_count is None
                        or candidate_glitch_count < best_glitch_count
                        or (
                            candidate_glitch_count == best_glitch_count
                            and len(updates) < best_update_size
                        )
                        or (
                            candidate_glitch_count == best_glitch_count
                            and len(updates) == best_update_size
                            and candidate_signature < best_signature
                        )
                    ):
                        best_updates = dict(updates)
                        best_glitch_count = candidate_glitch_count
                        best_update_size = len(updates)
                        best_signature = candidate_signature

            if best_updates is None or best_glitch_count > current_glitch_count:
                break

            self._apply_fold_updates(best_updates)
            seen_signatures.add(self._assignment_signature())
            repairs += 1

        return repairs

    def get_pairings(self, v):
        # Run algorithm to pair vertices around locally minimal angles
        # This is the algorithm from the paper The Complexity of Flat Origami by Bern and Hayes
        # angles[i] is the angle between adj[i] and adj[i+1]
        adj = self.clockwise_neighbors(v)
        adj_folds = []
        for v1 in adj:
            for f in v1.adj:
                if f.v1 == v or f.v2 == v:
                    adj_folds.append(f)
        angles = self.adjacent_angles(v)

        # start with empty pairings
        pairings = []
        # loop until all folds are paired
        i = 0
        while len(angles) > 2:
            for i in range(len(angles)):
                # check if angle is locally minimal (less than both adjacent angles)
                if angles[i] <= angles[(i+1)%len(angles)] and angles[i] <= angles[(i-1)%len(angles)]:
                    # then pair the folds
                    # add the flag 0 to indicate these folds have opposite mountain/valley assignment
                    pairings.append(([adj_folds[i], adj_folds[(i+1)%len(adj_folds)]], [2,0]))
                    # remove the wedge by subtracting angles[i] from angles[i+1], and removing angles[i]
                    # then, remove the adjacent folds
                    angles[(i-1)%len(angles)] = angles[(i-1)%len(angles)] + angles[(i+1)%len(angles)] - angles[i]
                    del angles[i]
                    del angles[(i+1)%len(angles)]
                    del adj_folds[i]
                    del adj_folds[i%len(adj_folds)]
                    break
        # the final two folds are paired with the flag 1 to indicate they have the same mountain/valley assignment
        if len(angles) == 2:
            pairings.append(([adj_folds[0], adj_folds[1]], [2,1]))
        return pairings

    def get_pairings_on_edge(self, v):
        if(self.on_corner(v)):
            # case when v is on a corner of the square
            # make different cases for each corner
            if v.x == 0 and v.y == 0:
                # top left corner
                f1 = Fold(v, Vertex(0, self.side), 0)
                f2 = Fold(v, Vertex(self.side, 0), 0)
            elif v.x == self.side and v.y == 0:
                # top right corner
                f1 = Fold(v, Vertex(0, 0), 0)
                f2 = Fold(v, Vertex(self.side, self.side), 0)
            elif v.x == self.side and v.y == self.side:
                # bottom right corner
                f1 = Fold(v, Vertex(self.side, 0), 0)
                f2 = Fold(v, Vertex(0, self.side), 0)
            elif v.x == 0 and v.y == self.side:
                # bottom left corner
                f1 = Fold(v, Vertex(0, 0), 0)
                f2 = Fold(v, Vertex(self.side, self.side), 0)
        elif self.on_edge(v):
            # case when v is on an edge of the square
            # make different cases for each edge
            if v.x == 0:
                # left edge
                f1 = Fold(v, Vertex(0, 0), 0)
                f2 = Fold(v, Vertex(0, self.side), 0)
            elif v.x == self.side:
                # right edge
                f1 = Fold(v, Vertex(self.side, 0), 0)
                f2 = Fold(v, Vertex(self.side, self.side), 0)
            elif v.y == 0:
                # top edge
                f1 = Fold(v, Vertex(0, 0), 0)
                f2 = Fold(v, Vertex(self.side, 0), 0)
            elif v.y == self.side:
                # bottom edge
                f1 = Fold(v, Vertex(0, self.side), 0)
                f2 = Fold(v, Vertex(self.side, self.side), 0)
        self.add_foldf(f1)
        self.add_foldf(f2)
        # case when v is not on the edge of the square
        adj = self.clockwise_neighbors(v)
        # rotate the list of adjacent vertices so that the first vertex is on the edge
        while not self.on_edge(adj[0]):
            adj.append(adj.pop(0))
        # get the adjacent folds
        adj_folds = []
        for v1 in adj:
            for f in v1.adj:
                if f.v1 == v or f.v2 == v:
                    adj_folds.append(f)
        # get the angle between successive adjacent folds
        angles = []
        for i in range(len(adj)):
            v1 = adj[i]
            v2 = adj[(i+1)%len(adj)]
            angle = math.atan2(v2.y - v.y, v2.x - v.x) - math.atan2(v1.y - v.y, v1.x - v.x)
            if angle < 0:
                angle += 2*math.pi
            angles.append(angle)
        # start with empty pairings
        pairings = []

        # loop until all vertices are paired
        # the difference between now and before is we don't take the mod at the edges
        while len(angles) > 2:
            for i in range(len(angles)):
                # check if angle is locally minimal (less than both adjacent angles)
                if angles[i] <= angles[min(i+1, len(angles)-1)] and angles[i] <= angles[max(0,i-1)]:
                    # then make a group with the vertices
                    # if one of the folds is on the edge, do not add it to the group
                    group = []
                    if not self.on_edge_fold(adj_folds[i]):
                        group.append(adj_folds[i])
                    if not self.on_edge_fold(adj_folds[min(i+1, len(angles)-1)]):
                        group.append(adj_folds[min(i+1, len(angles)-1)])
                    if len(group) == 1:
                        pairings.append((group, [2]))
                    if len(group) == 2:
                        pairings.append((group, [2,0]))
                    # remove the wedge by subtracting angles[i] from angles[i+1], and removing angles[i]
                    # then, remove the adjacent folds
                    angles[max(0,i-1)] = angles[max(0,i-1)] + angles[min(i+1, len(angles)-1)] - angles[i]
                    del angles[i]
                    del angles[min(i+1, len(angles)-1)]
                    del adj_folds[i]
                    del adj_folds[min(i,len(adj_folds)-1)]
                    break
        if len(angles) == 1:
            if not self.on_edge_fold(adj_folds[0]):
                # add the flag 2 to indicate this one fold has arbitrary assignment
                pairings.append(([adj_folds[0]], [2]))
        if len(angles) == 2:
            # check if both folds are on the edge
            if not self.on_edge_fold(adj_folds[0]) and not self.on_edge_fold(adj_folds[1]):
                # if not, add them to the pairings
                # add the flag 1 to indicate the second fold is the same mountain/valley assignment as the first
                pairings.append(([adj_folds[0], adj_folds[1]], [2, 1]))
        self.remove_fold(f1)
        self.remove_fold(f2)
        return pairings

    def assign_mv(self):
        # Run algorithm to assign mountain and valley folds
        # This is the algorithm from the paper The Complexity of Flat Origami by Bern and Hayes

        # first verify that the crease pattern has even degree
        if not self.even_degree():
            self._clear_assignments()
            return AssignmentSearchResult(
                success=False,
                message="Interior vertices must have even degree before assigning folds.",
                assigned_fold_count=0,
                unassigned_fold_count=len(self.folds),
                group_count=0,
            )

        # start from a neutral state so reruns do not inherit stale assignments
        for fold in self.folds:
            fold.type = -1

        groupings = []
        for v in self.vertices:
            if self.on_edge(v):
                groupings.append(self.get_pairings_on_edge(v))
            else:
                groupings.append(self.get_pairings(v))

        groupings = [item for sublist in groupings for item in sublist]
        # combine groups if we can form a chain by combining their folds
        # loop until no more groups can be combined
        combined = True
        while combined:
            combined = False
            for i in range(len(groupings)):
                for j in range(i+1, len(groupings)):
                    # check if the groups can be combined
                    # we may have to reverse the order of one of the groups
                    # so that the first fold of the first group is the last fold of the second group

                    # each grouping is a list of folds and a list of flags
                    # if flag[i] = 0, then the ith fold is mountain/valley opposite the previous fold
                    # if flag[i] = 1, then the ith fold is mountain/valley the same as the previous fold
                    # if flag[i] = 2, then the ith fold is arbitrary
                    # we combine groups and modify the flags accordingly
                    g1 = groupings[i][0]
                    g2 = groupings[j][0]
                    flag1 = groupings[i][1]
                    flag2 = groupings[j][1]
                    if g1[0] == g2[-1]:
                        # the end of g2 is the beginning of g1
                        # combine the groups and combine the flags
                        groupings[i] = (g2[:-1] + g1, flag2 + flag1[1:])
                        del groupings[j]
                        combined = True
                        break
                    elif g1[-1] == g2[0]:
                        # the end of g1 is the beginning of g2
                        # combine the groups
                        groupings[i] = (g1[:-1] + g2,  flag1 + flag2[1:])
                        del groupings[j]
                        combined = True
                        break
                    elif g1[0] == g2[0]:
                        # the beginning of g1 is the beginning of g2
                        # reverse the order of g2
                        g2.reverse()
                        flag2.reverse()
                        flag2 = [2] + flag2[:-1]
                        # combine the groups
                        groupings[i] = (g2[:-1] + g1,  flag2 + flag1[1:])
                        del groupings[j]
                        combined = True
                        break
                    elif g1[-1] == g2[-1]:
                        # reverse the order of g1
                        g1.reverse()
                        flag1.reverse()
                        flag1 = [2] + flag1[:-1]
                        # combine the groups
                        groupings[i] = (g2 + g1[1:],  flag2 + flag1[1:])
                        del groupings[j]
                        combined = True
                        break
        # print("check well formedness")
        # print([(self.vertices.index(f.v1), self.vertices.index(f.v2)) for f in self.folds])
        # print([([(self.vertices.index(f.v1), self.vertices.index(f.v2)) for f in g[0]], "parity", g[1]) for g in groupings])

        # I don't understand how there are duplicates in each group
        # But in anycase, remove them and their corresponding flag value
        for i in range(len(groupings)):
            g = groupings[i][0]
            flag = groupings[i][1]
            new_g = []
            new_flag = []
            for j in range(len(g)):
                if g[j] not in new_g:
                    new_g.append(g[j])
                    new_flag.append(flag[j])
            groupings[i] = (new_g, new_flag)

        def apply_choice(choice):
            for fold in self.folds:
                fold.type = -1
            for j in range(len(groupings)):
                group = groupings[j]
                group[0][0].type = choice[j]
                last = choice[j]
                for i in range(1, len(group[0])):
                    if group[1][i] == 0:
                        # opposite mountain/valley assignment as previous fold
                        last = 1 - last
                        group[0][i].type = last
                    elif group[1][i] == 1:
                        # same mountain/valley assignment as previous fold
                        group[0][i].type = group[0][i-1].type
                    else:
                        group[0][i].type = -1

        def assignment_signature():
            return self._assignment_signature()

        def interlacing_score():
            score = 0.0
            assigned_folds = sum(1 for fold in self.folds if fold.type != -1)
            score += 0.05 * assigned_folds

            for v in self.vertices:
                folds = self.clockwise_folds(v)
                if len(folds) < 2:
                    continue

                angles = self.adjacent_angles(v)
                transitions = 0.0
                repeats = 0.0
                assigned_pairs = 0

                if self.on_edge(v):
                    skipped_pair = max(range(len(angles)), key=lambda i: angles[i])
                    pair_indices = [i for i in range(len(folds)) if i != skipped_pair]
                else:
                    pair_indices = range(len(folds))

                for i in pair_indices:
                    left = folds[i]
                    right = folds[(i + 1) % len(folds)]
                    if left.type == -1 or right.type == -1:
                        continue

                    angle = angles[i]
                    wedge_weight = 1.0 + max(0.0, (math.pi - angle) / math.pi)
                    assigned_pairs += 1
                    if left.type != right.type:
                        transitions += wedge_weight
                    else:
                        repeats += wedge_weight

                if assigned_pairs == 0:
                    continue

                score += transitions - 0.65 * repeats

                types = [fold.type for fold in folds if fold.type != -1]
                if len(types) >= 3:
                    mountains = types.count(0)
                    valleys = types.count(1)
                    minority = min(mountains, valleys)
                    if minority > 0:
                        score += 0.2 * minority

            score -= 4.0 * self._count_obtuse_monochrome_glitches()

            return score

        best_choice = None
        best_score = None
        best_signature = None

        # enumerate all lists of 1 or 0 of length len(groupings)
        for choice in product([0, 1], repeat=len(groupings)):
            # we can make a choice for each group by assigning the first fold arbitrarily
            # then, we can assign the rest of the folds based on the flags
            apply_choice(choice)

            # check if every vertex not on an edge satisfies Maekawa's theorem
            succeeded = True
            for v in self.none_edge_vertices():
                if not self.maekawa(v):
                    succeeded = False
                    break
            if not succeeded:
                continue

            score = interlacing_score()
            signature = assignment_signature()
            if (
                best_score is None
                or score > best_score
                or (score == best_score and signature < best_signature)
            ):
                best_choice = choice
                best_score = score
                best_signature = signature

        if best_choice is not None:
            apply_choice(best_choice)
            repaired_glitches = self.repair_obtuse_monochrome_glitches()
            assigned_fold_count = sum(1 for fold in self.folds if fold.type in (0, 1))
            unassigned_fold_count = sum(1 for fold in self.folds if fold.type == -1)
            message = "A locally admissible mountain/valley assignment was found."
            if unassigned_fold_count > 0:
                message = (
                    "A locally admissible assignment was found, but some folds remain underdetermined."
                )
            if repaired_glitches > 0:
                detail = (
                    f" after repairing {repaired_glitches} obtuse-angle glitch"
                    f"{'es' if repaired_glitches != 1 else ''}"
                )
                if unassigned_fold_count > 0:
                    message = (
                        "A locally admissible assignment was found"
                        f"{detail}, but some folds remain underdetermined."
                    )
                else:
                    message = (
                        "A locally admissible mountain/valley assignment was found"
                        f"{detail}."
                    )
            return AssignmentSearchResult(
                success=True,
                message=message,
                assigned_fold_count=assigned_fold_count,
                unassigned_fold_count=unassigned_fold_count,
                group_count=len(groupings),
            )

        # if we get here, no choice worked
        self._clear_assignments()
        return AssignmentSearchResult(
            success=False,
            message="No locally admissible mountain/valley assignment was found for this geometry.",
            assigned_fold_count=0,
            unassigned_fold_count=len(self.folds),
            group_count=len(groupings),
        )

    def _clear_assignments(self):
        for fold in self.folds:
            fold.type = -1

    def get_svg(self, length):
        # return the svg of the crease pattern
        if svgwrite is None:
            raise RuntimeError("SVG export requires the optional 'svgwrite' dependency.")
        # first, scale the crease pattern by size
        self.normalize()
        self.scale(length)
        # get the coordinates of the square
        square_coords = []
        square_coords.append([0, 0])
        square_coords.append([self.side, 0])
        square_coords.append([self.side, self.side])
        square_coords.append([0, self.side])

        # start the svg file
        dwg = svgwrite.Drawing('square.svg', profile='tiny', size=(length, length))

        # draw the square
        dwg.add(dwg.polygon(square_coords, fill='none', stroke='black'))

        # draw the crease pattern
        # for each fold, draw a line with blue for valley folds and red for mountain folds
        for f in self.folds:
            if f.type == 0:
                color = 'red'
            elif f.type == 1:
                color = 'blue'
            else:
                color = 'black'
            dwg.add(dwg.line((f.v1.x, f.v1.y), (f.v2.x, f.v2.y), stroke=color))

        return dwg
    def export_svg(self, filename):
        # export the square and crease pattern to an svg file

        dwg = self.get_svg(300)
        # export the svg file with the given filename
        dwg.saveas(filename)

        # convert to png too
        if svg2png is not None:
            svg2png(url=filename, write_to=filename[:-4] + ".png")
