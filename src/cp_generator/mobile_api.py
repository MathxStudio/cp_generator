from __future__ import annotations

import json

from . import core as cp
from . import workflow


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
        status_tone="neutral",
    )


def optimize_pattern(pattern_json: str, rounds: int = 1) -> str:
    pattern = cp.CreasePattern.from_data(json.loads(pattern_json))
    result = workflow.optimize_pattern(pattern, rounds=rounds)
    loss_text = "unknown" if result.loss is None else f"{result.loss:.3e}"
    return _snapshot(
        pattern,
        status_title="Refined",
        status_message=f"Optimization ran for {result.rounds} round{'s' if result.rounds != 1 else ''} and {result.iterations} total iterations.",
        note=f"The geometry was normalized for flatter local angles. Last loss: {loss_text}. Assign folds again after each refinement pass.",
        status_tone="neutral",
    )


def optimize_until_local_green(pattern_json: str, max_rounds: int = 8) -> str:
    pattern = cp.CreasePattern.from_data(json.loads(pattern_json))
    result = _optimize_until_local_green(pattern, max_rounds=max_rounds)
    if result["green"]:
        title = "Local green"
        message = f"Local flat-fold checks passed after {result['rounds']} optimization round{'s' if result['rounds'] != 1 else ''}."
        note = "The sheet is locally valid. Assign mountain and valley folds next to continue toward a full foldability check."
        tone = "success"
    elif pattern.analyze_pattern().local_status == cp.STATUS_PASS:
        title = "Near-degenerate"
        message = (
            f"Local flat-fold checks passed after {result['rounds']} optimization round{'s' if result['rounds'] != 1 else ''}, "
            "but the sheet stayed too collapsed to accept."
        )
        note = result["geometry_message"]
        tone = "warning"
    else:
        title = "Needs work"
        message = f"Stopped after {result['rounds']} optimization round{'s' if result['rounds'] != 1 else ''} without a green local badge."
        note = "The geometry improved, but at least one interior vertex still fails an even-degree or Kawasaki check."
        tone = "warning"
    return _snapshot(
        pattern,
        point_count=None,
        status_title=title,
        status_message=message,
        note=note,
        status_tone=tone,
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
            status_tone="success",
        )
    return _snapshot(
        pattern,
        status_title="No assignment",
        status_message="No locally admissible mountain and valley assignment was found.",
        note=result.message,
        status_tone="danger",
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
    last_optimize = _optimization_dict(
        workflow.OptimizationSummary(
            green=False,
            rounds=0,
            iterations=0,
            loss=None,
        )
    )
    last_preview_message = "No folded figure was evaluated yet."
    last_geometry_message = ""

    for attempt in range(1, max_attempts + 1):
        pattern = _build_pattern(point_count)
        optimize_result = _optimize_until_local_green(pattern, max_rounds=max_local_rounds)
        assign_result = pattern.assign_mv()
        last_assignment_message = assign_result.message

        report = pattern.analyze_pattern()
        preview = workflow.build_preview(pattern, spatial_mode=True)
        merged = workflow.merge_report_with_preview(report, preview.diagnostic)
        quality = workflow.geometry_quality(pattern)
        last_optimize = optimize_result
        last_preview_message = preview.diagnostic.message
        last_geometry_message = quality.message

        if workflow.all_green(merged) and quality.generic:
            winning_pattern = pattern
            winning_attempt = attempt
            break

        winning_pattern = pattern
        winning_attempt = attempt

    if winning_pattern is None:
        winning_pattern = _build_pattern(point_count)

    report = winning_pattern.analyze_pattern()
    preview = workflow.build_preview(winning_pattern, spatial_mode=True)
    merged = workflow.merge_report_with_preview(report, preview.diagnostic)
    quality = workflow.geometry_quality(winning_pattern)
    found = workflow.all_green(merged) and quality.generic

    if found:
        status_title = "All green"
        status_message = f"Found a fully green sheet on attempt {winning_attempt}."
        note = (
            f"Local, assignment, global, and preview diagnostics all passed. "
            f"The last search used {last_optimize['rounds']} local optimization round"
            f"{'s' if last_optimize['rounds'] != 1 else ''}."
        )
        status_tone = "success"
    else:
        status_title = "Search stopped"
        status_message = f"Checked {winning_attempt} random sheet{'s' if winning_attempt != 1 else ''} without finding an all-green result."
        note = f"{last_assignment_message} {last_preview_message} {last_geometry_message}".strip()
        status_tone = "warning"

    return _snapshot(
        winning_pattern,
        point_count=point_count,
        status_title=status_title,
        status_message=status_message,
        note=note,
        status_tone=status_tone,
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
    return workflow.build_pattern(point_count, side=MODEL_SIDE)


def _optimize_until_local_green(
    pattern: cp.CreasePattern,
    *,
    max_rounds: int,
) -> dict[str, object]:
    return _optimization_dict(
        workflow.optimize_until_local_green(pattern, max_rounds=max_rounds)
    )


def _snapshot(
    pattern: cp.CreasePattern,
    *,
    status_title: str,
    status_message: str,
    note: str,
    status_tone: str | None = None,
    point_count: int | None = None,
    automation: dict[str, object] | None = None,
) -> str:
    return workflow.snapshot_json(
        pattern=pattern,
        status_title=status_title,
        status_message=status_message,
        note=note,
        status_tone=status_tone,
        point_count=point_count,
        automation=automation,
        spatial_mode=True,
    )


def _optimization_dict(result: workflow.OptimizationSummary) -> dict[str, object]:
    return {
        "green": bool(result.green),
        "rounds": int(result.rounds),
        "iterations": int(result.iterations),
        "loss": result.loss,
        "generic": (
            True
            if result.geometry_quality is None
            else bool(result.geometry_quality.generic)
        ),
        "geometry_message": (
            ""
            if result.geometry_quality is None
            else result.geometry_quality.message
        ),
    }
