from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
import json
import math
import random

from . import core as cp
from . import fold_sim


MODEL_SIDE = 500
PREVIEW_FRAME_COUNT = 13
DEFAULT_BUILD_PATTERN_ATTEMPTS = 16
DEFAULT_GEOMETRY_REPAIR_ATTEMPTS = 6
MIN_GENERIC_VERTEX_DISTANCE_RATIO = 1e-3
MIN_GENERIC_COLLINEAR_HEIGHT_RATIO = 1e-3
MAX_INTERIOR_SAMPLE_ATTEMPTS = 96

BASIS_CERTIFIED = "certified"
BASIS_HEURISTIC = "heuristic"
BASIS_LOCAL_ONLY = "local_only"
BASIS_NOT_RUN = "not_run"
BASIS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class GeometryQuality:
    generic: bool
    min_vertex_distance: float | None
    min_vertex_distance_ratio: float | None
    min_triangle_height: float | None
    min_triangle_height_ratio: float | None
    threshold: float
    closest_vertex_pair: tuple[int, int] | None = None
    most_collinear_triple: tuple[int, int, int] | None = None
    message: str = ""


@dataclass(frozen=True)
class OptimizationSummary:
    green: bool
    rounds: int
    iterations: int
    loss: float | None
    last_result: object | None = None
    geometry_quality: GeometryQuality | None = None


@dataclass(frozen=True)
class PreviewBuildResult:
    model: fold_sim.FoldedFigureModel | fold_sim.ApproximateFoldedFigureModel | None
    diagnostic: fold_sim.FoldSimulationDiagnostic
    payload: dict[str, object] | None
    solver: str
    source: str
    preview_reference_pattern: cp.CreasePattern | None
    failure_messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class RestoredSession:
    pattern: cp.CreasePattern
    point_count: str
    preview_reference_pattern: cp.CreasePattern | None
    fold_assignment_ready: bool
    extra_state: dict[str, object]


RESERVED_SESSION_KEYS = frozenset(
    {
        "format",
        "version",
        "point_count",
        "fold_assignment_ready",
        "pattern",
        "preview_reference_pattern",
    }
)


def build_pattern(point_count: int, *, side: int = MODEL_SIDE) -> cp.CreasePattern:
    return _build_pattern_with_retries(
        point_count,
        side=side,
        max_attempts=DEFAULT_BUILD_PATTERN_ATTEMPTS,
    )


def _build_pattern_with_retries(
    point_count: int,
    *,
    side: int,
    max_attempts: int,
) -> cp.CreasePattern:
    max_attempts = max(1, int(max_attempts))
    best_pattern: cp.CreasePattern | None = None
    best_quality: GeometryQuality | None = None
    for _ in range(max_attempts):
        pattern = _build_pattern_once(point_count, side=side)
        quality = geometry_quality(pattern)
        if best_pattern is None or _geometry_score(quality) > _geometry_score(best_quality):
            best_pattern = pattern
            best_quality = quality
        if quality.generic:
            return pattern
    assert best_pattern is not None
    return best_pattern


def _build_pattern_once(point_count: int, *, side: int = MODEL_SIDE) -> cp.CreasePattern:
    point_count = max(0, int(point_count))
    pattern = cp.CreasePattern()
    pattern.side = side
    pattern.add_square_vertices()
    _seed_interior_vertices(pattern, point_count, side=side)
    pattern.push_to_edge(_edge_clearance_for_side(side))
    pattern.triangulate()
    pattern.evenize_vertices()
    pattern.remove_edge_folds()
    return pattern


def _seed_interior_vertices(
    pattern: cp.CreasePattern,
    point_count: int,
    *,
    side: float,
) -> None:
    existing = [(float(vertex.x), float(vertex.y)) for vertex in pattern.vertices]
    for _ in range(max(0, int(point_count))):
        x, y = _sample_interior_vertex(existing, side=side)
        pattern.add_vertex(x, y)
        existing.append((x, y))


def _sample_interior_vertex(
    existing: list[tuple[float, float]],
    *,
    side: float,
    max_attempts: int = MAX_INTERIOR_SAMPLE_ATTEMPTS,
) -> tuple[float, float]:
    side = abs(float(side or 1.0)) or 1.0
    threshold = max(float(MIN_GENERIC_VERTEX_DISTANCE_RATIO) * side, 1e-12)
    height_threshold = max(float(MIN_GENERIC_COLLINEAR_HEIGHT_RATIO) * side, 1e-12)
    edge_clearance = min(max(_edge_clearance_for_side(side), 2.0 * threshold), side / 4.0)
    lower_bound = edge_clearance
    upper_bound = side - edge_clearance
    if lower_bound >= upper_bound:
        lower_bound = 0.0
        upper_bound = side

    best_candidate = (side * 0.5, side * 0.5)
    best_score = _candidate_geometry_score(
        existing,
        best_candidate,
        distance_threshold=threshold,
        height_threshold=height_threshold,
    )

    for _ in range(max(1, int(max_attempts))):
        candidate = (
            random.uniform(lower_bound, upper_bound),
            random.uniform(lower_bound, upper_bound),
        )
        score = _candidate_geometry_score(
            existing,
            candidate,
            distance_threshold=threshold,
            height_threshold=height_threshold,
        )
        if score > best_score:
            best_candidate = candidate
            best_score = score
        if score >= 1.0:
            return candidate

    return best_candidate


