"""Where the server lives. One definition, so nothing drifts."""

from __future__ import annotations

import os

PORT = int(os.environ.get("MITL_PORT", "4711"))

# 127.0.0.1 rather than localhost: on Windows the latter resolves to ::1 first
# and the IPv4 fallback costs about two seconds per call.
APP_URL = os.environ.get("MITL_URL", f"http://127.0.0.1:{PORT}")
