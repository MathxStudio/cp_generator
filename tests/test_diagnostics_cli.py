from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from cp_generator import diagnostics_cli


class DiagnosticsCliTests(unittest.TestCase):
    def test_text_summary_reports_all_cases(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = diagnostics_cli.main([])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Validation corpus:", output)
        self.assertIn("all_green", output)
        self.assertIn("Mismatches: 0", output)

    def test_json_mode_emits_machine_readable_results(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = diagnostics_cli.main(["--json"])

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertGreaterEqual(payload["case_count"], 6)
        self.assertEqual(payload["mismatch_count"], 0)
        self.assertTrue(any(item["id"] == "crossing_folds" for item in payload["cases"]))


if __name__ == "__main__":
    unittest.main()