def _candidate_geometry_score(
    existing: list[tuple[float, float]],
    candidate: tuple[float, float],
    *,
    distance_threshold: float,
    height_threshold: float,
) -> float:
    scores: list[float] = []
    if existing:
        min_distance = min(_point_distance(candidate, other) for other in existing)
        scores.append(min_distance / distance_threshold)
    if len(existing) >= 2:
        min_height = math.inf
        for first_index, first in enumerate(existing):
            for second in existing[first_index + 1 :]:
                min_height = min(min_height, _triangle_height(first, second, candidate))
        scores.append(min_height / height_threshold)
    if not scores:
        return math.inf
    return min(scores)


def _point_distance(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _triangle_height(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> float:
    base = max(
        _point_distance(first, second),
        _point_distance(second, third),
        _point_distance(third, first),
    )
    if base <= 1e-12:
        return 0.0

    cross = abs(
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )
    return cross / base


def _edge_clearance_for_side(side: float) -> float:
    side = abs(float(side or 1.0)) or 1.0
    return min(20.0, side * 0.04)


def geometry_quality(
    pattern: cp.CreasePattern,
    *,
    min_vertex_distance_ratio: float = MIN_GENERIC_VERTEX_DISTANCE_RATIO,
) -> GeometryQuality:
    side = abs(float(pattern.side or 1.0)) or 1.0
    threshold = max(float(min_vertex_distance_ratio) * side, 1e-12)
    collinearity_threshold = max(float(MIN_GENERIC_COLLINEAR_HEIGHT_RATIO) * side, 1e-12)
    if len(pattern.vertices) < 2:
        return GeometryQuality(
            generic=True,
            min_vertex_distance=None,
            min_vertex_distance_ratio=None,
            min_triangle_height=None,
            min_triangle_height_ratio=None,
            threshold=threshold,
            closest_vertex_pair=None,
            most_collinear_triple=None,
            message="The sheet has fewer than two vertices, so it is not geometrically collapsed.",
        )

    min_distance = math.inf
    closest_pair: tuple[int, int] | None = None
    coords = [(float(vertex.x), float(vertex.y)) for vertex in pattern.vertices]
    for first_index, first in enumerate(coords):
        for second_index in range(first_index + 1, len(coords)):
            second = coords[second_index]
            distance = _point_distance(first, second)
            if distance < min_distance:
                min_distance = distance
                closest_pair = (first_index, second_index)

    min_ratio = min_distance / side
    min_triangle_height: float | None = None
    min_triangle_height_ratio: float | None = None
    most_collinear_triple: tuple[int, int, int] | None = None
    if len(coords) >= 3:
        min_triangle_height = math.inf
        for first_index, first in enumerate(coords):
            for second_index in range(first_index + 1, len(coords)):
                second = coords[second_index]
                for third_index in range(second_index + 1, len(coords)):
                    third = coords[third_index]
                    height = _triangle_height(first, second, third)
                    if height < min_triangle_height:
                        min_triangle_height = height
                        most_collinear_triple = (
                            first_index,
                            second_index,
                            third_index,
                        )
        min_triangle_height_ratio = min_triangle_height / side

    pair_generic = min_distance >= threshold
    triple_generic = (
        min_triangle_height is None or min_triangle_height >= collinearity_threshold
    )
    generic = pair_generic and triple_generic
    if generic:
        height_text = (
            ""
            if min_triangle_height is None
            else (
                f" The most collinear triple still keeps a height of {min_triangle_height:.3e}, "
                f"above the collinearity threshold of {collinearity_threshold:.3e}."
            )
        )
        message = (
            f"The closest vertices stay {min_distance:.3e} apart, above the generic-geometry threshold of {threshold:.3e}."
            f"{height_text}"
        )
    else:
        issues: list[str] = []
        if not pair_generic:
            pair_text = (
                f"vertices {closest_pair[0]} and {closest_pair[1]}"
                if closest_pair is not None
                else "two vertices"
            )
            issues.append(
                f"The closest pair ({pair_text}) is only {min_distance:.3e} apart, below the generic-geometry threshold of {threshold:.3e}."
            )
        if not triple_generic:
            triple_text = (
                f"vertices {most_collinear_triple[0]}, {most_collinear_triple[1]}, and {most_collinear_triple[2]}"
                if most_collinear_triple is not None
                else "three vertices"
            )
            issues.append(
                f"The most collinear triple ({triple_text}) has height {min_triangle_height:.3e}, below the collinearity threshold of {collinearity_threshold:.3e}."
            )
        message = " ".join(issues)
    return GeometryQuality(
        generic=generic,
        min_vertex_distance=min_distance,
        min_vertex_distance_ratio=min_ratio,
        min_triangle_height=min_triangle_height,
        min_triangle_height_ratio=min_triangle_height_ratio,
        threshold=threshold,
        closest_vertex_pair=closest_pair,
        most_collinear_triple=most_collinear_triple,
        message=message,
    )


def is_generic_geometry(
    pattern: cp.CreasePattern,
    *,
    min_vertex_distance_ratio: float = MIN_GENERIC_VERTEX_DISTANCE_RATIO,
) -> bool:
    return geometry_quality(
        pattern,
        min_vertex_distance_ratio=min_vertex_distance_ratio,
    ).generic


def clear_assignments(pattern: cp.CreasePattern) -> None:
    for fold in pattern.folds:
        fold.type = -1


def _vertex_mobility(pattern: cp.CreasePattern, index: int) -> int:
    vertex = pattern.vertices[index]
    if pattern.on_corner(vertex):
        return 0
    if pattern.on_edge(vertex):
        return 1
    return 2


def _fallback_unit_vector(seed: int) -> tuple[float, float]:
    angle = math.radians((seed * 137) % 360)
    return math.cos(angle), math.sin(angle)


def _candidate_clone_with_moves(
    pattern: cp.CreasePattern,
    moves: dict[int, tuple[float, float]],
    *,
    threshold: float,
) -> cp.CreasePattern:
    candidate = pattern.clone()
    side = abs(float(pattern.side or 1.0)) or 1.0
    clearance = min(max(threshold * 1.25, 1e-9), side / 4.0)
    lower_bound = clearance
    upper_bound = side - clearance
    if lower_bound >= upper_bound:
        lower_bound = 0.0
        upper_bound = side

    for index, (target_x, target_y) in moves.items():
        original = pattern.vertices[index]
        if pattern.on_corner(original):
            continue
        candidate.vertices[index].x = min(max(target_x, lower_bound), upper_bound)
        candidate.vertices[index].y = min(max(target_y, lower_bound), upper_bound)
    return candidate


def _pair_repair_moves(
    pattern: cp.CreasePattern,
    pair: tuple[int, int],
    *,
    threshold: float,
) -> list[dict[int, tuple[float, float]]]:
    first_index, second_index = pair
    first = pattern.vertices[first_index]
    second = pattern.vertices[second_index]
    dx = float(first.x - second.x)
    dy = float(first.y - second.y)
    distance = math.hypot(dx, dy)
    if distance <= 1e-12:
        dx, dy = _fallback_unit_vector(first_index * len(pattern.vertices) + second_index)
        distance = 1.0
    else:
        dx /= distance
        dy /= distance

    target_distance = max(threshold * 1.5, distance + threshold)
    needed_shift = max(target_distance - distance, threshold)
    first_weight = _vertex_mobility(pattern, first_index)
    second_weight = _vertex_mobility(pattern, second_index)
    candidates: list[dict[int, tuple[float, float]]] = []

    total_weight = first_weight + second_weight
    if total_weight > 0:
        candidates.append(
            {
                first_index: (
                    float(first.x) + dx * needed_shift * (first_weight / total_weight),
                    float(first.y) + dy * needed_shift * (first_weight / total_weight),
                ),
                second_index: (
                    float(second.x) - dx * needed_shift * (second_weight / total_weight),
                    float(second.y) - dy * needed_shift * (second_weight / total_weight),
                ),
            }
        )
    if first_weight > 0:
        candidates.append(
            {
                first_index: (
                    float(first.x) + dx * needed_shift,
                    float(first.y) + dy * needed_shift,
                )
            }
        )
    if second_weight > 0:
        candidates.append(
            {
                second_index: (
                    float(second.x) - dx * needed_shift,
                    float(second.y) - dy * needed_shift,
                )
            }
        )
    return candidates


def _triple_repair_moves(
    pattern: cp.CreasePattern,
    triple: tuple[int, int, int],
    *,
    threshold: float,
) -> list[dict[int, tuple[float, float]]]:
    side = abs(float(pattern.side or 1.0)) or 1.0
    center = (side * 0.5, side * 0.5)
    candidates: list[dict[int, tuple[float, float]]] = []

    ordered = sorted(triple, key=lambda index: _vertex_mobility(pattern, index), reverse=True)
    for moved_index in ordered:
        if _vertex_mobility(pattern, moved_index) <= 0:
            continue
        first_index, second_index = [index for index in triple if index != moved_index]
        first = pattern.vertices[first_index]
        second = pattern.vertices[second_index]
        moved = pattern.vertices[moved_index]
        base_dx = float(second.x - first.x)
        base_dy = float(second.y - first.y)
        base_length = math.hypot(base_dx, base_dy)
        if base_length <= 1e-12:
            continue

        normal_x = -base_dy / base_length
        normal_y = base_dx / base_length
        current_height = _triangle_height(
            (float(first.x), float(first.y)),
            (float(second.x), float(second.y)),
            (float(moved.x), float(moved.y)),
        )
        needed_shift = max(threshold * 1.5 - current_height, threshold)
        signed_area = (
            base_dx * (float(moved.y) - float(first.y))
            - base_dy * (float(moved.x) - float(first.x))
        )
        preferred_sign = 1.0 if signed_area > 0 else -1.0
        if abs(signed_area) <= 1e-12:
            toward_center = (
                normal_x * (center[0] - float(moved.x))
                + normal_y * (center[1] - float(moved.y))
            )
            preferred_sign = 1.0 if toward_center >= 0 else -1.0

        for sign in (preferred_sign, -preferred_sign):
            candidates.append(
                {
                    moved_index: (
                        float(moved.x) + normal_x * needed_shift * sign,
                        float(moved.y) + normal_y * needed_shift * sign,
                    )
                }
            )
    return candidates


def _repair_near_degenerate_geometry(
    pattern: cp.CreasePattern,
    quality: GeometryQuality,
) -> bool:
    if quality.generic:
        return False

    candidate_moves: list[dict[int, tuple[float, float]]] = []
    if (
        quality.closest_vertex_pair is not None
        and quality.min_vertex_distance is not None
        and quality.min_vertex_distance < quality.threshold
    ):
        candidate_moves.extend(
            _pair_repair_moves(
                pattern,
                quality.closest_vertex_pair,
                threshold=quality.threshold,
            )
        )
    if (
        quality.most_collinear_triple is not None
        and quality.min_triangle_height is not None
        and quality.min_triangle_height < quality.threshold
    ):
        candidate_moves.extend(
            _triple_repair_moves(
                pattern,
                quality.most_collinear_triple,
                threshold=quality.threshold,
            )
        )

    best_candidate: cp.CreasePattern | None = None
    best_quality = quality
    for moves in candidate_moves:
        candidate = _candidate_clone_with_moves(
            pattern,
            moves,
            threshold=quality.threshold,
        )
        candidate_quality = geometry_quality(candidate)
        if _geometry_score(candidate_quality) > _geometry_score(best_quality) + 1e-12:
            best_candidate = candidate
            best_quality = candidate_quality

    if best_candidate is None:
        return False

    for index, vertex in enumerate(best_candidate.vertices):
        pattern.vertices[index].x = vertex.x
        pattern.vertices[index].y = vertex.y
    return True


def _optimize_once_with_geometry_repairs(
    pattern: cp.CreasePattern,
    *,
    max_repair_attempts: int = DEFAULT_GEOMETRY_REPAIR_ATTEMPTS,
) -> tuple[object | None, int, float | None, GeometryQuality]:
    total_iterations = 0
    last_result = None
    last_loss: float | None = None
    quality = geometry_quality(pattern)

    for _ in range(max(1, int(max_repair_attempts))):
        last_result = pattern.optimize()
        total_iterations += int(getattr(last_result, "nit", 0) or 0)
        loss = getattr(last_result, "fun", None)
        last_loss = float(loss) if loss is not None else None
        clear_assignments(pattern)
        quality = geometry_quality(pattern)
        if quality.generic:
            break
        if not _repair_near_degenerate_geometry(pattern, quality):
            break

    quality = geometry_quality(pattern)
    return last_result, total_iterations, last_loss, quality


def optimize_pattern(
    pattern: cp.CreasePattern,
    *,
    rounds: int = 1,
) -> OptimizationSummary:
    rounds = max(1, int(rounds))
    total_iterations = 0
    last_loss: float | None = None
    last_result = None
    quality = geometry_quality(pattern)
    for _ in range(rounds):
        last_result, iterations, last_loss, quality = _optimize_once_with_geometry_repairs(
            pattern
        )
        total_iterations += iterations
    report = pattern.analyze_pattern()
    return OptimizationSummary(
        green=(report.local_status == cp.STATUS_PASS and quality.generic),
        rounds=rounds,
        iterations=total_iterations,
        loss=last_loss,
        last_result=last_result,
        geometry_quality=quality,
    )


def optimize_until_local_green(
    pattern: cp.CreasePattern,
    *,
    max_rounds: int,
) -> OptimizationSummary:
    max_rounds = max(1, int(max_rounds))
    report = pattern.analyze_pattern()
    quality = geometry_quality(pattern)
    if report.local_status == cp.STATUS_PASS and quality.generic:
        return OptimizationSummary(
            green=True,
            rounds=0,
            iterations=0,
            loss=None,
            geometry_quality=quality,
        )

    rounds = 0
    total_iterations = 0
    last_loss: float | None = None
    last_result = None
    while rounds < max_rounds:
        rounds += 1
        last_result, iterations, last_loss, quality = _optimize_once_with_geometry_repairs(
            pattern
        )
        total_iterations += iterations
        report = pattern.analyze_pattern()
        if report.local_status == cp.STATUS_PASS and quality.generic:
            break

    return OptimizationSummary(
        green=(report.local_status == cp.STATUS_PASS and quality.generic),
        rounds=rounds,
        iterations=total_iterations,
        loss=last_loss,
        last_result=last_result,
        geometry_quality=quality,
    )


def clone_pattern(pattern: cp.CreasePattern) -> cp.CreasePattern:
    return pattern.clone()


def edge_map(pattern: cp.CreasePattern) -> dict[tuple[int, int], cp.Fold]:
    vertex_index = {vertex: index for index, vertex in enumerate(pattern.vertices)}
    return {
        tuple(sorted((vertex_index[fold.v1], vertex_index[fold.v2]))): fold
        for fold in pattern.folds
    }


def same_connectivity(first: cp.CreasePattern, second: cp.CreasePattern) -> bool:
    if len(first.vertices) != len(second.vertices):
        return False
    if len(first.folds) != len(second.folds):
        return False
    return set(edge_map(first)) == set(edge_map(second))


def copy_fold_types(source: cp.CreasePattern, target: cp.CreasePattern) -> bool:
    if not same_connectivity(source, target):
        return False

    source_edges = edge_map(source)
    target_edges = edge_map(target)
    for edge_key, target_fold in target_edges.items():
        target_fold.type = source_edges[edge_key].type
    return True


def refresh_preview_reference(pattern: cp.CreasePattern) -> cp.CreasePattern | None:
    if not pattern.folds:
        return None
    candidate = pattern.clone()
    model, diagnostic = fold_sim.try_build_folded_figure(candidate)
    if model is None or diagnostic.status == cp.STATUS_FAIL:
        return None
    return candidate


def build_preview(
    pattern: cp.CreasePattern,
    *,
    preview_reference_pattern: cp.CreasePattern | None = None,
    allow_reference_fallback: bool = False,
    spatial_mode: bool = True,
) -> PreviewBuildResult:
    assignment = pattern.analyze_assignments()
    if not pattern.vertices or not pattern.folds or assignment.assigned_fold_count == 0:
        diagnostic = preview_not_run_diagnostic(pattern)
        return PreviewBuildResult(
            model=None,
            diagnostic=diagnostic,
            payload=None,
            solver="none",
            source="none",
            preview_reference_pattern=preview_reference_pattern,
        )

    failure_messages: list[str] = []
    candidates: list[tuple[str, str, cp.CreasePattern]] = [
        ("exact", "current", pattern.clone())
    ]
    if allow_reference_fallback and preview_reference_pattern is not None:
        reference_candidate = preview_reference_pattern.clone()
        if copy_fold_types(pattern, reference_candidate):
            candidates.append(("exact", "reference", reference_candidate))

    candidates.append(("mesh", "current", pattern.clone()))
    if allow_reference_fallback and preview_reference_pattern is not None:
        reference_candidate = preview_reference_pattern.clone()
        if copy_fold_types(pattern, reference_candidate):
            candidates.append(("mesh", "reference", reference_candidate))

    for solver_name, source_name, candidate in candidates:
        if solver_name == "exact":
            model, diagnostic = fold_sim.try_build_folded_figure(candidate)
            if model is None:
                failure_messages.append(diagnostic.message)
                continue
            if source_name == "reference":
                diagnostic = fold_sim.FoldSimulationDiagnostic(
                    status=cp.STATUS_WARNING,
                    face_count=diagnostic.face_count,
                    uses_provisional_signs=diagnostic.uses_provisional_signs,
                    uses_approximate_cycles=diagnostic.uses_approximate_cycles,
                    cycle_drift=diagnostic.cycle_drift,
                    crossing_fold_pairs=diagnostic.crossing_fold_pairs,
                    message="Exact preview succeeded only from the last stable reference geometry.",
                    preview_mode="exact",
                    used_reference_pattern=True,
                )
        else:
            try:
                model = fold_sim.build_approximate_folded_figure_with_mode(
                    candidate,
                    spatial_mode=spatial_mode,
                )
            except fold_sim.FoldSimulationError as exc:
                failure_messages.append(str(exc))
                continue
            diagnostic = fold_sim.FoldSimulationDiagnostic(
                status=cp.STATUS_WARNING,
                face_count=getattr(model, "face_count", None),
                uses_provisional_signs=model.uses_provisional_signs,
                uses_approximate_cycles=model.uses_approximate_cycles,
                cycle_drift=model.cycle_drift,
                crossing_fold_pairs=pattern.crossing_fold_pairs(),
                message=(
                    "Only a mesh fallback from the last stable reference geometry succeeded."
                    if source_name == "reference"
                    else "The exact face solver rejected this sheet, so the 3D preview uses a guarded mesh fallback."
                ),
                preview_mode="mesh",
                used_reference_pattern=(source_name == "reference"),
            )

        diagnostic = _with_preview_basis(diagnostic)
        reference_result = preview_reference_pattern
        if solver_name == "exact" and source_name == "current":
            reference_result = candidate.clone()

        return PreviewBuildResult(
            model=model,
            diagnostic=diagnostic,
            payload=_preview_payload(model, diagnostic),
            solver=solver_name,
            source=source_name,
            preview_reference_pattern=reference_result,
            failure_messages=tuple(failure_messages),
        )

    diagnostic = _with_preview_basis(
        fold_sim.FoldSimulationDiagnostic(
            status=cp.STATUS_FAIL,
            face_count=None,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            crossing_fold_pairs=pattern.crossing_fold_pairs(),
            message=(
                failure_messages[-1]
                if failure_messages
                else "The folded figure could not be constructed."
            ),
            preview_mode="none",
            used_reference_pattern=False,
        )
    )
    return PreviewBuildResult(
        model=None,
        diagnostic=diagnostic,
        payload=None,
        solver="none",
        source="none",
        preview_reference_pattern=preview_reference_pattern,
        failure_messages=tuple(failure_messages),
    )


def merge_report_with_preview(
    report: cp.PatternDiagnosticReport,
    preview: fold_sim.FoldSimulationDiagnostic,
) -> cp.PatternDiagnosticReport:
    prerequisite_failure = _global_failure_from_prerequisites(report)
    if prerequisite_failure is not None:
        global_status, global_message, basis, method, heuristic_reasons = prerequisite_failure
    elif preview.status != cp.STATUS_NOT_RUN:
        global_status = preview.status
        global_message = preview.message or report.global_diagnostic.message
        basis = preview.basis
        method = (
            "exact_face_reconstruction"
            if preview.preview_mode == "exact"
            else "mesh_fallback"
        )
        heuristic_reasons = preview.heuristic_reasons
    else:
        global_status = report.global_status
        global_message = report.global_diagnostic.message
        if report.global_status == cp.STATUS_NOT_RUN:
            basis = BASIS_NOT_RUN
            method = "not_run"
        else:
            basis = BASIS_LOCAL_ONLY
            method = "local_checks_only"
        heuristic_reasons = ()

    return cp.PatternDiagnosticReport(
        local_status=report.local_status,
        global_status=global_status,
        preview_status=preview.status,
        fold_assignment_status=report.fold_assignment_status,
        vertex_diagnostics=report.vertex_diagnostics,
        fold_assignment=report.fold_assignment,
        global_diagnostic=cp.GlobalDiagnostic(
            status=global_status,
            used_exact_faces=(preview.preview_mode == "exact"),
            used_reference_pattern=preview.used_reference_pattern,
            uses_provisional_signs=preview.uses_provisional_signs,
            uses_approximate_cycles=preview.uses_approximate_cycles,
            cycle_drift=preview.cycle_drift,
            crossing_fold_pairs=(
                preview.crossing_fold_pairs
                or report.global_diagnostic.crossing_fold_pairs
            ),
            face_count=preview.face_count,
            message=global_message,
            basis=basis,
            method=method,
            heuristic_reasons=heuristic_reasons,
        ),
        summary=(global_message,),
    )


def all_green(report: cp.PatternDiagnosticReport) -> bool:
    return all(
        status == cp.STATUS_PASS
        for status in (
            report.local_status,
            report.fold_assignment_status,
            report.global_status,
            report.preview_status,
        )
    )


def build_session_payload(
    pattern: cp.CreasePattern,
    *,
    point_count: int | str | None = None,
    preview_reference_pattern: cp.CreasePattern | None = None,
    fold_assignment_ready: bool = False,
    extra_state: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "format": "cp-generator-session",
        "version": 1,
        "point_count": "" if point_count is None else str(point_count),
        "fold_assignment_ready": bool(fold_assignment_ready),
        "pattern": pattern.to_data(),
        "preview_reference_pattern": (
            preview_reference_pattern.to_data()
            if preview_reference_pattern is not None
            else None
        ),
    }
    if extra_state:
        payload.update(
            {
                key: value
                for key, value in extra_state.items()
                if key not in RESERVED_SESSION_KEYS
            }
        )
    return payload


def restore_session_payload(payload: dict[str, object]) -> RestoredSession:
    if payload.get("format") != "cp-generator-session":
        raise ValueError("Unsupported session file format.")
    if payload.get("version") != 1:
        raise ValueError("Unsupported session file version.")

    pattern_data = payload.get("pattern")
    if not isinstance(pattern_data, dict):
        raise ValueError("Session file is missing crease-pattern data.")

    preview_reference_data = payload.get("preview_reference_pattern")
    extra_state = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "format",
            "version",
            "point_count",
            "fold_assignment_ready",
            "pattern",
            "preview_reference_pattern",
        }
    }

    return RestoredSession(
        pattern=cp.CreasePattern.from_data(pattern_data),
        point_count=str(payload.get("point_count", "")),
        preview_reference_pattern=(
            cp.CreasePattern.from_data(preview_reference_data)
            if isinstance(preview_reference_data, dict)
            else None
        ),
        fold_assignment_ready=bool(payload.get("fold_assignment_ready", False)),
        extra_state=extra_state,
    )


