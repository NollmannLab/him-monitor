from __future__ import annotations

from datetime import datetime
from pathlib import Path


def latest_mtime(paths: list[Path] | tuple[Path, ...]) -> datetime | None:
    existing = [path.stat().st_mtime for path in paths if path.is_file()]
    return datetime.fromtimestamp(max(existing)) if existing else None
