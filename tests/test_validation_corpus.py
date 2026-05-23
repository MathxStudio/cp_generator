from __future__ import annotations

import unittest

from cp_generator import validation_corpus


class ValidationCorpusTests(unittest.TestCase):
    def test_manifest_cases_match_expected_diagnostics(self) -> None:
        cases = validation_corpus.load_corpus()
        self.assertGreaterEqual(len(cases), 6)

        for case in cases:
            with self.subTest(case=case.case_id):
                evaluation = validation_corpus.evaluate_case(case)
                expected = case.expected

                self.assertEqual(evaluation.merged.local_status, expected["local_status"])
                self.assertEqual(
                    evaluation.merged.fold_assignment_status,
                    expected["assignment_status"],
                )
                self.assertEqual(
                    evaluation.merged.global_status,
                    expected["global_status"],
                )
                self.assertEqual(
                    evaluation.preview.diagnostic.status,
                    expected["preview_status"],
                )
                self.assertEqual(
                    evaluation.preview.diagnostic.preview_mode,
                    expected["preview_mode"],
                )
                self.assertEqual(
                    evaluation.merged.global_diagnostic.basis,
                    expected["global_basis"],
                )
                self.assertEqual(
                    evaluation.preview.diagnostic.basis,
                    expected["preview_basis"],
                )
                self.assertEqual(
                    evaluation.exact_check.status,
                    expected["exact_checker_status"],
                )


if __name__ == "__main__":
    unittest.main()