def snapshot_payload(
    pattern: cp.CreasePattern,
    *,
    status_title: str,
    status_message: str,
    note: str,
    status_tone: str | None = None,
    point_count: int | None = None,
    automation: dict[str, object] | None = None,
    preview_reference_pattern: cp.CreasePattern | None = None,
    allow_reference_fallback: bool = False,
    spatial_mode: bool = True,
    exact_check: object | None = None,
) -> dict[str, object]:
    preview = build_preview(
        pattern,
        preview_reference_pattern=preview_reference_pattern,
        allow_reference_fallback=allow_reference_fallback,
        spatial_mode=spatial_mode,
    )
    report = merge_report_with_preview(pattern.analyze_pattern(), preview.diagnostic)
    quality = geometry_quality(pattern)
    assignment = report.fold_assignment
    data_json = json.dumps(pattern.to_data(), separators=(",", ":"), sort_keys=True)

    payload: dict[str, object] = {
        "pattern_json": data_json,
        "title": "CP Generator",
        "subtitle": _subtitle(point_count),
        "summary": _summary_text(report, preview.diagnostic),
        "note": note,
        "point_count": point_count,
        "status": {
            "title": status_title,
            "message": status_message,
            "tone": (
                status_tone
                if status_tone is not None
                else _tone_for_status(_dominant_status(report))
            ),
        },
        "stats": {
            "vertices": len(pattern.vertices),
            "folds": len(pattern.folds),
            "interior_vertices": len(pattern.none_edge_vertices()),
            "assigned_folds": assignment.assigned_fold_count,
            "unassigned_folds": assignment.unassigned_fold_count,
            "face_count": preview.diagnostic.face_count,
        },
        "geometry": {
            "generic": quality.generic,
            "min_vertex_distance": quality.min_vertex_distance,
            "min_vertex_distance_ratio": quality.min_vertex_distance_ratio,
            "min_triangle_height": quality.min_triangle_height,
            "min_triangle_height_ratio": quality.min_triangle_height_ratio,
            "threshold": quality.threshold,
            "closest_vertex_pair": (
                list(quality.closest_vertex_pair)
                if quality.closest_vertex_pair is not None
                else None
            ),
            "most_collinear_triple": (
                list(quality.most_collinear_triple)
                if quality.most_collinear_triple is not None
                else None
            ),
            "message": quality.message,
        },
        "diagnostics": [
            {
                **_diagnostic_payload(
                    "local",
                    "Local",
                    report.local_status,
                    _local_message(report),
                ),
                "basis": BASIS_CERTIFIED,
                "method": "local_constraints",
            },
            {
                **_diagnostic_payload(
                    "assignment",
                    "Assignment",
                    report.fold_assignment_status,
                    _assignment_message(report),
                ),
                "basis": BASIS_CERTIFIED,
                "method": "maekawa_assignment",
            },
            {
                **_diagnostic_payload(
                    "global",
                    "Global",
                    report.global_status,
                    report.global_diagnostic.message,
                ),
                "basis": report.global_diagnostic.basis,
                "method": report.global_diagnostic.method,
                "heuristic_reasons": report.global_diagnostic.heuristic_reasons,
            },
            {
                **_diagnostic_payload(
                    "preview",
                    "Preview",
                    report.preview_status,
                    preview.diagnostic.message,
                ),
                "basis": preview.diagnostic.basis,
                "method": preview.diagnostic.preview_mode,
                "heuristic_reasons": preview.diagnostic.heuristic_reasons,
            },
        ],
        "stage": _stage_payload(pattern),
        "preview": preview.payload,
        "automation": automation,
        "preview_ready": preview.model is not None,
    }
    if exact_check is not None:
        payload["exact_checker"] = {
            "status": getattr(exact_check, "status", cp.STATUS_NOT_RUN),
            "message": getattr(exact_check, "message", ""),
            "face_count": getattr(exact_check, "face_count", None),
            "overlap_pair_count": getattr(exact_check, "overlap_pair_count", None),
            "total_orders_checked": getattr(exact_check, "total_orders_checked", 0),
            "unique_order": getattr(exact_check, "unique_order", None),
        }
    return payload


