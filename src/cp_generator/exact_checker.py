from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from . import core as cp
from . import fold_sim


NEAR_FLAT_ANGLE = math.pi - 0.08


@dataclass(frozen=True)
class SmallInstanceCheckResult:
    status: str
    message: str
    face_count: int | None
    overlap_pair_count: int | None
    total_orders_checked: int
    unique_order: bool | None
    max_faces: int


def check_small_instance(
    pattern: cp.CreasePattern,
    *,
    max_faces: int = 8,
    max_orders: int = 100000,
) -> SmallInstanceCheckResult:
    report = pattern.analyze_pattern()
    if report.local_status == cp.STATUS_FAIL:
        return SmallInstanceCheckResult(
            status=cp.STATUS_FAIL,
            message="Local flat-fold conditions fail before the bounded exact checker can start.",
            face_count=None,
            overlap_pair_count=None,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )
    if report.fold_assignment_status == cp.STATUS_FAIL:
        return SmallInstanceCheckResult(
            status=cp.STATUS_FAIL,
            message="The mountain/valley assignment fails Maekawa, so no bounded exact stack order is possible.",
            face_count=None,
            overlap_pair_count=None,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )
    if report.fold_assignment_status != cp.STATUS_PASS:
        return SmallInstanceCheckResult(
            status=cp.STATUS_NOT_RUN,
            message="A complete mountain/valley assignment is required before the bounded exact checker can run.",
            face_count=None,
            overlap_pair_count=None,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )
    if report.global_diagnostic.crossing_fold_pairs:
        return SmallInstanceCheckResult(
            status=cp.STATUS_FAIL,
            message="Crossing folds are a certified obstruction for the bounded exact checker.",
            face_count=None,
            overlap_pair_count=None,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )

    try:
        model = fold_sim.build_folded_figure(pattern.clone())
    except fold_sim.FoldSimulationError as exc:
        return SmallInstanceCheckResult(
            status=cp.STATUS_UNKNOWN,
            message=f"Exact face reconstruction failed before bounded checking: {exc}",
            face_count=None,
            overlap_pair_count=None,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )

    if model.uses_provisional_signs or model.uses_approximate_cycles:
        return SmallInstanceCheckResult(
            status=cp.STATUS_UNKNOWN,
            message="The bounded exact checker only runs on exact face reconstructions without provisional signs or approximate cycle closure.",
            face_count=model.face_count,
            overlap_pair_count=None,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )

    if model.face_count > max_faces:
        return SmallInstanceCheckResult(
            status=cp.STATUS_NOT_RUN,
            message=f"The bounded exact checker is limited to at most {max_faces} faces.",
            face_count=model.face_count,
            overlap_pair_count=None,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )

    near_flat_points = model.face_points_at_angle(NEAR_FLAT_ANGLE)
    partial_order, overlap_pair_count, failure = _build_partial_order(
        model,
        near_flat_points,
    )
    if failure is not None:
        return SmallInstanceCheckResult(
            status=cp.STATUS_FAIL,
            message=failure,
            face_count=model.face_count,
            overlap_pair_count=overlap_pair_count,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )

    total_orders = _count_topological_orders(
        model.face_count,
        partial_order,
        max_orders=max_orders,
    )
    if total_orders == 0:
        return SmallInstanceCheckResult(
            status=cp.STATUS_FAIL,
            message="The exact face arrangement induces a cyclic stack-order constraint on a bounded instance.",
            face_count=model.face_count,
            overlap_pair_count=overlap_pair_count,
            total_orders_checked=0,
            unique_order=None,
            max_faces=max_faces,
        )

    if overlap_pair_count == 0:
        message = "The exact face arrangement has no interior-overlap pairs, so the bounded stack-order check passes vacuously."
    elif total_orders == 1:
        message = "A unique bounded stack order exists for the exact face arrangement."
    else:
        message = "At least one bounded stack order exists for the exact face arrangement."

    return SmallInstanceCheckResult(
        status=cp.STATUS_PASS,
        message=message,
        face_count=model.face_count,
        overlap_pair_count=overlap_pair_count,
        total_orders_checked=total_orders,
        unique_order=(total_orders == 1),
        max_faces=max_faces,
    )


def _build_partial_order(
    model: fold_sim.FoldedFigureModel,
    near_flat_points: tuple[np.ndarray, ...],
) -> tuple[set[tuple[int, int]], int, str | None]:
    epsilon_area = 1e-8
    epsilon_z = 1e-7
    relations: set[tuple[int, int]] = set()
    overlap_pair_count = 0

    flat_faces = tuple(points[:, :2] for points in model.final_face_points)
    for first_index in range(model.face_count):
        first_face = model.faces[first_index]
        for second_index in range(first_index + 1, model.face_count):
            second_face = model.faces[second_index]
            pair_sign: int | None = None
            pair_overlaps = 0

            for first_triangle in first_face.triangles:
                triangle_a_2d = np.array(
                    [flat_faces[first_index][local_index] for local_index in first_triangle],
                    dtype=float,
                )
                triangle_a_3d = np.array(
                    [near_flat_points[first_index][local_index] for local_index in first_triangle],
                    dtype=float,
                )
                for second_triangle in second_face.triangles:
                    triangle_b_2d = np.array(
                        [flat_faces[second_index][local_index] for local_index in second_triangle],
                        dtype=float,
                    )
                    triangle_b_3d = np.array(
                        [near_flat_points[second_index][local_index] for local_index in second_triangle],
                        dtype=float,
                    )
                    clipped = _clip_convex_polygon(triangle_a_2d, triangle_b_2d)
                    if len(clipped) < 3:
                        continue
                    area = abs(_polygon_area(clipped))
                    if area <= epsilon_area:
                        continue

                    pair_overlaps += 1
                    centroid = _polygon_centroid(clipped)
                    z_first = _interpolated_triangle_z(
                        triangle_a_2d,
                        triangle_a_3d,
                        centroid,
                    )
                    z_second = _interpolated_triangle_z(
                        triangle_b_2d,
                        triangle_b_3d,
                        centroid,
                    )
                    delta = z_first - z_second
                    if abs(delta) <= epsilon_z:
                        return relations, overlap_pair_count, (
                            f"Faces {first_index} and {second_index} become numerically indistinguishable in the bounded overlap check."
                        )
                    sign = 1 if delta > 0 else -1
                    if pair_sign is None:
                        pair_sign = sign
                    elif pair_sign != sign:
                        return relations, overlap_pair_count, (
                            f"Faces {first_index} and {second_index} reverse stack order across overlapping cells."
                        )

            if pair_overlaps:
                overlap_pair_count += 1
                if pair_sign is None:
                    continue
                if pair_sign > 0:
                    relations.add((first_index, second_index))
                else:
                    relations.add((second_index, first_index))

    return relations, overlap_pair_count, None


