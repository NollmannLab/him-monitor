from __future__ import annotations

import argparse
import sys

from .discovery import discover_metadata_folder
from .service import load_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="him-monitor", description="Read-only HiM experiment monitor")
    parser.add_argument("folder", help="metadata, experiment, or parent folder")
    args = parser.parse_args(argv)
    folder = discover_metadata_folder(args.folder)
    if folder is None:
        parser.error(f"could not find HiM metadata in or below '{args.folder}'")
    try:
        from PySide6.QtWidgets import QApplication
        from .qt.overview import OverviewWindow
    except ImportError as exc:
        print(f"him-monitor requires PySide6: {exc}", file=sys.stderr)
        return 2
    app = QApplication(sys.argv if argv is None else ["him-monitor", *argv])
    window = OverviewWindow(load_experiment(folder))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
