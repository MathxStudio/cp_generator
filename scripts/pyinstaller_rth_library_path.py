from __future__ import annotations

import os
import sys

from cp_generator.runtime_support import configure_frozen_library_search_path


configure_frozen_library_search_path(
    os.environ,
    platform=sys.platform,
    meipass=getattr(sys, "_MEIPASS", None),
    executable=sys.executable,
)
