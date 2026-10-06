from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


ROOT_DIR = Path(__file__).resolve().parents[2]
ROOT_STR = str(ROOT_DIR)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

from backend.remote_persistence import _connect_with_fallback, _resolve_db_url


def _write_json_payload(payload: str, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        parsed = json.loads(payload)
        target_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        target_path.write_text(payload, encoding="utf-8")


def _fetch_extraction_payload(reference: str) -> str:
    reference = (reference or "").strip()
    if not reference:
        raise ValueError("empty extraction reference")

    parsed = urlparse(reference)
    if parsed.scheme in {"http", "https"}:
        resp = requests.get(reference, timeout=60)
        resp.raise_for_status()
        return resp.text

    path = Path(reference)
    if path.exists():
        return path.read_text(encoding="utf-8", errors="ignore")

    raise FileNotFoundError(f"extraction reference not reachable: {reference}")


def pull_remote_extractions(*, book_id: str | None, source_file_id: str, output_dir: Path | None = None, db_url: str | None = None) -> list[Path]:
    resolved_db_url = _resolve_db_url(db_url)
    cache_root = output_dir or (ROOT_DIR / "local_cache" / "pulled_extractions" / source_file_id)
    saved_paths: list[Path] = []

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            rows = []
            if book_id:
                cur.execute(
                    """
                    select c.chapter_no, c.chapter_title, ce.chapter_id, ce.extraction_json_url
                    from public.chapter_extractions ce
                    join public.chapters c on c.id = ce.chapter_id
                    where ce.book_id = %s and ce.chapter_id like %s
                    order by c.chapter_no
                    """,
                    (book_id, f"ch_{source_file_id}_%"),
                )
                rows = cur.fetchall()

            if not rows:
                cur.execute(
                    """
                    select c.chapter_no, c.chapter_title, ce.chapter_id, ce.extraction_json_url
                    from public.chapter_extractions ce
                    join public.chapters c on c.id = ce.chapter_id
                    where ce.chapter_id like %s
                    order by c.chapter_no
                    """,
                    (f"ch_{source_file_id}_%",),
                )
                rows = cur.fetchall()

    for chapter_no, chapter_title, chapter_id, extraction_json_url in rows:
        payload = _fetch_extraction_payload(str(extraction_json_url))
        file_name = f"{source_file_id}_chapter_{int(chapter_no):04d}.json"
        target_path = cache_root / file_name
        _write_json_payload(payload, target_path)
        saved_paths.append(target_path)

    return saved_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull chapter extraction JSON files referenced in remote Supabase to local cache.")
    parser.add_argument("--book-id", default="b_demo_001")
    parser.add_argument("--source-file-id", default="sf_remote_demo_001")
    parser.add_argument("--output-dir", default=str(ROOT_DIR / "local_cache" / "pulled_extractions" / "sf_remote_demo_001"))
    args = parser.parse_args()

    saved_paths = pull_remote_extractions(
        book_id=args.book_id,
        source_file_id=args.source_file_id,
        output_dir=Path(args.output_dir),
    )

    print(json.dumps([path.as_posix() for path in saved_paths], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()