from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path


def chapter_output_directory(database, book_id: str) -> Path:
    safe_id = "".join(char for char in book_id if char.isalnum() or char in "-_")
    if not safe_id:
        raise ValueError("Invalid book id")
    root_database = getattr(database, "parent", database)
    return Path(root_database.path).resolve().parent / "novel" / safe_id


def chapter_output_paths(database, book_id: str, chapter_count: int) -> list[Path]:
    directory = chapter_output_directory(database, book_id) / "chapters"
    return [directory / f"{index:04d}.txt" for index in range(1, chapter_count + 1)]


def save_chapter_outputs(database, book_id: str, cleaned_text: str, chapters: list[dict]) -> list[str]:
    target = chapter_output_directory(database, book_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    chapter_dir = staging / "chapters"
    chapter_dir.mkdir(parents=True)

    try:
        (staging / "unified.txt").write_text(cleaned_text, encoding="utf-8")
        manifest = []
        paths = []
        for index, chapter in enumerate(chapters, start=1):
            filename = f"{index:04d}.txt"
            (chapter_dir / filename).write_text(chapter["content"], encoding="utf-8")
            paths.append(str((target / "chapters" / filename).resolve()))
            manifest.append(
                {
                    "chapter_no": index,
                    "title": chapter["title"],
                    "source_start": chapter["source_start"],
                    "source_end": chapter["source_end"],
                    "split_method": chapter["split_method"],
                    "confidence": chapter["confidence"],
                    "text_path": paths[-1],
                }
            )
        (staging / "chapters.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        target.mkdir(parents=True, exist_ok=True)
        os.replace(staging / "unified.txt", target / "unified.txt")
        if (target / "chapters").exists():
            shutil.rmtree(target / "chapters")
        os.replace(staging / "chapters", target / "chapters")
        os.replace(staging / "chapters.json", target / "chapters.json")
        return paths
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def remove_chapter_outputs(database, book_id: str) -> None:
    target = chapter_output_directory(database, book_id)
    if target.exists():
        shutil.rmtree(target)
