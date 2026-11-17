from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from him_monitor.discovery import discover_metadata_folder, discover_files
from him_monitor.model import LogEvent, RunStatus
from him_monitor.readers.injections import read_injections
from him_monitor.readers.csv_reader import read_csv
from him_monitor.readers.log_reader import infer_operation, infer_run_details, read_log
from him_monitor.readers.yaml_reader import read_yaml
from him_monitor.service import load_experiment
from him_monitor.status import classify_status

DATA = Path(__file__).parent / "data"
NESTED = DATA / "nested_experiment"


def test_discovery_accepts_metadata_folder_and_parent(tmp_path):
    metadata = tmp_path / "experiment" / "metadata"
    metadata.mkdir(parents=True)
    (metadata / "metadata.yml").write_text("name: x", encoding="utf-8")
    assert discover_metadata_folder(metadata) == metadata
    assert discover_metadata_folder(tmp_path) == metadata


def test_discovery_reports_missing_expected_files():
    discovered = discover_files(DATA)
    assert "metadata.yml" in discovered.files
    assert "experiment_config.yaml" in discovered.missing


def test_readers_parse_valid_fixture():
    metadata, error = read_yaml(DATA / "metadata.yml")
    _, count, injection_error = read_injections(DATA / "injections.yml")
    events, log_error = read_log(DATA / "HiM_task.log")
    assert error is None and metadata["experiment_name"] == "synthetic overview"
    assert injection_error is None and count == 2
    assert log_error is None and len(events) == 2