def snapshot_json(**kwargs) -> str:
    return json.dumps(
        snapshot_payload(**kwargs),
        separators=(",", ":"),
        sort_keys=True,
    )


def _geometry_score(quality: GeometryQuality | None) -> float:
    if quality is None:
        return -math.inf
    scores: list[float] = []
    if quality.min_vertex_distance is not None:
        scores.append(quality.min_vertex_distance / quality.threshold)
    if quality.min_triangle_height is not None:
        scores.append(quality.min_triangle_height / quality.threshold)
    if not scores:
        return math.inf
    return min(scores)


def _global_failure_from_prerequisites(
    report: cp.PatternDiagnosticReport,
) -> tuple[str, str, str, str, tuple[str, ...]] | None:
    if report.local_status == cp.STATUS_FAIL:
        message = (
            report.summary[0]
            if report.summary
            else "At least one interior vertex fails a local flat-fold condition."
        )
        return (
            cp.STATUS_FAIL,
            message,
            BASIS_CERTIFIED,
            "local_constraints",
            (),
        )
    if report.fold_assignment_status == cp.STATUS_FAIL:
        message = (
            report.summary[0]
            if report.summary
            else "Assigned folds violate Maekawa at an interior vertex."
        )
        return (
            cp.STATUS_FAIL,
            message,
            BASIS_CERTIFIED,
            "maekawa_assignment",
            (),
        )
    if report.global_status == cp.STATUS_FAIL:
        return (
            cp.STATUS_FAIL,
            report.global_diagnostic.message,
            BASIS_CERTIFIED,
            "crossing_detection",
            (),
        )
    return None