def _clip_convex_polygon(subject: np.ndarray, clipper: np.ndarray) -> np.ndarray:
    output = [point for point in subject]
    if len(output) == 0:
        return np.array([], dtype=float)

    clipper_list = [point for point in clipper]
    clip_area = _polygon_area(np.array(clipper_list, dtype=float))
    orientation = 1.0 if clip_area >= 0 else -1.0

    for start, end in zip(clipper_list, clipper_list[1:] + clipper_list[:1]):
        input_list = output
        output = []
        if not input_list:
            break
        previous = input_list[-1]
        for current in input_list:
            current_inside = _is_inside(current, start, end, orientation)
            previous_inside = _is_inside(previous, start, end, orientation)
            if current_inside:
                if not previous_inside:
                    output.append(_segment_intersection(previous, current, start, end))
                output.append(current)
            elif previous_inside:
                output.append(_segment_intersection(previous, current, start, end))
            previous = current

    if not output:
        return np.array([], dtype=float)
    return np.array(output, dtype=float)


def _is_inside(
    point: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
    orientation: float,
) -> bool:
    cross = (
        (end[0] - start[0]) * (point[1] - start[1])
        - (end[1] - start[1]) * (point[0] - start[0])
    )
    return orientation * cross >= -1e-10


def _segment_intersection(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
) -> np.ndarray:
    first_direction = first_end - first_start
    second_direction = second_end - second_start
    denominator = (
        first_direction[0] * second_direction[1]
        - first_direction[1] * second_direction[0]
    )
    if abs(denominator) <= 1e-12:
        return first_end
    delta = second_start - first_start
    t = (
        delta[0] * second_direction[1]
        - delta[1] * second_direction[0]
    ) / denominator
    return first_start + t * first_direction


def _polygon_area(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for first, second in zip(points, np.vstack((points[1:], points[:1]))):
        area += float(first[0] * second[1] - second[0] * first[1])
    return 0.5 * area


def _polygon_centroid(points: np.ndarray) -> np.ndarray:
    area_twice = 0.0
    centroid_x = 0.0
    centroid_y = 0.0
    for first, second in zip(points, np.vstack((points[1:], points[:1]))):
        cross = float(first[0] * second[1] - second[0] * first[1])
        area_twice += cross
        centroid_x += (first[0] + second[0]) * cross
        centroid_y += (first[1] + second[1]) * cross
    if abs(area_twice) <= 1e-12:
        return np.mean(points, axis=0)
    factor = 1.0 / (3.0 * area_twice)
    return np.array([centroid_x * factor, centroid_y * factor], dtype=float)


def _interpolated_triangle_z(
    triangle_2d: np.ndarray,
    triangle_3d: np.ndarray,
    point: np.ndarray,
) -> float:
    a, b, c = triangle_2d
    denominator = (
        (b[1] - c[1]) * (a[0] - c[0])
        + (c[0] - b[0]) * (a[1] - c[1])
    )
    if abs(denominator) <= 1e-12:
        return float(np.mean(triangle_3d[:, 2]))
    w1 = (
        (b[1] - c[1]) * (point[0] - c[0])
        + (c[0] - b[0]) * (point[1] - c[1])
    ) / denominator
    w2 = (
        (c[1] - a[1]) * (point[0] - c[0])
        + (a[0] - c[0]) * (point[1] - c[1])
    ) / denominator
    w3 = 1.0 - w1 - w2
    weights = np.array([w1, w2, w3], dtype=float)
    return float(np.dot(weights, triangle_3d[:, 2]))


def _count_topological_orders(
    face_count: int,
    relations: set[tuple[int, int]],
    *,
    max_orders: int,
) -> int:
    predecessors = [0] * face_count
    for higher, lower in relations:
        predecessors[lower] |= 1 << higher

    target_mask = (1 << face_count) - 1
    memo: dict[int, int] = {}

    def count(mask: int) -> int:
        if mask == target_mask:
            return 1
        if mask in memo:
            return memo[mask]

        total = 0
        for face_index in range(face_count):
            bit = 1 << face_index
            if mask & bit:
                continue
            if predecessors[face_index] & ~mask:
                continue
            total += count(mask | bit)
            if total >= max_orders:
                memo[mask] = max_orders
                return max_orders

        memo[mask] = total
        return total

    return count(0)
