from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
import json
import math

from . import core as cp
from . import fold_sim


MODEL_SIDE = 500
PREVIEW_FRAME_COUNT = 13
DEFAULT_BUILD_PATTERN_ATTEMPTS = 16
MIN_GENERIC_VERTEX_DISTANCE_RATIO = 1e-3

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
    threshold: float
    closest_vertex_pair: tuple[int, int] | None = None
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
    for _ in range(point_count):
        pattern.add_random_vertex()
    pattern.push_to_edge(20)
    pattern.triangulate()
    pattern.evenize_vertices()
    pattern.remove_edge_folds()
    return pattern


def geometry_quality(
    pattern: cp.CreasePattern,
    *,
    min_vertex_distance_ratio: float = MIN_GENERIC_VERTEX_DISTANCE_RATIO,
) -> GeometryQuality:
    side = abs(float(pattern.side or 1.0)) or 1.0
    threshold = max(float(min_vertex_distance_ratio) * side, 1e-12)
    if len(pattern.vertices) < 2:
        return GeometryQuality(
            generic=True,
            min_vertex_distance=None,
            min_vertex_distance_ratio=None,
            threshold=threshold,
            closest_vertex_pair=None,
            message="The sheet has fewer than two vertices, so it is not geometrically collapsed.",
        )

    min_distance = math.inf
    closest_pair: tuple[int, int] | None = None
    for first_index, first in enumerate(pattern.vertices):
        for second_index in range(first_index + 1, len(pattern.vertices)):
            second = pattern.vertices[second_index]
            distance = math.hypot(first.x - second.x, first.y - second.y)
            if distance < min_distance:
                min_distance = distance
                closest_pair = (first_index, second_index)

    min_ratio = min_distance / side
    generic = min_distance >= threshold
    if generic:
        message = (
            f"The closest vertices stay {min_distance:.3e} apart, above the generic-geometry threshold of {threshold:.3e}."
        )
    else:
        pair_text = (
            f"vertices {closest_pair[0]} and {closest_pair[1]}"
            if closest_pair is not None
            else "two vertices"
        )
        message = (
            f"The closest pair ({pair_text}) is only {min_distance:.3e} apart, below the generic-geometry threshold of {threshold:.3e}."
        )
    return GeometryQuality(
        generic=generic,
        min_vertex_distance=min_distance,
        min_vertex_distance_ratio=min_ratio,
        threshold=threshold,
        closest_vertex_pair=closest_pair,
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


def optimize_pattern(
    pattern: cp.CreasePattern,
    *,
    rounds: int = 1,
) -> OptimizationSummary:
    rounds = max(1, int(rounds))
    total_iterations = 0
    last_loss: float | None = None
    last_result = None
    for _ in range(rounds):
        last_result = pattern.optimize()
        total_iterations += int(getattr(last_result, "nit", 0) or 0)
        loss = getattr(last_result, "fun", None)
        last_loss = float(loss) if loss is not None else None
        clear_assignments(pattern)
    report = pattern.analyze_pattern()
    quality = geometry_quality(pattern)
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
        last_result = pattern.optimize()
        total_iterations += int(getattr(last_result, "nit", 0) or 0)
        loss = getattr(last_result, "fun", None)
        last_loss = float(loss) if loss is not None else None
        clear_assignments(pattern)
        report = pattern.analyze_pattern()
        quality = geometry_quality(pattern)
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
            "threshold": quality.threshold,
            "closest_vertex_pair": (
                list(quality.closest_vertex_pair)
                if quality.closest_vertex_pair is not None
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
    if quality.min_vertex_distance is None:
        return math.inf
    return quality.min_vertex_distance


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