def preview_not_run_diagnostic(
    pattern: cp.CreasePattern,
) -> fold_sim.FoldSimulationDiagnostic:
    assignment = pattern.analyze_assignments()
    if not pattern.vertices:
        message = "Generate a crease pattern to open the folded figure."
    elif not pattern.folds:
        message = "This sheet has no interior folds to animate."
    elif assignment.assigned_fold_count == 0:
        message = "Assign mountain and valley folds to unlock the folded figure."
    else:
        message = "Rebuild the folded figure to refresh preview diagnostics."

    return _with_preview_basis(
        fold_sim.FoldSimulationDiagnostic(
            status=cp.STATUS_NOT_RUN,
            face_count=None,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            crossing_fold_pairs=(),
            message=message,
            preview_mode="none",
            used_reference_pattern=False,
        )
    )


def _with_preview_basis(
    diagnostic: fold_sim.FoldSimulationDiagnostic,
) -> fold_sim.FoldSimulationDiagnostic:
    if diagnostic.status == cp.STATUS_NOT_RUN:
        return fold_sim.with_basis(diagnostic, basis=BASIS_NOT_RUN)

    heuristic_reasons: list[str] = []
    if diagnostic.preview_mode == "mesh":
        heuristic_reasons.append("mesh_fallback")
    if diagnostic.used_reference_pattern:
        heuristic_reasons.append("reference_geometry")
    if diagnostic.uses_provisional_signs:
        heuristic_reasons.append("provisional_signs")
    if diagnostic.uses_approximate_cycles:
        heuristic_reasons.append("approximate_cycle_closure")

    if heuristic_reasons:
        return fold_sim.with_basis(
            diagnostic,
            basis=BASIS_HEURISTIC,
            heuristic_reasons=tuple(heuristic_reasons),
        )
    if diagnostic.preview_mode == "exact":
        return fold_sim.with_basis(diagnostic, basis=BASIS_CERTIFIED)
    if diagnostic.status == cp.STATUS_FAIL:
        return fold_sim.with_basis(diagnostic, basis=BASIS_UNKNOWN)
    return fold_sim.with_basis(diagnostic, basis=BASIS_HEURISTIC)


