# him-monitor

`him-monitor` is a read-only desktop overview for long HiM microscope experiments. It is independent of Qudi hardware and GUI modules and does not modify experiment files.

## Installation with `uv`

The recommended development workflow uses [`uv`](https://docs.astral.sh/uv/). It creates and manages an isolated `.venv` for this project, installs the package in editable mode, and keeps the application dependencies separate from Qudi and system Python environments.

Check that `uv` is available:

```bash
uv --version
```

If it is not installed, follow the official [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/).

From the `him-monitor` repository directory, create the environment and install the application together with its test dependencies:

```bash
cd /home/jb/Repositories/him-monitor
uv sync --extra test
```

The first run creates `.venv/` automatically. It also installs the project in editable mode, so source-code changes are immediately available to the commands run through `uv`.

You do not need to activate the environment when using `uv run`:

```bash
uv run pytest
```

If you prefer to activate the environment for an interactive shell, use:

```bash
source .venv/bin/activate
pytest
```

The `.venv/` directory is local environment state and should not be committed to the repository.

### Python and platform compatibility

The project supports Python 3.10, 3.11, 3.12, and 3.13. The Qt dependency is pinned to PySide6 6.9.3, together with matching PySide6 Addons, PySide6 Essentials, and Shiboken6 packages.

PySide6 6.9.3 was selected instead of the newer releases because its Linux x86_64 wheels use the `manylinux_2_28` tag. They are compatible with Linux systems providing glibc 2.28 or newer, including `manylinux_2_31_x86_64`, without requiring an operating-system or glibc upgrade. The same release provides the Python 3.13-compatible `cp39-abi3` wheel and matching macOS and Windows wheels.

Newer PySide6 releases may require a newer Linux baseline. Keep the pinned version unless the platform wheel compatibility has been checked again.

## Launching the monitor

Launch an experiment overview with:

```bash
uv run him-monitor /path/to/folder
```

The folder argument can be any of the following:

- the metadata folder itself;
- the experiment folder containing a `metadata/` directory; or
- a parent folder from which a metadata folder can be discovered.

For example:

```bash
uv run him-monitor /data/experiments/experiment-001
```

After activating `.venv`, the equivalent command is:

```bash
him-monitor /data/experiments/experiment-001
```

The monitor searches for recognizable files including `HiM_task.log`, `HiM_parameters.yml`, `metadata.yml`, `experiment_config.yaml`, and `injections.yml`. If no such files can be found, it exits with an error explaining that the folder is not recognized as a HiM experiment.

The argument may be the metadata directory, an experiment directory containing `metadata/`, or a parent directory. The monitor searches for `HiM_task.log`, `HiM_parameters.yml`, `metadata.yml`, `experiment_config.yaml`, and `injections.yml`.

The first milestone provides an overview with experiment identity, setup, ROI/probe counts, status, inferred position, timestamps, selected folder, and data-health information. Status classification is deliberately conservative: absent files are not treated as failures, while errors, terminal messages, and stale activity are surfaced as evidence.

## Supported layouts and limitations

Metadata may be directly in the selected folder or in a `metadata/` child folder. The application currently reads YAML and plain-text logs and does not control hardware, rewrite metadata, or import the full Qudi application. Elapsed-time inference and richer CSV parsing will be expanded as real format examples are formalized.

Fluidics cycle/injection tables and plots, live autofocus heatmaps, autofocus drift visualization, and accelerated replay are intentionally not implemented yet. The Qt overview is kept separate from readers so these can be added as independent panels later.

Run tests with:

```bash
uv run pytest
```