def test_readers_report_malformed_files(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("broken: [", encoding="utf-8")
    _, error = read_yaml(bad)
    assert error
    missing_events, error = read_log(tmp_path / "missing.log")
    assert missing_events == [] and error
    malformed_csv = tmp_path / "bad.csv"
    malformed_csv.write_bytes(b"header\n\xff")
    _, error = read_csv(malformed_csv)
    assert error


def test_status_classifier_is_conservative():
    now = datetime(2026, 11, 13, 12)
    assert classify_status([LogEvent(now, "starting")], now, now=now) is RunStatus.RUNNING
    assert classify_status([LogEvent(now, "experiment completed")], now, now=now) is RunStatus.COMPLETED
    assert classify_status([LogEvent(now, "Traceback: error")], now, now=now) is RunStatus.FAILED
    assert classify_status([LogEvent(now, "aborted by user")], now, now=now) is RunStatus.INTERRUPTED
    assert classify_status([LogEvent(now, "starting")], now - timedelta(hours=2), now=now) is RunStatus.STALLED
    assert classify_status([], None, now=now) is RunStatus.UNKNOWN


def test_load_experiment_fixture():
    snapshot = load_experiment(DATA)
    assert snapshot.name == "synthetic overview"
    assert snapshot.probe_count == 2
    assert snapshot.cycle == 1 and snapshot.roi == 2
    assert snapshot.status is RunStatus.RUNNING
    assert snapshot.elapsed_seconds == 60
    assert "experiment_config.yaml" in snapshot.health.not_yet_produced


def test_nested_fixture_matches_completed_him_experiment_expectations():
    snapshot = load_experiment(NESTED)
    assert snapshot.folder == NESTED / "metadata"
    assert snapshot.name == "sanitized sample"
    assert snapshot.experiment_id == "him_epi_sd"
    assert snapshot.task_class == "HiMSDTask"
    assert snapshot.microscope == "Spinning Disk"
    assert snapshot.mode == "Epifluorescence"
    assert snapshot.roi_count == 15
    assert snapshot.probe_count == 11
    assert snapshot.status is RunStatus.COMPLETED
    assert snapshot.phase == "COMPLETED"
    assert snapshot.completed_cycles == 11
    assert snapshot.total_cycles == 11
    assert snapshot.roi == 15
    assert snapshot.conflicts
    assert any("RAMM" in warning for warning in snapshot.warnings)


def test_status_ignores_transfer_warnings_but_detects_real_failures():
    now = datetime(2026, 11, 13, 12)
    warnings = [LogEvent(now, "server folder not reachable (copy failed)", "WARNING")]
    assert classify_status(warnings, now, now=now) is RunStatus.RUNNING
    assert classify_status(warnings + [LogEvent(now, "11/11 - Done")], now, now=now) is RunStatus.COMPLETED
    assert classify_status([LogEvent(now, "ERROR task failed: camera exception", "ERROR")], now, now=now) is RunStatus.FAILED


def test_phase_inference_ignores_protocol_summary_and_tracks_active_operations():
    events = [
        LogEvent(None, "photobleaching: 0 step(s), buffer valve only"),
        LogEvent(None, "planned hybridization: 6 step(s)"),
        LogEvent(None, "RT1 - hybridization step 1/6: inject WB"),
        LogEvent(None, "moving to ROI_000 (1/15)"),
        LogEvent(None, "Triggering ZEN acquisition for ROI_000"),
    ]
    assert infer_run_details(events)[0] == "IMAGING"
    assert infer_run_details(events[:3])[0] == "HYBRIDIZATION"
    assert infer_run_details(events[:2])[0] is None


def test_phase_transitions_to_photobleaching_only_for_active_step():
    summary = [LogEvent(None, "photobleaching: 0 step(s), buffer valve only")]
    active = [LogEvent(None, "RT1 - photobleaching step 1/2: inject TCEP")]
    assert infer_run_details(summary)[0] is None
    assert infer_run_details(summary + active)[0] == "PHOTOBLEACHING"


def test_live_snapshot_changes_after_log_is_extended(tmp_path):
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (metadata / "metadata.yml").write_text("Acquisition:\n- sample_name: live\n", encoding="utf-8")
    log = metadata / "HiM_task.log"
    log.write_text("2026-11-16 10:00:00 - info - RT1 - hybridization step 1/2\n", encoding="utf-8")
    first = load_experiment(metadata)
    log.write_text(
        log.read_text(encoding="utf-8")
        + "2026-11-16 10:00:05 - info - Triggering ZEN acquisition for ROI_000\n",
        encoding="utf-8",
    )
    second = load_experiment(metadata)
    assert first.phase == "HYBRIDIZATION"
    assert second.phase == "IMAGING"
    assert second.last_event != first.last_event
    assert second.elapsed_seconds == 5


def test_current_operation_extracts_injection_incubation_and_imaging_details():
    injection = LogEvent(None, "RT2 - hybridization step 1/3: inject Probe (valve 7), 50 µl at 250 µl/min")
    incubation = LogEvent(None, "RT2 - hybridization step 2/3: incubation 5 s")
    imaging = LogEvent(None, "moving to ROI_030 (5/25)")
    details = infer_operation([injection])
    assert details["cycle"] == "RT2"
    assert details["operation"] == "HYBRIDIZATION"
    assert details["product"] == "Probe"
    assert details["volume_ul"] == 50.0
    assert details["flow_ul_min"] == 250.0
    details = infer_operation([injection, incubation])
    assert details["operation"] == "INCUBATION"
    assert details["incubation_seconds"] == 5.0
    details = infer_operation([injection, imaging])
    assert details["operation"] == "IMAGING"
    assert details["roi_name"] == "ROI_030"
    assert details["roi_progress"] == 5 and details["roi_total"] == 25


def test_overview_uses_grouped_ui_without_task_class():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QGroupBox, QLabel
    from him_monitor.qt.overview import OverviewWindow

    app = QApplication.instance() or QApplication([])
    window = OverviewWindow(load_experiment(DATA))
    group_titles = {group.title() for group in window.findChildren(QGroupBox)}
    label_text = "\n".join(label.text() for label in window.findChildren(QLabel))
    assert "General experiment information" in group_titles
    assert "Current operation" in group_titles
    assert "STATUS" in label_text and "CYCLES" in label_text and "OPERATION" in label_text
    assert "PHASE" not in label_text
    assert "HiMDummyTask" not in label_text and "HiMSDTask" not in label_text
    assert "ROIs" not in label_text and "Probes / barcodes" not in label_text
    assert "22px" in window._labels["status"].styleSheet()
    assert "#f5f7fa" in window.styleSheet()
    assert not window._messages_box.isVisible()
    assert "Activity age" not in label_text
    assert "Last monitor refresh" not in label_text
    assert "Data health" not in label_text
    assert "." not in window._labels["last_activity"].text()
    window.close()
    app.processEvents()


def test_last_activity_is_second_precision_and_basic_window_omits_technical_fields():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QLabel
    from him_monitor.qt.overview import OverviewWindow

    app = QApplication.instance() or QApplication([])
    window = OverviewWindow(load_experiment(DATA))
    labels = "\n".join(label.text() for label in window.findChildren(QLabel))
    assert window._labels["last_activity"].text() == "2026-11-13 10:01:00"
    assert "Activity age" not in labels
    assert "Last monitor refresh" not in labels
    assert "Data health" not in labels
    window.close()
    app.processEvents()


def test_imaging_modality_is_read_recursively_and_overrides_fallback(tmp_path):
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (metadata / "metadata.yml").write_text(
        "Microscope:\n- type: RAMM\n- Imaging_Modality: Epifluorescence\n",
        encoding="utf-8",
    )
    (metadata / "HiM_task.log").write_text("2026-11-17 14:32:08 - info - starting\n", encoding="utf-8")
    snapshot = load_experiment(metadata)
    assert snapshot.mode == "Epifluorescence"


def test_imaging_modality_from_nested_parameters_and_fallback_without_it(tmp_path):
    metadata = tmp_path / "metadata"
    parameters = metadata / "experiment_parameters"
    parameters.mkdir(parents=True)
    (metadata / "metadata.yml").write_text("Microscope:\n- type: RAMM\n", encoding="utf-8")
    (parameters / "HiM_parameters.yml").write_text(
        "1- global parameters:\n  experiment: him_epi_sd\n2- imaging parameters:\n- imaging modality: Spinning Disk\n",
        encoding="utf-8",
    )
    (metadata / "HiM_task.log").write_text("2026-11-17 14:32:08 - info - starting\n", encoding="utf-8")
    snapshot = load_experiment(metadata)
    assert snapshot.mode == "Spinning Disk"

    fallback = tmp_path / "fallback"
    fallback.mkdir()
    (fallback / "HiM_parameters.yml").write_text("experiment: him_epi_sd\n", encoding="utf-8")
    (fallback / "HiM_task.log").write_text("2026-11-17 14:32:08 - info - starting\n", encoding="utf-8")
    assert load_experiment(fallback).mode == "Epifluorescence"


def test_overview_colors_current_activity_and_roi_by_context():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from him_monitor.qt.overview import OverviewWindow

    app = QApplication.instance() or QApplication([])
    base = load_experiment(DATA)
    imaging = replace(base, phase="IMAGING", current_operation="IMAGING", roi_name="ROI_030", roi_progress=5, roi_total=25)
    window = OverviewWindow(imaging)
    assert "#16803c" in window._labels["roi"].styleSheet()
    hybridization = replace(base, phase="HYBRIDIZATION", current_operation="HYBRIDIZATION", current_product="Probe", incubation_seconds=None)
    window._update_display(hybridization)
    assert "#16803c" in window._labels["activity"].styleSheet()
    not_active = replace(base, phase="AUTOFOCUS", current_operation="AUTOFOCUS", current_product=None, incubation_seconds=None)
    window._update_display(not_active)
    assert "#667085" in window._labels["roi"].styleSheet()
    assert "#667085" in window._labels["activity"].styleSheet()
    incubation = replace(hybridization, current_product=None, incubation_seconds=5)
    window._update_display(incubation)
    assert window._labels["activity"].text().startswith("INCUBATION")
    assert "#16803c" in window._labels["activity"].styleSheet()
    window.close()
    app.processEvents()


def test_completed_window_remains_open_and_shows_final_cards():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from him_monitor.qt.overview import OverviewWindow

    app = QApplication.instance() or QApplication([])
    window = OverviewWindow(load_experiment(NESTED))
    window.show()
    app.processEvents()
    assert window.isVisible()
    assert window._labels["status"].text() == "COMPLETED"
    assert window._labels["cycles_card"].text() == "11/11"
    assert window._labels["operation"].text() == "COMPLETED"
    assert window._refresh_timer.isActive()
    window.close()
    app.processEvents()
