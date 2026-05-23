from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import validation_corpus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cp-generator-diagnostics",
        description=(
            "Run the checked-in validation corpus and compare the current pipeline "
            "against expected statuses and the bounded exact checker."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional path to a validation corpus manifest.",
    )
    parser.add_argument(
        "--max-faces",
        type=int,
        default=8,
        help="Maximum face count for the bounded exact checker.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the text summary.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit non-zero when any fixture result differs from its expected status.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cases = validation_corpus.load_corpus(args.manifest)

    evaluations = [
        validation_corpus.evaluate_case(case, max_faces=max(1, int(args.max_faces)))
        for case in cases
    ]
    mismatches = [evaluation for evaluation in evaluations if _case_mismatches(evaluation)]

    if args.json:
        payload = {
            "case_count": len(evaluations),
            "max_faces": max(1, int(args.max_faces)),
            "mismatch_count": len(mismatches),
            "cases": [_evaluation_payload(evaluation) for evaluation in evaluations],
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        _print_text_summary(evaluations, max_faces=max(1, int(args.max_faces)))

    if args.fail_on_mismatch and mismatches:
        return 1
    return 0


def _case_mismatches(evaluation: validation_corpus.EvaluatedCase) -> dict[str, tuple[str, str]]:
    expected = evaluation.case.expected
    actual = {
        "local_status": evaluation.merged.local_status,
        "assignment_status": evaluation.merged.fold_assignment_status,
        "global_status": evaluation.merged.global_status,
        "global_basis": evaluation.merged.global_diagnostic.basis,
        "preview_status": evaluation.preview.diagnostic.status,
        "preview_mode": evaluation.preview.diagnostic.preview_mode,
        "preview_basis": evaluation.preview.diagnostic.basis,
        "exact_checker_status": evaluation.exact_check.status,
    }
    return {
        key: (str(expected[key]), str(actual[key]))
        for key in expected
        if key in actual and str(expected[key]) != str(actual[key])
    }


def _evaluation_payload(
    evaluation: validation_corpus.EvaluatedCase,
) -> dict[str, object]:
    return {
        "id": evaluation.case.case_id,
        "note": evaluation.case.note,
        "expected": evaluation.case.expected,
        "actual": {
            "local_status": evaluation.merged.local_status,
            "assignment_status": evaluation.merged.fold_assignment_status,
            "global_status": evaluation.merged.global_status,
            "global_basis": evaluation.merged.global_diagnostic.basis,
            "preview_status": evaluation.preview.diagnostic.status,
            "preview_mode": evaluation.preview.diagnostic.preview_mode,
            "preview_basis": evaluation.preview.diagnostic.basis,
            "exact_checker_status": evaluation.exact_check.status,
        },
        "exact_checker": {
            "message": evaluation.exact_check.message,
            "face_count": evaluation.exact_check.face_count,
            "overlap_pair_count": evaluation.exact_check.overlap_pair_count,
            "total_orders_checked": evaluation.exact_check.total_orders_checked,
            "unique_order": evaluation.exact_check.unique_order,
        },
        "mismatches": _case_mismatches(evaluation),
    }


def _print_text_summary(
    evaluations: list[validation_corpus.EvaluatedCase],
    *,
    max_faces: int,
) -> None:
    print(f"Validation corpus: {len(evaluations)} case(s), bounded exact checker max_faces={max_faces}")
    print(
        "Case                     Local  Assign  Global               Preview              Exact   Match"
    )
    print(
        "-----------------------  -----  ------  -------------------  -------------------  ------  -----"
    )
    for evaluation in evaluations:
        mismatches = _case_mismatches(evaluation)
        global_text = (
            f"{evaluation.merged.global_status}/{evaluation.merged.global_diagnostic.basis}"
        )
        preview_text = (
            f"{evaluation.preview.diagnostic.status}/"
            f"{evaluation.preview.diagnostic.preview_mode}/"
            f"{evaluation.preview.diagnostic.basis}"
        )
        print(
            f"{evaluation.case.case_id:23}  "
            f"{evaluation.merged.local_status:5}  "
            f"{evaluation.merged.fold_assignment_status:6}  "
            f"{global_text:19}  "
            f"{preview_text:19}  "
            f"{evaluation.exact_check.status:6}  "
            f"{'ok' if not mismatches else 'mismatch'}"
        )
        if mismatches:
            for key, (expected, actual) in mismatches.items():
                print(f"  - {key}: expected {expected}, got {actual}")
    mismatch_count = sum(1 for evaluation in evaluations if _case_mismatches(evaluation))
    print(f"\nMismatches: {mismatch_count}")
