from __future__ import annotations

import unittest

from cp_generator import core as cp
from cp_generator import exact_checker
from cp_generator import validation_corpus
from cp_generator import workflow


CASE_MAP = validation_corpus.case_map()


def _load_pattern(case_id: str) -> cp.CreasePattern:
    payload = validation_corpus.load_case_payload(CASE_MAP[case_id])
    return cp.CreasePattern.from_data(payload["pattern"])


class SmallInstanceExactCheckerTests(unittest.TestCase):
    def test_all_green_fixture_passes_small_instance_check(self) -> None:
        pattern = _load_pattern("all_green")

        result = exact_checker.check_small_instance(pattern, max_faces=8)

        self.assertEqual(result.status, cp.STATUS_PASS)
        self.assertEqual(result.face_count, 4)

    def test_face_limit_can_defer_the_small_instance_check(self) -> None:
        pattern = _load_pattern("all_green")

        result = exact_checker.check_small_instance(pattern, max_faces=3)

        self.assertEqual(result.status, cp.STATUS_NOT_RUN)
        self.assertEqual(result.max_faces, 3)


class PreviewFailureTests(unittest.TestCase):
    def test_degenerate_zero_length_fold_reports_hard_preview_failure(self) -> None:
        pattern = cp.CreasePattern()
        pattern.side = 10
        vertex = cp.Vertex(5, 5)
        pattern.add_fold(vertex, vertex, 0)

        preview = workflow.build_preview(pattern)

        self.assertIsNone(preview.model)
        self.assertEqual(preview.diagnostic.status, cp.STATUS_FAIL)
        self.assertEqual(preview.diagnostic.preview_mode, "none")


if __name__ == "__main__":
    unittest.main()
