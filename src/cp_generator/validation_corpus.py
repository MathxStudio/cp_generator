from __future__ import annotations

from dataclasses import dataclass
from importlib.resources.abc import Traversable
import json
from pathlib import Path

from . import core as cp
from . import exact_checker
from . import workflow


@dataclass(frozen=True)
class ValidationCase:
    case_id: str
    session_path: Path | Traversable
    note: str
    expected: dict[str, str]


@dataclass(frozen=True)
class EvaluatedCase:
    case: ValidationCase
    session: workflow.RestoredSession
    report: cp.PatternDiagnosticReport
    preview: workflow.PreviewBuildResult
    merged: cp.PatternDiagnosticReport
    exact_check: exact_checker.SmallInstanceCheckResult


def default_manifest_path() -> Traversable:
    return workflow.packaged_corpus_root() / "manifest.json"


def load_corpus(manifest_path: Path | Traversable | None = None) -> tuple[ValidationCase, ...]:
    manifest_file = default_manifest_path() if manifest_path is None else manifest_path
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    cases = []
    for item in payload.get("cases", []):
        cases.append(
            ValidationCase(
                case_id=str(item["id"]),
                session_path=manifest_file.parent / str(item["path"]),
                note=str(item.get("note", "")),
                expected=dict(item.get("expected", {})),
            )
        )
    return tuple(cases)


def case_map(
    manifest_path: Path | Traversable | None = None,
) -> dict[str, ValidationCase]:
    return {case.case_id: case for case in load_corpus(manifest_path)}


def load_case_payload(case: ValidationCase) -> dict[str, object]:
    return json.loads(case.session_path.read_text(encoding="utf-8"))


def evaluate_case(
    case: ValidationCase,
    *,
    max_faces: int = 8,
) -> EvaluatedCase:
    payload = load_case_payload(case)
    session = workflow.restore_session_payload(payload)
    preview = workflow.build_preview(
        session.pattern,
        preview_reference_pattern=session.preview_reference_pattern,
        allow_reference_fallback=session.preview_reference_pattern is not None,
        spatial_mode=True,
    )
    report = session.pattern.analyze_pattern()
    merged = workflow.merge_report_with_preview(report, preview.diagnostic)
    exact_check = exact_checker.check_small_instance(
        session.pattern,
        max_faces=max_faces,
    )
    return EvaluatedCase(
        case=case,
        session=session,
        report=report,
        preview=preview,
        merged=merged,
        exact_check=exact_check,
    )
