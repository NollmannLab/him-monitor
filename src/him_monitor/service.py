from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .discovery import discover_files, discover_metadata_folder
from .model import DataHealth, ExperimentSnapshot
from .readers.injections import read_injections
from .readers.log_reader import infer_operation, infer_run_details, read_log, task_class
from .readers.timestamps import latest_mtime
from .readers.yaml_reader import read_yaml
from .status import classify_status


def _first(data: dict, *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value not in (None, "") and isinstance(value, (str, int, float)):
            return str(value)
    return None


def _section(data: dict, *names: str) -> dict:
    wanted = {name.casefold() for name in names}
    for key, value in data.items():
        if str(key).casefold() in wanted and isinstance(value, dict):
            return value
    return {}


def _first_from(sections: tuple[dict, ...], *keys: str) -> str | None:
    for section in sections:
        if value := _first(section, *keys):
            return value
    return None


def _count_rois(sections: tuple[dict, ...]) -> int | None:
    for section in sections:
        for key in ("roi_list_(xyz)", "roi_list", "rois", "ROI", "roi_count"):
            value = next((item for item_key, item in section.items() if str(item_key).casefold() == key.casefold()), None)
            if isinstance(value, (dict, list, tuple)):
                return len(value)
            if isinstance(value, int):
                return value
    return None


def _microscope(metadata: dict, experiment_id: str | None, task: str | None) -> tuple[str, str, tuple[str, ...]]:
    microscope_section = _section(metadata, "Microscope")
    generic = _first(microscope_section, "type", "microscope", "name")
    explicit = _first(metadata, "corrected_microscope", "microscope_setup", "setup_microscope")
    identifier = (experiment_id or "").casefold()
    inferred = None
    if explicit:
        inferred = (explicit, _mode_from_text(explicit))
    elif "him_epi_sd" in identifier or "spinning" in identifier:
        inferred = ("Spinning Disk", "Epifluorescence")
    elif task and task.casefold().startswith("himsd"):
        inferred = ("Spinning Disk", "Epifluorescence")
    elif generic:
        inferred = (generic, _mode_from_text(generic))
    else:
        inferred = ("Unknown", "Unknown")
    conflicts: list[str] = []
    if generic and inferred[0].casefold() != generic.casefold():
        conflicts.append(f"Microscope metadata says {generic}, but the experiment evidence indicates {inferred[0]}.")
    return inferred[0], inferred[1], tuple(conflicts)


def _mode_from_text(text: str) -> str:
    lower = text.casefold()
    if "epi" in lower:
        return "Epifluorescence"
    if "confocal" in lower:
        return "Confocal"
    return "Unknown"


def load_experiment(folder: str | Path, *, now: datetime | None = None) -> ExperimentSnapshot:
    metadata_folder = discover_metadata_folder(folder) or Path(folder).expanduser().resolve()
    discovered = discover_files(metadata_folder)
    errors: list[str] = []
    parsed: dict[str, dict] = {}
    for name in ("metadata.yml", "HiM_parameters.yml", "experiment_config.yaml"):
        if name in discovered.files:
            parsed[name], error = read_yaml(discovered.files[name])
            if error:
                errors.append(f"{name}: {error}")
    injections: dict = {}
    probe_count = None
    if "injections.yml" in discovered.files:
        injections, probe_count, error = read_injections(discovered.files["injections.yml"])
        if error:
            errors.append(f"injections.yml: {error}")
    events: list = []
    if "HiM_task.log" in discovered.files:
        events, error = read_log(discovered.files["HiM_task.log"])
        if error:
            errors.append(f"HiM_task.log: {error}")
    phase, cycle, total_cycles, current_roi, log_total_rois = infer_run_details(events)
    operation = infer_operation(events)
    task = task_class(events)
    activity = events[-1].timestamp if events and events[-1].timestamp else latest_mtime(tuple(discovered.files.values()) + discovered.output_files)
    status = classify_status(events, activity, now=now)
    metadata_file = parsed.get("metadata.yml", {})
    parameters = parsed.get("HiM_parameters.yml", {})
    config = parsed.get("experiment_config.yaml", {})
    global_params = _section(parameters, "1- global parameters", "global parameters")
    fluidic_params = _section(parameters, "2- fluidic parameters", "fluidic parameters")
    numbered_rois = _section(parameters, "4- ROIs", "ROIs")
    acquisition = _section(metadata_file, "Acquisition")
    metadata = {**parameters, **metadata_file, **config}
    experiment_id = _first_from((global_params, parameters, metadata_file), "experiment", "experiment_id", "identifier")
    microscope, mode, conflicts = _microscope(metadata_file, experiment_id, task)
    roi_count = _count_rois((acquisition, numbered_rois)) or log_total_rois
    probe_count = probe_count or _count_mapping(fluidic_params, parameters, key="probes")
    warnings = tuple(event.message for event in reversed(events) if event.level == "WARNING")
    if conflicts:
        warnings += conflicts
    if phase == "COMPLETED" and total_cycles is None:
        total_cycles = cycle
    if phase == "COMPLETED" and total_cycles is not None:
        cycle = total_cycles
    health = DataHealth(
        available=tuple(discovered.files),
        # Absence alone is not evidence of failure: these may be outputs from a
        # later phase that has not been reached. Parsing errors are different.
        not_yet_produced=discovered.missing,
        missing_or_malformed=tuple(errors),
        incomplete=("HiM_task.log has no events" if "HiM_task.log" in discovered.files and not events else "",),
    )
    health = DataHealth(health.available, health.not_yet_produced, tuple(item for item in health.missing_or_malformed if item), tuple(item for item in health.incomplete if item))
    return ExperimentSnapshot(
        folder=discovered.folder,
        name=(
            _first_from((acquisition, global_params, metadata_file, metadata), "experiment_name", "name")
            or _first_from((acquisition, global_params, metadata_file, metadata), "sample_name", "sample")
            or "Unknown"
        ),
        microscope=microscope,
        mode=mode,
        experiment_id=experiment_id,
        task_class=task,
        setup=mode,
        roi_count=roi_count,
        probe_count=probe_count,
        status=status,
        completed_cycles=cycle,
        total_cycles=total_cycles,
        elapsed_seconds=_elapsed_seconds(events),
        last_activity=activity,
        phase=phase, cycle=cycle, roi=current_roi,
        roi_name=operation["roi_name"],
        roi_progress=operation["roi_progress"],
        roi_total=operation["roi_total"],
        current_cycle=operation["cycle"],
        current_operation=operation["operation"],
        current_product=operation["product"],
        target_volume_ul=operation["volume_ul"],
        flow_rate_ul_min=operation["flow_ul_min"],
        incubation_seconds=operation["incubation_seconds"],
        last_event=events[-1].message if events else None,
        health=health,
        errors=tuple(event.message for event in events if event.level == "ERROR") + tuple(errors),
        warnings=warnings,
        conflicts=conflicts,
        raw={**metadata, "injections": injections},
    )


def _count(data: dict, *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, (list, tuple, dict)):
            return len(value)
        if isinstance(value, int):
            return value
    return None


def _count_mapping(*sections: dict, key: str) -> int | None:
    for section in sections:
        for name, value in section.items():
            if str(name).casefold() == key.casefold() and isinstance(value, (dict, list, tuple)):
                return len(value)
    return None


def _elapsed_seconds(events: list) -> float | None:
    timestamps = [event.timestamp for event in events if event.timestamp is not None]
    if len(timestamps) < 2:
        return None
    return (max(timestamps) - min(timestamps)).total_seconds()