def packaged_corpus_root() -> Traversable:
    return files("cp_generator") / "data" / "corpus"


def _preview_payload(
    model: fold_sim.FoldedFigureModel | fold_sim.ApproximateFoldedFigureModel,
    diagnostic: fold_sim.FoldSimulationDiagnostic,
) -> dict[str, object]:
    frames = []
    all_points = []
    for step in range(PREVIEW_FRAME_COUNT):
        progress = 0.0 if PREVIEW_FRAME_COUNT == 1 else step / (PREVIEW_FRAME_COUNT - 1)
        states = model.frame(progress)
        faces = []
        for state in states:
            points = [
                {
                    "x": float(point[0]),
                    "y": float(point[1]),
                    "z": float(point[2]) if len(point) > 2 else 0.0,
                }
                for point in state.points
            ]
            all_points.extend(points)
            faces.append(
                {
                    "index": int(state.index),
                    "points": points,
                    "top_surface": bool(state.top_surface),
                }
            )
        frames.append(
            {
                "progress": float(progress),
                "faces": faces,
            }
        )

    if all_points:
        min_x = min(point["x"] for point in all_points)
        max_x = max(point["x"] for point in all_points)
        min_y = min(point["y"] for point in all_points)
        max_y = max(point["y"] for point in all_points)
        min_z = min(point["z"] for point in all_points)
        max_z = max(point["z"] for point in all_points)
    else:
        min_x = max_x = min_y = max_y = min_z = max_z = 0.0

    return {
        "mode": diagnostic.preview_mode,
        "message": diagnostic.message,
        "face_count": diagnostic.face_count,
        "uses_provisional_signs": diagnostic.uses_provisional_signs,
        "uses_approximate_cycles": diagnostic.uses_approximate_cycles,
        "cycle_drift": diagnostic.cycle_drift,
        "is_mesh_approximation": bool(getattr(model, "is_mesh_approximation", False)),
        "basis": diagnostic.basis,
        "heuristic_reasons": diagnostic.heuristic_reasons,
        "frames": frames,
        "bounds": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "min_z": min_z,
            "max_z": max_z,
        },
    }


