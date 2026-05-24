from __future__ import annotations

import unittest

from cp_generator.runtime_support import (
    configure_frozen_library_search_path,
    frozen_library_search_dirs,
)


class FrozenLibrarySearchPathTests(unittest.TestCase):
    def test_frozen_library_search_dirs_covers_bundle_and_runtime_paths(self) -> None:
        executable = "/tmp/CPGenerator.app/Contents/MacOS/CPGenerator"
        dirs = frozen_library_search_dirs(
            meipass="/tmp/_MEI12345",
            executable=executable,
        )

        self.assertEqual(
            dirs,
            [
                "/tmp/_MEI12345",
                "/tmp/_MEI12345/lib",
                "/tmp/CPGenerator.app/Contents/MacOS",
                "/tmp/CPGenerator.app/Contents/MacOS/lib",
                "/tmp/CPGenerator.app/Contents/MacOS/_internal",
                "/tmp/CPGenerator.app/Contents/MacOS/_internal/lib",
                "/tmp/CPGenerator.app/Contents/Frameworks",
                "/tmp/CPGenerator.app/Contents/Resources",
            ],
        )

    def test_configure_frozen_library_search_path_prepends_bundle_dirs_on_macos(self) -> None:
        env = {"DYLD_FALLBACK_LIBRARY_PATH": "/usr/local/lib:/opt/custom"}
        configure_frozen_library_search_path(
            env,
            platform="darwin",
            meipass="/tmp/_MEI12345",
            executable="/tmp/CPGenerator.app/Contents/MacOS/CPGenerator",
        )

        self.assertEqual(
            env["DYLD_FALLBACK_LIBRARY_PATH"],
            ":".join(
                [
                    "/tmp/_MEI12345",
                    "/tmp/_MEI12345/lib",
                    "/tmp/CPGenerator.app/Contents/MacOS",
                    "/tmp/CPGenerator.app/Contents/MacOS/lib",
                    "/tmp/CPGenerator.app/Contents/MacOS/_internal",
                    "/tmp/CPGenerator.app/Contents/MacOS/_internal/lib",
                    "/tmp/CPGenerator.app/Contents/Frameworks",
                    "/tmp/CPGenerator.app/Contents/Resources",
                    "/usr/local/lib",
                    "/opt/custom",
                ]
            ),
        )

    def test_configure_frozen_library_search_path_is_noop_off_macos(self) -> None:
        env = {"DYLD_FALLBACK_LIBRARY_PATH": "/usr/local/lib"}
        configure_frozen_library_search_path(
            env,
            platform="linux",
            meipass=None,
            executable=None,
        )

        self.assertEqual(env["DYLD_FALLBACK_LIBRARY_PATH"], "/usr/local/lib")


if __name__ == "__main__":
    unittest.main()
