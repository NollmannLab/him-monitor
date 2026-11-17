from __future__ import annotations

from datetime import datetime, timedelta
import re

from .model import LogEvent, RunStatus

COMPLETION = ("experiment completed", "experiment finished", "run completed", "finished successfully", "hi-m task ended")
INTERRUPTION = ("interrupted", "keyboardinterrupt", "cancelled", "canceled", "aborted")
FAILURE = ("traceback", "fatal", "critical", "unhandled exception", "task exception", "task failed")
ACTIVITY = ("starting", "running", "processing", "acquiring", "cycle", "roi", "phase")
NON_FATAL = ("copy failed", "server folder", "not reachable", "data transfer")


def classify_status(events: list[LogEvent], last_activity: datetime | None, *, now: datetime | None = None, stall_after: timedelta = timedelta(hours=1)) -> RunStatus:
    messages = [event.message.lower() for event in events]
    if any(any(term in message for term in COMPLETION) for message in messages) or any(
        re.search(r"\b\d+\s*/\s*\d+\s*-\s*done\b", message, re.I) for message in messages
    ):
        return RunStatus.COMPLETED
    if any(any(term in message for term in INTERRUPTION) for message in messages):
        return RunStatus.INTERRUPTED
    if any(event.level == "ERROR" and not any(term in event.message.lower() for term in NON_FATAL) for event in events) or any(any(term in message for term in FAILURE) for message in messages) or any(
        "exception" in message and not any(term in message for term in NON_FATAL) for message in messages
    ):
        return RunStatus.FAILED
    if last_activity is not None and now is not None and now - last_activity > stall_after:
        return RunStatus.STALLED
    if events or any(any(term in message for term in ACTIVITY) for message in messages):
        return RunStatus.RUNNING
    return RunStatus.UNKNOWN
