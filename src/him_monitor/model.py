from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    STALLED = "STALLED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DiscoveredFiles:
    folder: Path
    files: dict[str, Path] = field(default_factory=dict)
    output_files: tuple[Path, ...] = ()
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataHealth:
    available: tuple[str, ...] = ()
    not_yet_produced: tuple[str, ...] = ()
    missing_or_malformed: tuple[str, ...] = ()
    incomplete: tuple[str, ...] = ()


@dataclass(frozen=True)
class LogEvent:
    timestamp: datetime | None
    message: str
    level: str = "INFO"


@dataclass(frozen=True)
class ExperimentSnapshot:
    folder: Path
    name: str = "Unknown"
    microscope: str = "Unknown"
    mode: str = "Unknown"
    experiment_id: str | None = None
    task_class: str | None = None
    setup: str = "Unknown"
    roi_count: int | None = None
    probe_count: int | None = None
    status: RunStatus = RunStatus.UNKNOWN
    completed_cycles: int | None = None
    total_cycles: int | None = None
    elapsed_seconds: float | None = None
    last_activity: datetime | None = None
    phase: str | None = None
    cycle: int | None = None
    roi: int | None = None
    roi_name: str | None = None
    roi_progress: int | None = None
    roi_total: int | None = None
    current_cycle: str | None = None
    current_operation: str | None = None
    current_product: str | None = None
    target_volume_ul: float | None = None
    flow_rate_ul_min: float | None = None
    incubation_seconds: float | None = None
    last_event: str | None = None
    health: DataHealth = field(default_factory=DataHealth)
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)
