from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def normalize_qudi(value: Any) -> Any:
    """Normalize Qudi's list-of-one-key-mappings representation recursively."""
    if isinstance(value, dict):
        return {key: normalize_qudi(item) for key, item in value.items()}
    if isinstance(value, list):
        normalized = [normalize_qudi(item) for item in value]
        keys = [next(iter(item)) for item in normalized if isinstance(item, dict) and len(item) == 1]
        if normalized and len(keys) == len(normalized) and len(set(keys)) == len(keys):
            merged: dict[str, Any] = {}
            for item in normalized:
                merged.update(item)
            return merged
        return normalized
    return value


def read_yaml(path: str | Path) -> tuple[dict[str, Any], str | None]:
    try:
        with Path(path).open(encoding="utf-8") as handle:
            value = yaml.safe_load(handle)
        if value is None:
            return {}, None
        if not isinstance(value, dict):
            return {}, "top-level YAML value is not a mapping"
        return normalize_qudi(value), None
    except (OSError, yaml.YAMLError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
