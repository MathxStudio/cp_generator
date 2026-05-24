from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def frozen_library_search_dirs(
    *,
    meipass: str | None,
    executable: str | None,
) -> list[str]:
    dirs: list[str] = []

    if meipass:
        base = Path(meipass)
        dirs.extend([str(base), str(base / "lib")])

    if executable:
        executable_dir = Path(executable).resolve().parent
        contents_dir = executable_dir.parent
        dirs.extend(
            [
                str(executable_dir),
                str(executable_dir / "lib"),
                str(executable_dir / "_internal"),
                str(executable_dir / "_internal" / "lib"),
                str(contents_dir / "Frameworks"),
                str(contents_dir / "Resources"),
            ]
        )

    return _dedupe_preserving_order(dirs)


def configure_frozen_library_search_path(
    env: MutableMapping[str, str],
    *,
    platform: str,
    meipass: str | None,
    executable: str | None,
) -> None:
    if platform != "darwin":
        return

    bundled_dirs = frozen_library_search_dirs(
        meipass=meipass,
        executable=executable,
    )
    existing = env.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    current_dirs = [value for value in existing.split(":") if value]
    combined = _dedupe_preserving_order(bundled_dirs + current_dirs)
    if combined:
        env["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(combined)
