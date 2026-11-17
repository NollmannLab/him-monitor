from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ..model import LogEvent

TIMESTAMP = re.compile(r"(?P<stamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[,.]\d+)?)")
PHASE = re.compile(r"(?:phase|stage)\s*[:=]?\s*([A-Za-z0-9 _-]+)", re.I)
CYCLE = re.compile(r"cycle\s*(?:[:=]|#)?\s*(\d+)", re.I)
FRACTION = re.compile(r"(?<!\d)(\d+)\s*/\s*(\d+)(?:\s+(?:-\s*)?done|\s+cycle)?", re.I)
ROI = re.compile(r"ROI\s*(?:[:=]|#)?\s*(\d+)", re.I)
ROI_FRACTION = re.compile(r"(?:ROI[_ ]?\d+|ROI)\D+\((\d+)\s*/\s*(\d+)\)", re.I)
TASK_CLASS = re.compile(r"qudi\.tasks\.him\.([A-Za-z0-9_]+)", re.I)
ACTIVE_CYCLE = re.compile(r"\b(RT[\w-]+)\s*-\s*(hybridization|photobleaching)\s+step\b", re.I)
INJECTION = re.compile(
    r"inject\s+(?P<product>[^,(]+).*?(?P<volume>\d+(?:\.\d+)?)\s*(?:µl|ul|uL)\s+at\s+(?P<flow>\d+(?:\.\d+)?)\s*(?:µl|ul|uL)/min",
    re.I,
)
INCUBATION = re.compile(r"\bincubation\s+(?P<seconds>\d+(?:\.\d+)?)\s*s\b", re.I)
ROI_MOVE = re.compile(r"moving to\s+(?P<name>ROI[_ ]?\d+)\s*\((?P<current>\d+)\s*/\s*(?P<total>\d+)\)", re.I)
ROI_NAME = re.compile(r"\b(?P<name>ROI[_ ]?\d+)\b", re.I)


def _timestamp(message: str) -> datetime | None:
    match = TIMESTAMP.search(message)
    if not match:
        return None
    value = match.group("stamp").replace(",", ".")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def read_log(path: str | Path) -> tuple[list[LogEvent], str | None]:
    events: list[LogEvent] = []
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            upper = line.upper()
            if "WARNING" in upper or "WARN" in upper:
                level = "WARNING"
            elif "ERROR" in upper or "TRACEBACK" in upper or "EXCEPTION" in upper:
                level = "ERROR"
            else:
                level = "INFO"
            events.append(LogEvent(_timestamp(line), line.strip(), level))
        return events, None
    except OSError as exc:
        return [], f"{type(exc).__name__}: {exc}"


def infer_position(events: list[LogEvent]) -> tuple[str | None, int | None, int | None]:
    phase = cycle = roi = None
    for event in events:
        if match := PHASE.search(event.message):
            phase = match.group(1).strip()
        if match := CYCLE.search(event.message):
            cycle = int(match.group(1))
        if match := ROI.search(event.message):
            roi = int(match.group(1))
    return phase, cycle, roi


def infer_run_details(events: list[LogEvent]) -> tuple[str | None, int | None, int | None, int | None, int | None]:
    """Return phase, current cycle, total cycles, current ROI, total ROIs."""
    phase = cycle = total_cycles = roi = total_rois = None
    for event in events:
        message = event.message
        lower = message.lower()
        active_phase = _active_phase(lower)
        if active_phase is not None:
            phase = active_phase
        if match := re.search(r"cycle\s+(\d+)\s*/\s*(\d+)", message, re.I):
            cycle, total_cycles = int(match.group(1)), int(match.group(2))
        elif match := re.search(r"cycle\s+(\d+)\b", message, re.I):
            cycle = int(match.group(1))
        if match := re.search(r"(\d+)\s*/\s*(\d+)\s*-\s*done", message, re.I):
            cycle, total_cycles = int(match.group(1)), int(match.group(2))
        if match := re.search(r"moving to ROI[_ ]?\d+\s*\((\d+)\s*/\s*(\d+)\)", message, re.I):
            roi, total_rois = int(match.group(1)), int(match.group(2))
        elif match := re.search(r"ROI\s*(?:[:=]|#)?\s*(\d+)", message, re.I):
            roi = int(match.group(1))
        if match := re.search(r"autofocus check .*?:\s*(\d+)\s*/\s*(\d+)\s*ROI", message, re.I):
            roi, total_rois = int(match.group(1)), int(match.group(2))
    if phase == "COMPLETED" and total_rois is not None:
        roi = total_rois
    return phase, cycle, total_cycles, roi, total_rois


def _active_phase(message: str) -> str | None:
    """Infer only from active operations, ignoring protocol summaries."""
    if "hi-m task ended" in message or re.search(r"\b\d+\s*/\s*\d+\s*-\s*done\b", message):
        return "COMPLETED"
    if re.search(r"\brt[^-]*-\s*hybridization step\b", message):
        return "HYBRIDIZATION"
    if "triggering zen autofocus" in message or "autofocus confirmed done" in message:
        return "AUTOFOCUS"
    if (
        re.search(r"moving to roi[_ ]?\d+", message)
        or "dummy imaging" in message
        or "triggering zen acquisition" in message
        or "acquisition confirmed done" in message
    ):
        return "IMAGING"
    if re.search(r"\brt[^-]*-\s*photobleaching step\b", message):
        return "PHOTOBLEACHING"
    if "rinsing needle" in message:
        return "RINSING"
    if "cleanup" in message or "clean-up" in message:
        return "CLEANUP"
    return None


def task_class(events: list[LogEvent]) -> str | None:
    for event in events:
        if match := TASK_CLASS.search(event.message):
            return match.group(1)
    return None


def infer_operation(events: list[LogEvent]) -> dict[str, object | None]:
    """Extract the latest active operation, ignoring configuration summaries."""
    operation: dict[str, object | None] = {
        "cycle": None,
        "operation": None,
        "product": None,
        "volume_ul": None,
        "flow_ul_min": None,
        "incubation_seconds": None,
        "roi_name": None,
        "roi_progress": None,
        "roi_total": None,
    }
    for event in events:
        message = event.message
        lower = message.lower()
        if match := ACTIVE_CYCLE.search(message):
            operation["cycle"] = match.group(1).upper()
            operation["operation"] = match.group(2).upper()
            operation["product"] = None
            operation["volume_ul"] = None
            operation["flow_ul_min"] = None
            operation["incubation_seconds"] = None
        if match := INJECTION.search(message):
            operation["product"] = match.group("product").strip()
            operation["volume_ul"] = float(match.group("volume"))
            operation["flow_ul_min"] = float(match.group("flow"))
        if match := INCUBATION.search(message):
            operation["operation"] = "INCUBATION"
            operation["incubation_seconds"] = float(match.group("seconds"))
            operation["product"] = None
            operation["volume_ul"] = None
            operation["flow_ul_min"] = None
        if match := ROI_MOVE.search(message):
            operation["operation"] = "IMAGING"
            operation["roi_name"] = match.group("name").replace(" ", "_").upper()
            operation["roi_progress"] = int(match.group("current"))
            operation["roi_total"] = int(match.group("total"))
        elif any(term in lower for term in ("triggering zen acquisition", "acquisition confirmed done", "dummy imaging")):
            operation["operation"] = "IMAGING"
            if match := ROI_NAME.search(message):
                operation["roi_name"] = match.group("name").replace(" ", "_").upper()
        if "hi-m task ended" in lower or re.search(r"\b\d+\s*/\s*\d+\s*-\s*done\b", lower):
            operation["operation"] = "COMPLETED"
    return operation