def _stage_payload(pattern: cp.CreasePattern) -> dict[str, object]:
    side = float(pattern.side or 1.0)
    if side <= 0:
        side = 1.0
    vertex_index = {vertex: index for index, vertex in enumerate(pattern.vertices)}
    ordered_folds = sorted(
        pattern.folds,
        key=lambda fold: tuple(sorted((vertex_index[fold.v1], vertex_index[fold.v2]))),
    )
    folds = [
        {
            "x1": float(fold.v1.x) / side,
            "y1": float(fold.v1.y) / side,
            "x2": float(fold.v2.x) / side,
            "y2": float(fold.v2.y) / side,
            "type": int(fold.type),
        }
        for fold in ordered_folds
    ]
    vertices = [
        {
            "x": float(vertex.x) / side,
            "y": float(vertex.y) / side,
            "on_edge": pattern.on_edge(vertex),
        }
        for vertex in pattern.vertices
    ]
    return {
        "boundary": (
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
            {"x": 1.0, "y": 1.0},
            {"x": 0.0, "y": 1.0},
        ),
        "folds": folds,
        "vertices": vertices,
    }


def _diagnostic_payload(
    key: str,
    label: str,
    status: str,
    message: str,
) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "message": message,
        "tone": _tone_for_status(status),
    }


