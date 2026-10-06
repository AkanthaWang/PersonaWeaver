"""
Reusable smoke test for remote sync operations.
Verifies end-to-end remote persistence to Supabase and Aliyun OSS.

Usage:
    python -m backend.remote_sync.run_remote_sync_smoke
    
    With custom parameters (via env):
    CUSTOM_BOOK_ID=b_test python -m backend.remote_sync.run_remote_sync_smoke
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Add workspace root to path for imports
workspace_root = Path(__file__).resolve().parents[2]
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from backend.remote_persistence import (
    create_extraction_task,
    persist_card_rows,
    persist_l0_l1_rows,
    persist_l2_rows,
    persist_summary_rows,
    update_extraction_task,
)


def run_remote_sync_smoke_test(
    user_id: str = "u_demo_001",
    book_id: str = "b_demo_001",
    source_file_id: str = "test_sf_test_fullchain_002",
    cache_base_dir: str | Path = None,
    skip_remote: bool = False,
) -> dict[str, Any]:
    """
    Run smoke test for remote sync pipeline.
    
    Args:
        user_id: User identifier
        book_id: Book identifier
        source_file_id: Source file identifier
        cache_base_dir: Base directory containing L0/L1/L2/summary/card cache
        skip_remote: If True, skip remote operations (local cache verification only)
    
    Returns:
        Dictionary with task IDs and upload counts
    """
    if cache_base_dir is None:
        # Default to standard project structure
        workspace_root = Path(__file__).resolve().parents[2]
        cache_base_dir = workspace_root / "local_cache" / source_file_id
    else:
        cache_base_dir = Path(cache_base_dir)

    if not cache_base_dir.exists():
        raise FileNotFoundError(f"Cache directory not found: {cache_base_dir}")

    print(f"[Cache] {cache_base_dir}")
    print(f"[User] {user_id}, [Book] {book_id}")
    print(f"[Skip Remote] {skip_remote}")
    print("-" * 60)

    result = {
        "chapter_task_id": None,
        "summary_task_id": None,
        "card_task_id": None,
        "l0_l1": {},
        "l2": {},
        "summary": {},
        "card": {},
    }

    if skip_remote:
        print("[SKIPPING] Remote operations (local verification only)")
        print("-" * 60)
        result["status"] = "local_verified"
        return result

    # === L0/L1: Chapter persistence ===
    chapter_task_id = None
    try:
        chapter_json_dir = cache_base_dir / "chapter_extractions"
        if chapter_json_dir.exists():
            chapter_task_id = create_extraction_task(
                user_id=user_id,
                book_id=book_id,
                task_type="chapter", status="running", progress=10
            )
            print(f"[+] Chapter task created: ID={chapter_task_id}")

            persisted_l0_l1 = persist_l0_l1_rows(
                chapter_json_dir=chapter_json_dir.as_posix(),
                user_id=user_id,
                book_id=book_id,
                source_file_id=source_file_id,
            )
            result["l0_l1"] = persisted_l0_l1
            print(f"[+] L0/L1 uploaded: {persisted_l0_l1}")

            if chapter_task_id:
                result["chapter_task_id"] = chapter_task_id
                update_extraction_task(
                    task_id=chapter_task_id, status="completed", progress=100
                )
                print(f"[+] Chapter task completed: ID={chapter_task_id}")
        else:
            print(f"[INFO] Chapter cache not found: {chapter_json_dir}")
    except Exception as e:
        print(f"[ERROR] L0/L1 error: {e}")

    # === L2: Chapter extractions (structured data) ===
    l2_task_id = None
    try:
        l2_dir = cache_base_dir / "chapter_extractions"
        if l2_dir.exists():
            l2_task_id = create_extraction_task(
                user_id=user_id,
                book_id=book_id,
                task_type="extraction", status="running", progress=30
            )
            print(f"[+] L2 task created: ID={l2_task_id}")

            persisted_l2 = persist_l2_rows(
                chapter_extraction_json_dir=l2_dir.as_posix(),
                user_id=user_id,
                book_id=book_id,
                source_file_id=source_file_id,
            )
            result["l2"] = persisted_l2
            print(f"[+] L2 uploaded: {persisted_l2['uploaded_extraction_count']} extractions")
            if persisted_l2.get("uploaded_extractions"):
                for ext in persisted_l2["uploaded_extractions"][:2]:
                    print(f"  - {ext['extractor_type']}: {ext['oss_url']}")

            if l2_task_id:
                update_extraction_task(task_id=l2_task_id, status="completed", progress=100)
                print(f"[+] L2 task completed: ID={l2_task_id}")
        else:
            print(f"[INFO] L2 cache not found: {l2_dir}")
    except Exception as e:
        print(f"[ERROR] L2 error: {e}")

    # === Summary ===
    summary_task_id = None
    try:
        summary_root_dir = cache_base_dir / "summary"
        if summary_root_dir.exists():
            summary_task_id = create_extraction_task(
                user_id=user_id,
                book_id=book_id,
                task_type="summary", status="running", progress=60
            )
            print(f"[+] Summary task created: ID={summary_task_id}")

            # Collect all summary rows from new directory structure
            summary_rows = []
            
            # Try new structure: summary/{dimension}/{dimension}.{json,md}
            for type_dir in summary_root_dir.iterdir():
                if type_dir.name in {"summary_json", "summary_md"}:
                    # Skip old structure folders
                    continue
                if not type_dir.is_dir():
                    continue
                summary_type = type_dir.name
                json_file = type_dir / f"{summary_type}.json"
                md_file = type_dir / f"{summary_type}.md"

                if json_file.exists():
                    summary_rows.append({
                        "dimension": summary_type,
                        "content_url": json_file.as_posix(),
                        "content_kind": "json",
                    })
                    continue

                if md_file.exists():
                    summary_rows.append({
                        "dimension": summary_type,
                        "content_url": md_file.as_posix(),
                        "content_kind": "md",
                    })
            
            # Fallback to old structure if needed (for backward compatibility)
            if not summary_rows:
                old_json_dir = summary_root_dir / "summary_json"
                old_md_dir = summary_root_dir / "summary_md"
                
                if old_json_dir.exists() and old_md_dir.exists():
                    print("[INFO] Using legacy summary structure (summary_json/summary_md)")
                    for json_file in old_json_dir.glob("*.json"):
                        # Extract dimension from filename: {source_file_id}_{dimension}.json
                        parts = json_file.stem.split("_", 1)
                        if len(parts) == 2:
                            summary_type = parts[1]
                            md_file = old_md_dir / f"{json_file.stem}.md"
                            if md_file.exists():
                                summary_rows.append({
                                    "dimension": summary_type,
                                    "content_url": md_file.as_posix(),
                                    "content_kind": "md",
                                })

            if summary_rows:
                persisted_summary = persist_summary_rows(
                    summary_rows=summary_rows,
                    user_id=user_id,
                    book_id=book_id,
                    source_file_id=source_file_id,
                )
                result["summary"] = persisted_summary
                print(f"[+] Summary uploaded: {persisted_summary['uploaded_summary_count']} types")

                if summary_task_id:
                    result["summary_task_id"] = summary_task_id
                    update_extraction_task(
                        task_id=summary_task_id, status="completed", progress=100
                    )
                    print(f"[+] Summary task completed: ID={summary_task_id}")
            else:
                print("[INFO] No summary data found")
        else:
            print(f"[INFO] Summary cache not found: {summary_root_dir}")
    except Exception as e:
        print(f"[ERROR] Summary error: {e}")

    # === Card ===
    card_task_id = None
    try:
        card_root_dir = cache_base_dir / "card"
        if card_root_dir.exists():
            card_task_id = create_extraction_task(
                user_id=user_id,
                book_id=book_id,
                task_type="card", status="running", progress=80
            )
            print(f"[+] Card task created: ID={card_task_id}")

            # New card layout: card/{source_file_id}_{character}_{dimension}/card.md
            card_rows = []
            for card_dir in card_root_dir.iterdir():
                if not card_dir.is_dir():
                    continue
                md_file = card_dir / "card.md"
                if md_file.exists():
                    character_name = card_dir.name
                    card_type = "character_card"
                    try:
                        content = md_file.read_text(encoding="utf-8")
                        first_line = content.splitlines()[0].strip() if content else ""
                        if first_line.startswith("#"):
                            card_type = first_line.lstrip("#").strip().split(" - ")[-1] or card_type
                    except Exception:
                        pass
                    card_rows.append({
                        "content_url": md_file.as_posix(),
                        "content_kind": "md",
                        "character_name": character_name,
                        "dimension": card_type,
                    })

            if card_rows:
                persisted_card = persist_card_rows(
                    card_rows=card_rows,
                    user_id=user_id,
                    book_id=book_id,
                    source_file_id=source_file_id,
                    character_name=list(set(r["character_name"] for r in card_rows))[0],
                )
                result["card"] = persisted_card
                print(f"[+] Card uploaded: {persisted_card['uploaded_card_count']} cards")
            else:
                print("[INFO] No card data found")

            if card_task_id:
                result["card_task_id"] = card_task_id
                update_extraction_task(task_id=card_task_id, status="completed", progress=100)
                print(f"[+] Card task completed: ID={card_task_id}")
        else:
            print(f"[INFO] Card cache not found: {card_root_dir}")
    except Exception as e:
        print(f"[ERROR] Card error: {e}")

    # Summary
    print("-" * 60)
    print("[RESULT] Remote Sync Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return result


if __name__ == "__main__":
    # Support environment variable overrides
    user_id = os.getenv("CUSTOM_USER_ID", "u_demo_001")
    book_id = os.getenv("CUSTOM_BOOK_ID", "b_demo_001")
    source_file_id = os.getenv("CUSTOM_SOURCE_FILE_ID", "test_sf_test_fullchain_002")
    skip_remote = os.getenv("SKIP_REMOTE", "false").lower() == "true"

    result = run_remote_sync_smoke_test(
        user_id=user_id,
        book_id=book_id,
        source_file_id=source_file_id,
        skip_remote=skip_remote,
    )

    # Exit with success code
    sys.exit(0)
