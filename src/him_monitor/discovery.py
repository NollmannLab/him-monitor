from __future__ import annotations

from pathlib import Path

from .model import DiscoveredFiles

EXPECTED = ("HiM_task.log", "HiM_parameters.yml", "metadata.yml", "experiment_config.yaml", "injections.yml")
SECONDARY = "experiment_parameters"


def discover_metadata_folder(start: str | Path) -> Path | None:
    """Find the closest folder containing recognizable HiM metadata."""
    path = Path(start).expanduser().resolve()
    if path.is_file():
        path = path.parent
    candidates = [path] + list(path.parents)
    for candidate in candidates:
        if any((candidate / name).is_file() for name in EXPECTED):
            return candidate
        metadata = candidate / "metadata"
        if metadata.is_dir() and any((metadata / name).is_file() for name in EXPECTED):
            return metadata
        # A selected project/parent folder may contain multiple experiment folders.
        # Keep the search bounded to descendants and choose the shallowest match.
        matches = sorted(
            (child for child in candidate.glob("**/metadata") if child.is_dir()),
            key=lambda child: len(child.relative_to(candidate).parts),
        )
        for child in matches:
            if any((child / name).is_file() for name in EXPECTED):
                return child
    return None


def discover_files(folder: str | Path) -> DiscoveredFiles:
    folder = Path(folder).expanduser().resolve()
    locations = (folder, folder / SECONDARY)
    files = {
        name: next((candidate / name for candidate in locations if (candidate / name).is_file()), folder / name)
        for name in EXPECTED
        if any((candidate / name).is_file() for candidate in locations)
    }
    outputs = tuple(sorted(p for p in folder.rglob("*") if p.is_file() and p.name not in EXPECTED))
    return DiscoveredFiles(folder, files, outputs, tuple(name for name in EXPECTED if name not in files))
