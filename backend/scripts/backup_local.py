"""Create a consistent SQLite snapshot, including committed WAL transactions."""
import argparse
from datetime import datetime
from pathlib import Path
import sqlite3

from backend.app.core.config import Config


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError("Database does not exist; start the backend first.")
    if destination.exists():
        raise ValueError("Backup destination already exists.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(destination) as snapshot:
                original.backup(snapshot)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def main():
    config = Config.from_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or config.data_dir / "backups" / f"personaweaver-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
    main_snapshot = backup(config.database_path, destination)
    print(main_snapshot)
    novel_root = config.data_dir / "novel"
    for source in sorted(novel_root.glob("*/extraction.sqlite3")):
        book_snapshot = destination.parent / f"{destination.stem}-{source.parent.name}-extraction.sqlite3"
        print(backup(source, book_snapshot))


if __name__ == "__main__":
    main()
