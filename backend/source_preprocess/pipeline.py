import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

import requests

from .chapter_chunker import split_into_chapters
from .parsers import parse_input_to_text
from .parsers.txt_parser import normalize_text_file_to_utf8
from .text_cleaner import clean_text


def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parents[1] / "config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _safe_folder_name(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name.strip())
    return safe or "source_local"


def _resolve_file_name(file_name: str | None, source_file_id: str, source_path: str | None, file_url: str | None) -> str:
    if file_name:
        return file_name
    if source_path:
        return Path(source_path).name
    if file_url:
        parsed = urlparse(file_url)
        tail = Path(parsed.path).name
        return tail or f"{source_file_id}.txt"
    return f"{source_file_id}.txt"


def _download_to_local(file_url: str, target_path: Path) -> None:
    resp = requests.get(file_url, timeout=60)
    resp.raise_for_status()
    target_path.write_bytes(resp.content)


def process_source_file(
    source_path: str | None = None,
    source_type: str | None = "txt",
    source_file_id: str = "source_local",
    file_name: str | None = None,
    file_url: str | None = None,
    filter_noise: bool = False,
    book_id: str | None = None,
    book_title: str | None = None,
) -> dict:
    if not source_path and not file_url:
        raise ValueError("process_source_file requires either source_path or file_url")

    cfg = _load_config()
    root = Path(__file__).resolve().parents[2]
    cache_root = root / cfg["cache"]["root"]

    resolved_file_name = _resolve_file_name(file_name, source_file_id, source_path, file_url)
    resolved_book_title = book_title or Path(resolved_file_name).stem
    resolved_book_id = book_id or source_file_id
    book_folder = _safe_folder_name(f"{resolved_book_title}_{resolved_book_id}")

    book_cache_dir = cache_root / book_folder
    source_input_dir = book_cache_dir / "source_input"
    unified_dir = book_cache_dir / "unified_format"
    chapter_dir = book_cache_dir / "chapter_content_text"

    source_input_dir.mkdir(parents=True, exist_ok=True)
    unified_dir.mkdir(parents=True, exist_ok=True)
    chapter_dir.mkdir(parents=True, exist_ok=True)

    local_source_path = source_input_dir / resolved_file_name
    if file_url:
        _download_to_local(file_url, local_source_path)
    elif source_path:
        src = Path(source_path)
        if src.resolve() != local_source_path.resolve():
            shutil.copy2(src, local_source_path)

    resolved_source_type = (source_type or local_source_path.suffix.lstrip(".") or "txt").lower()
    if resolved_source_type in {"txt", "md"}:
        normalize_text_file_to_utf8(local_source_path)

    raw_text = parse_input_to_text(str(local_source_path), source_type=resolved_source_type)
    cleaned_text = clean_text(raw_text)

    unified_name = f"{source_file_id}.txt"
    unified_path = unified_dir / unified_name
    unified_path.write_text(cleaned_text, encoding="utf-8")

    chapters = split_into_chapters(cleaned_text, filter_noise=filter_noise)
    chapter_records: list[dict] = []

    for idx, chapter in enumerate(chapters, start=1):
        chapter_file_name = f"{source_file_id}_chapter_{idx:04d}.txt"
        chapter_path = chapter_dir / chapter_file_name
        chapter_path.write_text(chapter["content"], encoding="utf-8")

        chapter_records.append(
            {
                "chapter_no": idx,
                "chapter_title": chapter["title"],
                "chapter_range": "",
                "word_count": len(chapter["content"]),
                "content_text_url": str(chapter_path.as_posix()),
                "content_text": chapter["content"],
            }
        )

    return {
        "source_file_id": source_file_id,
        "source_type": resolved_source_type,
        "file_name": resolved_file_name,
        "local_source_url": str(local_source_path.as_posix()),
        "cache_folder": str(book_cache_dir.as_posix()),
        "unified_format_url": str(unified_path.as_posix()),
        "chapters": chapter_records,
    }
