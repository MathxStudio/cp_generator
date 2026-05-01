from __future__ import annotations

import json

from . import core as cp
from . import fold_sim
from .samples import box_head as box_head_sample


MODEL_SIDE = 500


def build_random_pattern(point_count: int) -> str:
    point_count = max(0, int(point_count))
    pattern = _build_pattern(point_count)
    return _snapshot(
        pattern,
        point_count=point_count,
        status_title="Fresh sheet",
        status_message=f"Generated a crease pattern with {point_count} random interior points.",
        note="Refine the geometry for cleaner local constraints, then assign mountain and valley folds to test foldability.",
    )


def optimize_pattern(pattern_json: str, rounds: int = 1) -> str:
    pattern = cp.CreasePattern.from_data(json.loads(pattern_json))
    rounds = max(1, int(rounds))
    total_iterations = 0
    last_loss = None
    for _ in range(rounds):
        result = pattern.optimize()
        total_iterations += int(getattr(result, "nit", 0) or 0)
        loss = getattr(result, "fun", None)
        last_loss = float(loss) if loss is not None else None
        _clear_assignments(pattern)

    loss_text = "unknown" if last_loss is None else f"{last_loss:.3e}"
    return _snapshot(
        pattern,
        status_title="Refined",
        status_message=f"Optimization ran for {rounds} round{'s' if rounds != 1 else ''} and {total_iterations} total iterations.",
        note=f"The geometry was normalized for flatter local angles. Last loss: {loss_text}. Assign folds again after each refinement pass.",
    )


def assign_pattern(pattern_json: str) -> str:
    pattern = cp.CreasePattern.from_data(json.loads(pattern_json))
    result = pattern.assign_mv()
    if result.success:
        return _snapshot(
            pattern,
            status_title="Assigned",
            status_message="Mountain and valley folds were assigned successfully.",
            note=result.message,
        )
    return _snapshot(
        pattern,
        status_title="No assignment",
        status_message="No locally admissible mountain and valley assignment was found.",
        note=result.message,
    )


def load_box_head() -> str:
    pattern = box_head_sample.build_box_head_pattern()
    return _snapshot(
        pattern,
        point_count=None,
        status_title="Box Head sample",
        status_message="Loaded the authored 16x16 sample crease pattern.",
        note="This sample already includes mountain and valley assignments and is ready for inspection immediately.",
        sample_key=box_head_sample.BOX_HEAD_KEY,
    )


def _build_pattern(point_count: int) -> cp.CreasePattern:
    pattern = cp.CreasePattern()
    pattern.side = MODEL_SIDE
    pattern.add_square_vertices()
    for _ in range(point_count):
        pattern.add_random_vertex()
    pattern.push_to_edge(20)
    pattern.triangulate()
    pattern.evenize_vertices()
    pattern.remove_edge_folds()
    return pattern


def _clear_assignments(pattern: cp.CreasePattern) -> None:
    for fold in pattern.folds:
        fold.type = -1


def _snapshot(
    pattern: cp.CreasePattern,
    *,
    status_title: str,
    status_message: str,
    note: str,
    point_count: int | None = None,
    sample_key: str | None = None,
) -> str:
    report = pattern.analyze_pattern()
    preview = _preview_diagnostic(pattern, sample_key=sample_key)
    assignment = report.fold_assignment
    data_json = json.dumps(pattern.to_data(), separators=(",", ":"), sort_keys=True)

    payload = {
        "pattern_json": data_json,
        "title": "CP Generator",
        "subtitle": _subtitle(sample_key, point_count),
        "summary": report.summary[0] if report.summary else preview.message,
        "note": note,
        "point_count": point_count,
        "sample_key": sample_key,
        "status": {
            "title": status_title,
            "message": status_message,
            "tone": _tone_for_status(_dominant_status(report, preview)),
        },
        "stats": {
            "vertices": len(pattern.vertices),
            "folds": len(pattern.folds),
            "interior_vertices": len(pattern.none_edge_vertices()),
            "assigned_folds": assignment.assigned_fold_count,
            "unassigned_folds": assignment.unassigned_fold_count,
            "face_count": preview.face_count,
        },
        "diagnostics": [
            _diagnostic_payload(
                "local",
                "Local",
                report.local_status,
                _local_message(report),
            ),
            _diagnostic_payload(
                "assignment",
                "Assignment",
                report.fold_assignment_status,
                _assignment_message(report),
            ),
            _diagnostic_payload(
                "global",
                "Global",
                report.global_status,
                report.global_diagnostic.message,
            ),
            _diagnostic_payload(
                "preview",
                "Preview",
                preview.status,
                preview.message,
            ),
        ],
        "stage": _stage_payload(pattern),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _preview_diagnostic(
    pattern: cp.CreasePattern,
    *,
    sample_key: str | None = None,
) -> fold_sim.FoldSimulationDiagnostic:
    if sample_key == box_head_sample.BOX_HEAD_KEY:
        return fold_sim.FoldSimulationDiagnostic(
            status=cp.STATUS_PASS,
            face_count=None,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            crossing_fold_pairs=(),
            message="The authored sample is preassigned and ready for crease inspection in the mobile layout.",
            preview_mode="none",
            used_reference_pattern=False,
        )
    assignment = pattern.analyze_assignments()
    if not pattern.vertices:
        return fold_sim.FoldSimulationDiagnostic(
            status=cp.STATUS_NOT_RUN,
            face_count=None,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            crossing_fold_pairs=(),
            message="Generate a crease pattern to open the folded figure.",
            preview_mode="none",
            used_reference_pattern=False,
        )
    if not pattern.folds:
        return fold_sim.FoldSimulationDiagnostic(
            status=cp.STATUS_NOT_RUN,
            face_count=None,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            crossing_fold_pairs=(),
            message="This sheet has no interior folds to animate.",
            preview_mode="none",
            used_reference_pattern=False,
        )
    if assignment.assigned_fold_count == 0:
        return fold_sim.FoldSimulationDiagnostic(
            status=cp.STATUS_NOT_RUN,
            face_count=None,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            crossing_fold_pairs=(),
            message="Assign mountain and valley folds to unlock the folded figure.",
            preview_mode="none",
            used_reference_pattern=False,
        )
    return fold_sim.analyze_foldability(pattern.clone())


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


def _subtitle(sample_key: str | None, point_count: int | None) -> str:
    if sample_key == box_head_sample.BOX_HEAD_KEY:
        return "Authored reference sample"
    if point_count is None:
        return "Mobile crease studio"
    return f"{point_count}-point random study"


def _dominant_status(
    report: cp.PatternDiagnosticReport,
    preview: fold_sim.FoldSimulationDiagnostic,
) -> str:
    statuses = (
        preview.status,
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
