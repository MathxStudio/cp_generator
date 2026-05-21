from __future__ import annotations

import json

from . import core as cp
from . import fold_sim


MODEL_SIDE = 500
PREVIEW_FRAME_COUNT = 13


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


def optimize_until_local_green(pattern_json: str, max_rounds: int = 8) -> str:
    pattern = cp.CreasePattern.from_data(json.loads(pattern_json))
    result = _optimize_until_local_green(pattern, max_rounds=max_rounds)
    if result["green"]:
        title = "Local green"
        message = f"Local flat-fold checks passed after {result['rounds']} optimization round{'s' if result['rounds'] != 1 else ''}."
        note = "The sheet is locally valid. Assign mountain and valley folds next to continue toward a full foldability check."
    else:
        title = "Needs work"
        message = f"Stopped after {result['rounds']} optimization round{'s' if result['rounds'] != 1 else ''} without a green local badge."
        note = "The geometry improved, but at least one interior vertex still fails an even-degree or Kawasaki check."
    return _snapshot(
        pattern,
        point_count=None,
        status_title=title,
        status_message=message,
        note=note,
        automation={
            "kind": "local_green",
            "found": bool(result["green"]),
            "attempts": 1,
            "max_attempts": 1,
            "rounds": int(result["rounds"]),
            "max_rounds": max(1, int(max_rounds)),
            "iterations": int(result["iterations"]),
            "loss": result["loss"],
        },
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


def auto_all_green(
    point_count: int,
    max_attempts: int = 16,
    max_local_rounds: int = 8,
) -> str:
    point_count = max(0, int(point_count))
    max_attempts = max(1, int(max_attempts))
    max_local_rounds = max(1, int(max_local_rounds))

    winning_pattern: cp.CreasePattern | None = None
    winning_attempt = 0
    last_assignment_message = "No search attempt was executed."
    last_optimize = {
        "green": False,
        "rounds": 0,
        "iterations": 0,
        "loss": None,
    }
    last_preview_message = "No folded figure was evaluated yet."

    for attempt in range(1, max_attempts + 1):
        pattern = _build_pattern(point_count)
        optimize_result = _optimize_until_local_green(pattern, max_rounds=max_local_rounds)
        assign_result = pattern.assign_mv()
        last_assignment_message = assign_result.message

        report = pattern.analyze_pattern()
        _, preview_diagnostic, _ = _build_preview(pattern)
        merged = _merge_report_with_preview(report, preview_diagnostic)
        last_optimize = optimize_result
        last_preview_message = preview_diagnostic.message

        if _all_green(merged):
            winning_pattern = pattern
            winning_attempt = attempt
            break

        winning_pattern = pattern
        winning_attempt = attempt

    if winning_pattern is None:
        winning_pattern = _build_pattern(point_count)

    report = winning_pattern.analyze_pattern()
    _, preview_diagnostic, _ = _build_preview(winning_pattern)
    merged = _merge_report_with_preview(report, preview_diagnostic)
    found = _all_green(merged)

    if found:
        status_title = "All green"
        status_message = f"Found a fully green sheet on attempt {winning_attempt}."
        note = (
            f"Local, assignment, global, and preview diagnostics all passed. "
            f"The last search used {last_optimize['rounds']} local optimization round"
            f"{'s' if last_optimize['rounds'] != 1 else ''}."
        )
    else:
        status_title = "Search stopped"
        status_message = f"Checked {winning_attempt} random sheet{'s' if winning_attempt != 1 else ''} without finding an all-green result."
        note = f"{last_assignment_message} {last_preview_message}"

    return _snapshot(
        winning_pattern,
        point_count=point_count,
        status_title=status_title,
        status_message=status_message,
        note=note,
        automation={
            "kind": "all_green",
            "found": found,
            "attempts": winning_attempt,
            "max_attempts": max_attempts,
            "rounds": int(last_optimize["rounds"]),
            "max_rounds": max_local_rounds,
            "iterations": int(last_optimize["iterations"]),
            "loss": last_optimize["loss"],
        },
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


def _optimize_until_local_green(
    pattern: cp.CreasePattern,
    *,
    max_rounds: int,
) -> dict[str, object]:
    max_rounds = max(1, int(max_rounds))
    report = pattern.analyze_pattern()
    if report.local_status == cp.STATUS_PASS:
        return {
            "green": True,
            "rounds": 0,
            "iterations": 0,
            "loss": None,
        }

    rounds = 0
    total_iterations = 0
    last_loss: float | None = None
    while rounds < max_rounds:
        rounds += 1
        result = pattern.optimize()
        total_iterations += int(getattr(result, "nit", 0) or 0)
        loss = getattr(result, "fun", None)
        last_loss = float(loss) if loss is not None else None
        _clear_assignments(pattern)
        report = pattern.analyze_pattern()
        if report.local_status == cp.STATUS_PASS:
            break

    return {
        "green": report.local_status == cp.STATUS_PASS,
        "rounds": rounds,
        "iterations": total_iterations,
        "loss": last_loss,
    }


def _snapshot(
    pattern: cp.CreasePattern,
    *,
    status_title: str,
    status_message: str,
    note: str,
    point_count: int | None = None,
    automation: dict[str, object] | None = None,
) -> str:
    report = pattern.analyze_pattern()
    preview_model, preview_diagnostic, preview_payload = _build_preview(pattern)
    merged = _merge_report_with_preview(report, preview_diagnostic)
    assignment = merged.fold_assignment
    data_json = json.dumps(pattern.to_data(), separators=(",", ":"), sort_keys=True)

    payload = {
        "pattern_json": data_json,
        "title": "CP Generator",
        "subtitle": _subtitle(point_count),
        "summary": _summary_text(merged, preview_diagnostic),
        "note": note,
        "point_count": point_count,
        "status": {
            "title": status_title,
            "message": status_message,
            "tone": _tone_for_status(_dominant_status(merged)),
        },
        "stats": {
            "vertices": len(pattern.vertices),
            "folds": len(pattern.folds),
            "interior_vertices": len(pattern.none_edge_vertices()),
            "assigned_folds": assignment.assigned_fold_count,
            "unassigned_folds": assignment.unassigned_fold_count,
            "face_count": preview_diagnostic.face_count,
        },
        "diagnostics": [
            _diagnostic_payload(
                "local",
                "Local",
                merged.local_status,
                _local_message(merged),
            ),
            _diagnostic_payload(
                "assignment",
                "Assignment",
                merged.fold_assignment_status,
                _assignment_message(merged),
            ),
            _diagnostic_payload(
                "global",
                "Global",
                merged.global_status,
                merged.global_diagnostic.message,
            ),
            _diagnostic_payload(
                "preview",
                "Preview",
                merged.preview_status,
                preview_diagnostic.message,
            ),
        ],
        "stage": _stage_payload(pattern),
        "preview": preview_payload,
        "automation": automation,
        "preview_ready": preview_model is not None,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _build_preview(
    pattern: cp.CreasePattern,
) -> tuple[
    fold_sim.FoldedFigureModel | fold_sim.ApproximateFoldedFigureModel | None,
    fold_sim.FoldSimulationDiagnostic,
    dict[str, object] | None,
]:
    assignment = pattern.analyze_assignments()
    if not pattern.vertices:
        diagnostic = fold_sim.FoldSimulationDiagnostic(
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
        return None, diagnostic, None

    if not pattern.folds:
        diagnostic = fold_sim.FoldSimulationDiagnostic(
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
        return None, diagnostic, None

    if assignment.assigned_fold_count == 0:
        diagnostic = fold_sim.FoldSimulationDiagnostic(
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
        return None, diagnostic, None

    exact_model, exact_diagnostic = fold_sim.try_build_folded_figure(pattern.clone())
    if exact_model is not None:
        return exact_model, exact_diagnostic, _preview_payload(exact_model, exact_diagnostic)

    try:
        mesh_model = fold_sim.build_approximate_folded_figure_with_mode(
            pattern.clone(),
            spatial_mode=True,
        )
    except fold_sim.FoldSimulationError as exc:
        diagnostic = fold_sim.FoldSimulationDiagnostic(
            status=cp.STATUS_FAIL,
            face_count=None,
            uses_provisional_signs=False,
            uses_approximate_cycles=False,
            cycle_drift=None,
            crossing_fold_pairs=pattern.crossing_fold_pairs(),
            message=f"{exact_diagnostic.message} Mesh fallback also failed: {exc}",
            preview_mode="none",
            used_reference_pattern=False,
        )
        return None, diagnostic, None

    mesh_diagnostic = fold_sim.FoldSimulationDiagnostic(
        status=cp.STATUS_WARNING,
        face_count=getattr(mesh_model, "face_count", None),
        uses_provisional_signs=mesh_model.uses_provisional_signs,
        uses_approximate_cycles=mesh_model.uses_approximate_cycles,
        cycle_drift=mesh_model.cycle_drift,
        crossing_fold_pairs=pattern.crossing_fold_pairs(),
        message="The exact face solver rejected this sheet, so the 3D preview uses a guarded mesh fallback.",
        preview_mode="mesh",
        used_reference_pattern=False,
    )
    return mesh_model, mesh_diagnostic, _preview_payload(mesh_model, mesh_diagnostic)


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


def _merge_report_with_preview(
    report: cp.PatternDiagnosticReport,
    preview: fold_sim.FoldSimulationDiagnostic,
) -> cp.PatternDiagnosticReport:
    global_status = report.global_status
    global_message = report.global_diagnostic.message
    if preview.status != cp.STATUS_NOT_RUN:
        global_message = preview.message or global_message
        if global_status != cp.STATUS_FAIL:
            global_status = preview.status

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
            crossing_fold_pairs=preview.crossing_fold_pairs or report.global_diagnostic.crossing_fold_pairs,
            face_count=preview.face_count,
            message=global_message,
        ),
        summary=report.summary,
    )


def _all_green(report: cp.PatternDiagnosticReport) -> bool:
    return all(
        status == cp.STATUS_PASS
        for status in (
            report.local_status,
            report.fold_assignment_status,
            report.global_status,
            report.preview_status,
        )
    )


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
