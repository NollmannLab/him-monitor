from __future__ import annotations

from pathlib import Path
from typing import Any

from .yaml_reader import read_yaml


def read_injections(path: str | Path) -> tuple[dict[str, Any], int | None, str | None]:
    data, error = read_yaml(path)
    if error:
        return {}, None, error
    probes = data.get("probes")
    if probes is None:
        return data, None, None
    if isinstance(probes, dict):
        return data, len(probes), None
    if isinstance(probes, (list, tuple)):
        return data, len(probes), None
    return data, None, "probes is neither a list nor a mapping"
