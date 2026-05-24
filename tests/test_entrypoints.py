from __future__ import annotations

import io
from pathlib import Path
import runpy
import unittest
from unittest import mock

from cp_generator import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DesktopEntrypointTests(unittest.TestCase):
    def test_main_smoke_test_mode_skips_tk_boot(self) -> None:
        output = io.StringIO()
        with mock.patch("cp_generator.app.tk.Tk") as tk_root:
            with mock.patch("sys.stdout", output):
                exit_code = app.main(["--smoke-test"])

        self.assertEqual(exit_code, 0)
        self.assertIn("smoke test ok", output.getvalue().lower())
        tk_root.assert_not_called()

    def test_package_main_runs_when_executed_as_a_script_path(self) -> None:
        entrypoint = PROJECT_ROOT / "src" / "cp_generator" / "__main__.py"

        with mock.patch("cp_generator.app.main", return_value=0) as main:
            with self.assertRaises(SystemExit) as stop:
                runpy.run_path(str(entrypoint), run_name="__main__")

        self.assertEqual(stop.exception.code, 0)
        main.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