def _subtitle(point_count: int | None) -> str:
    if point_count is None:
        return "Mobile crease studio"
    return f"{point_count}-point random study"


def _summary_text(
    report: cp.PatternDiagnosticReport,
    preview: fold_sim.FoldSimulationDiagnostic,
) -> str:
    if report.summary:
        return report.summary[0]
    return preview.message


def _dominant_status(report: cp.PatternDiagnosticReport) -> str:
    statuses = (
        report.preview_status,
        report.global_status,
        report.fold_assignment_status,
        report.local_status,
    )
    if cp.STATUS_FAIL in statuses:
        return cp.STATUS_FAIL
    if cp.STATUS_WARNING in statuses:
        return cp.STATUS_WARNING
    if cp.STATUS_PASS in statuses:
        return cp.STATUS_PASS
    return cp.STATUS_NOT_RUN


def _tone_for_status(status: str) -> str:
    if status == cp.STATUS_PASS:
        return "success"
    if status == cp.STATUS_WARNING:
        return "warning"
    if status == cp.STATUS_FAIL:
        return "danger"
    return "neutral"


def _local_message(report: cp.PatternDiagnosticReport) -> str:
    failing = [
        item
        for item in report.vertex_diagnostics
        if (not item.on_edge) and ((not item.even_degree_ok) or (not item.kawasaki_ok))
    ]
    if not failing:
        return "Interior vertices satisfy even-degree and Kawasaki checks."
    first = failing[0]
    return f"Vertex {first.vertex_index} fails a local flat-fold condition."


def _assignment_message(report: cp.PatternDiagnosticReport) -> str:
    assignment = report.fold_assignment
    if assignment.assigned_fold_count == 0:
        return "No mountain and valley assignment has been applied yet."
    if assignment.maekawa_failures:
        return f"Assigned folds violate Maekawa at vertex {assignment.maekawa_failures[0]}."
    if assignment.underdetermined:
        return "Some folds remain intentionally underdetermined."
    return "Assigned folds satisfy the current local Maekawa checks."
