from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QSizePolicy, QVBoxLayout, QWidget,
)

from ..model import ExperimentSnapshot
from ..service import load_experiment


def _value(value: object) -> str:
    return "unknown" if value is None else str(value)


def _status_color(status: str) -> str:
    if status in {"COMPLETED", "RUNNING"}:
        return "#16803c"
    if status == "FAILED":
        return "#b42318"
    if status in {"STALLED", "INTERRUPTED"}:
        return "#b54708"
    return "#667085"


def _format_elapsed(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    minutes, remainder = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min {remainder} s"


def _format_number(value: float | None) -> str:
    return "unknown" if value is None else f"{value:g}"


def _display_log_message(message: str) -> str:
    """Remove timestamp/logger/task-class prefixes from user-facing messages."""
    return re.sub(
        r"^\d{4}-\d{2}-\d{2}[,\sT:\d.-]+\s+-\s+\w+\s+-\s+[^-]+\s+-\s+",
        "",
        message,
    ).strip()


class OverviewWindow(QMainWindow):
    """Read-only, live-updating overview for one selected experiment folder."""

    def __init__(self, snapshot: ExperimentSnapshot) -> None:
        super().__init__()
        self._folder = Path(snapshot.folder)
        self._snapshot = snapshot
        self._last_refresh = datetime.now()
        self._labels: dict[str, QLabel] = {}

        root = QWidget()
        root.setObjectName("overviewRoot")
        main_layout = QVBoxLayout(root)
        main_layout.setSpacing(12)
        main_layout.addWidget(self._build_general_section())
        main_layout.addWidget(self._build_status_section())
        main_layout.addWidget(self._build_operation_section())
        main_layout.addWidget(self._build_secondary_section())
        main_layout.addWidget(self._build_messages_section())
        self.setCentralWidget(root)

        self._update_display(snapshot)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(3000)
        self._refresh_timer.timeout.connect(self.refresh_snapshot)
        self._refresh_timer.start()
        self.setMinimumWidth(700)
        self.setStyleSheet(
            "QWidget#overviewRoot { background: #f5f7fa; color: #1d2939; }"
            " QGroupBox { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 6px;"
            " margin-top: 8px; padding: 12px; color: #1d2939; }"
            " QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px;"
            " background: #f5f7fa; font-weight: bold; color: #344054; }"
            " QLabel { color: #1d2939; }"
        )

    def _build_general_section(self) -> QGroupBox:
        box = QGroupBox("General experiment information")
        form = QFormLayout(box)
        for key, label in (("name", "Experiment / sample"), ("experiment_id", "Experiment identifier"), ("microscope", "Microscope"), ("mode", "Mode")):
            self._labels[key] = QLabel()
            form.addRow(QLabel(f"<b>{label}</b>"), self._labels[key])
        return box

    def _build_status_section(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self._status_card, self._labels["status"] = self._build_card("STATUS")
        self._cycles_card, self._labels["cycles_card"] = self._build_card("CYCLES")
        self._operation_card, self._labels["operation"] = self._build_card("OPERATION")
        layout.addWidget(self._status_card)
        layout.addWidget(self._cycles_card)
        layout.addWidget(self._operation_card)
        return container

    def _build_card(self, title: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(card)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #667085")
        value_label = QLabel("UNKNOWN")
        value_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #667085")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return card, value_label

    def _build_operation_section(self) -> QGroupBox:
        box = QGroupBox("Current operation")
        form = QFormLayout(box)
        for key, label in (("current_cycle", "Cycle / probe"), ("activity", "Current activity"), ("target", "Target"), ("roi", "Current ROI")):
            self._labels[key] = QLabel()
            self._labels[key].setWordWrap(True)
            form.addRow(QLabel(f"<b>{label}</b>"), self._labels[key])
        return box

    def _build_secondary_section(self) -> QGroupBox:
        box = QGroupBox("Experiment details")
        form = QFormLayout(box)
        for key, label in (("elapsed", "Elapsed time"), ("last_activity", "Last experiment activity"), ("activity_age", "Activity age"), ("monitor_refresh", "Last monitor refresh"), ("latest", "Latest event"), ("folder", "Experiment folder"), ("health", "Data health")):
            self._labels[key] = QLabel()
            self._labels[key].setWordWrap(True)
            form.addRow(QLabel(f"<b>{label}</b>"), self._labels[key])
        return box

    def _build_messages_section(self) -> QGroupBox:
        self._messages_box = QGroupBox("Warnings and errors")
        layout = QVBoxLayout(self._messages_box)
        self._warnings_label = QLabel()
        self._warnings_label.setWordWrap(True)
        self._errors_label = QLabel()
        self._errors_label.setWordWrap(True)
        layout.addWidget(self._warnings_label)
        layout.addWidget(self._errors_label)
        return self._messages_box

    def refresh_snapshot(self) -> None:
        """Reload the selected folder without replacing the current window."""
        try:
            snapshot = load_experiment(self._folder)
        except Exception:
            # A network file can be appended or temporarily unreadable. Keep
            # the last valid display and retry at the next timer tick.
            return
        self._snapshot = snapshot
        self._last_refresh = datetime.now()
        self._update_display(snapshot)

    def _update_display(self, snapshot: ExperimentSnapshot) -> None:
        self._labels["name"].setText(snapshot.name)
        self._labels["experiment_id"].setText(_value(snapshot.experiment_id))
        self._labels["microscope"].setText(snapshot.microscope)
        self._labels["mode"].setText(snapshot.mode)

        color = _status_color(snapshot.status.value)
        operation = snapshot.current_operation or snapshot.phase or "UNKNOWN"
        self._labels["status"].setText(snapshot.status.value)
        self._labels["status"].setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color}")
        self._labels["cycles_card"].setText(f"{_value(snapshot.completed_cycles)}/{_value(snapshot.total_cycles)}")
        self._labels["cycles_card"].setStyleSheet("font-size: 22px; font-weight: bold; color: #1d2939")
        self._labels["operation"].setText(operation)
        self._labels["operation"].setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color}")
        self._status_card.setStyleSheet(f"QFrame {{ border: 2px solid {color}; border-radius: 6px; }}")
        self._cycles_card.setStyleSheet("QFrame { border: 2px solid #98a2b3; border-radius: 6px; }")
        self._operation_card.setStyleSheet(f"QFrame {{ border: 2px solid {color}; border-radius: 6px; }}")

        self._labels["current_cycle"].setText(_value(snapshot.current_cycle))
        target = "unknown"
        if snapshot.target_volume_ul is not None or snapshot.flow_rate_ul_min is not None:
            target = f"{_format_number(snapshot.target_volume_ul)} µl at {_format_number(snapshot.flow_rate_ul_min)} µl/min"
        self._labels["target"].setText(target)
        if snapshot.incubation_seconds is not None:
            activity_text = f"INCUBATION ({_format_number(snapshot.incubation_seconds)} s)"
        elif snapshot.current_product is not None:
            activity_text = snapshot.current_product
        else:
            activity_text = "unknown"
        self._labels["activity"].setText(activity_text)
        active_activity = operation in {"HYBRIDIZATION", "PHOTOBLEACHING"} and activity_text != "unknown"
        self._labels["activity"].setStyleSheet(f"color: {'#16803c' if active_activity else '#667085'}; font-weight: bold")
        if snapshot.roi_name:
            progress = f" ({snapshot.roi_progress}/{snapshot.roi_total})" if snapshot.roi_progress and snapshot.roi_total else ""
            roi_text = f"{snapshot.roi_name}{progress}"
        else:
            roi_text = "unknown"
        self._labels["roi"].setText(roi_text)
        self._labels["roi"].setStyleSheet(f"color: {'#16803c' if snapshot.phase == 'IMAGING' else '#667085'}; font-weight: bold")

        self._labels["elapsed"].setText(_format_elapsed(snapshot.elapsed_seconds))
        self._labels["last_activity"].setText(_value(snapshot.last_activity))
        self._labels["activity_age"].setText(_activity_age(snapshot.last_activity))
        self._labels["monitor_refresh"].setText(self._last_refresh.strftime("%Y-%m-%d %H:%M:%S"))
        self._labels["latest"].setText(_display_log_message(snapshot.last_event) if snapshot.last_event else "unknown")
        self._labels["folder"].setText(str(self._folder))
        self._labels["health"].setText(f"{len(snapshot.health.available)} available; {len(snapshot.health.not_yet_produced)} not yet produced; {len(snapshot.health.missing_or_malformed)} missing/malformed; {len(snapshot.health.incomplete)} incomplete")

        warning_items = (*snapshot.warnings, *snapshot.conflicts)
        self._warnings_label.setText("Warnings:\n" + "\n".join(f"• {_display_log_message(item)}" for item in warning_items) if warning_items else "")
        self._errors_label.setText("Errors:\n" + "\n".join(f"• {_display_log_message(item)}" for item in snapshot.errors) if snapshot.errors else "")
        self._warnings_label.setStyleSheet("color: #b54708")
        self._errors_label.setStyleSheet("color: #b42318")
        self._messages_box.setVisible(bool(warning_items or snapshot.errors))
        self.setWindowTitle(f"him-monitor — {snapshot.name}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._refresh_timer.stop()
        super().closeEvent(event)


def _activity_age(activity: datetime | None) -> str:
    if activity is None:
        return "unknown"
    seconds = max(0, int((datetime.now() - activity).total_seconds()))
    if seconds < 60:
        return f"{seconds} s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    return f"{minutes // 60} h {minutes % 60} min ago"
