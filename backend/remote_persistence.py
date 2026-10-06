import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import psycopg2
from dotenv import load_dotenv
from psycopg2 import Error as PsycopgError
from psycopg2 import OperationalError

try:
    import oss2
    _OSS2_IMPORT_ERROR = ""
except Exception as _exc:  # pragma: no cover - optional dependency for OSS upload
    oss2 = None
    _OSS2_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"
    import traceback as _tb
    print("[oss2 import failed]", _OSS2_IMPORT_ERROR, flush=True)
    _tb.print_exc()


def _normalize_source_type_for_db(source_type: str) -> str:
    value = (source_type or "txt").lower()
    if value in {"epub", "txt", "pdf", "image"}:
        return value
    if value in {"jpg", "jpeg", "heic", "heif", "png", "webp"}:
        return "image"
    return "txt"


def _safe_text_hash(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8", errors="ignore")).hexdigest()


def _safe_file_name(name: str) -> str:
    sanitized = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in (name or "").strip())
    return sanitized or "unknown"


def _resolve_db_url(explicit_db_url: str | None = None) -> str:
    root_dir = Path(__file__).resolve().parents[1]
    load_dotenv(root_dir / ".env")
    load_dotenv(root_dir / "database" / ".env")

    db_url = explicit_db_url or os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("Missing SUPABASE_DB_URL or DATABASE_URL for remote persistence")
    return db_url


def _build_supabase_pooler_url(db_url: str) -> str | None:
    explicit_pooler = os.getenv("SUPABASE_POOLER_DB_URL")
    if explicit_pooler:
        return explicit_pooler

    parsed = urlparse(db_url)
    host = parsed.hostname or ""
    if not host.startswith("db.") or not host.endswith(".supabase.co"):
        return None

    project_ref = host.split(".")[1]
    if not project_ref:
        return None

    pooler_host = os.getenv("SUPABASE_POOLER_HOST", "aws-1-ap-southeast-1.pooler.supabase.com")
    pooler_port = int(os.getenv("SUPABASE_POOLER_PORT", "6543"))

    user = parsed.username or "postgres"
    if user == "postgres":
        user = f"postgres.{project_ref}"

    password = parsed.password or ""
    db_name = parsed.path.lstrip("/") or "postgres"
    query = parsed.query or urlencode({"sslmode": "require"})
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{pooler_host}:{pooler_port}"
    return f"postgresql://{netloc}/{db_name}?{query}"


def _raw_connect(db_url: str):
    try:
        return psycopg2.connect(db_url)
    except OperationalError as exc:
        msg = str(exc).lower()
        if "could not translate host name" not in msg:
            raise

        pooler_url = _build_supabase_pooler_url(db_url)
        if not pooler_url:
            raise

        return psycopg2.connect(pooler_url)


@contextmanager
def _connect_with_fallback(db_url: str):
    """连接上下文管理器：提交/回滚事务后**务必关闭连接**。

    Supabase transaction 模式 pooler(6543) 连接数很紧，psycopg2 原生
    `with conn` 只提交不关闭，频繁调用会耗尽 pooler 连接导致卡死。
    这里统一在退出时 close，修复所有调用点的连接泄漏。
    """
    conn = _raw_connect(db_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _build_oss_client() -> tuple[Any, str]:
    endpoint = os.getenv("OSS_ENDPOINT") or os.getenv("VITE_OSS_ENDPOINT")
    bucket_name = os.getenv("OSS_BUCKET") or os.getenv("VITE_OSS_BUCKET")
    bucket_host = os.getenv("OSS_BUCKET_HOST") or os.getenv("VITE_OSS_BUCKET_HOST")
    access_key_id = os.getenv("OSS_ACCESS_KEY_ID") or os.getenv("VITE_OSS_ACCESS_KEY_ID")
    access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET") or os.getenv("VITE_OSS_ACCESS_KEY_SECRET")

    if not endpoint or not bucket_name or not access_key_id or not access_key_secret:
        raise RuntimeError(
            "Missing OSS config. Required: OSS_ENDPOINT/OSS_BUCKET/OSS_ACCESS_KEY_ID/OSS_ACCESS_KEY_SECRET"
        )

    if oss2 is None:
        raise RuntimeError(f"Missing oss2 package. Import error: {_OSS2_IMPORT_ERROR}")

    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, f"https://{endpoint}", bucket_name)
    resolved_host = bucket_host or f"{bucket_name}.{endpoint}"
    return bucket, resolved_host


def _upload_file_to_oss(local_file_path: str | Path, object_key: str) -> str:
    bucket, bucket_host = _build_oss_client()
    key = object_key.strip("/")
    local_path = Path(local_file_path)
    if not local_path.exists():
        raise FileNotFoundError(f"OSS upload source file not found: {local_path}")

    bucket.put_object_from_file(key, str(local_path))
    return f"https://{bucket_host}/{quote(key, safe='/._-')}"


def _object_prefix(*parts: str) -> str:
    return "/".join(_safe_file_name(part) for part in parts if part)


def create_extraction_task(
    *,
    user_id: str,
    book_id: str,
    task_type: str,
    status: str,
    progress: int,
    error_message: str | None = None,
    db_url: str | None = None,
) -> int | None:
    resolved_db_url = _resolve_db_url(db_url)

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO public.extraction_tasks (
                        user_id, book_id, task_type, status, progress, error_message
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, book_id, task_type, status, int(progress), error_message),
                )
                return int(cur.fetchone()[0])
            except PsycopgError as exc:
                # New schema may not include extraction_tasks; keep remote pipeline running.
                conn.rollback()
                if getattr(exc, "pgcode", None) == "42P01":
                    return None
                raise


def update_extraction_task(
    *,
    task_id: int | None,
    status: str,
    progress: int,
    error_message: str | None = None,
    db_url: str | None = None,
) -> None:
    if task_id is None:
        return

    resolved_db_url = _resolve_db_url(db_url)

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    UPDATE public.extraction_tasks
                    SET status = %s,
                        progress = %s,
                        error_message = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (status, int(progress), error_message, int(task_id)),
                )
            except PsycopgError as exc:
                conn.rollback()
                if getattr(exc, "pgcode", None) == "42P01":
                    return
                raise


def create_task_log(
    *,
    task_id: int | str | None,
    user_id: str,
    level: str,
    message: str,
    detail_json: dict[str, Any] | list[Any] | None = None,
    db_url: str | None = None,
) -> int | None:
    resolved_db_url = _resolve_db_url(db_url)

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO public.task_logs (
                        task_id, user_id, level, message, detail_json
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        str(task_id) if task_id is not None else None,
                        user_id,
                        str(level or "info").lower(),
                        message,
                        json.dumps(detail_json, ensure_ascii=False) if detail_json is not None else None,
                    ),
                )
                return int(cur.fetchone()[0])
            except PsycopgError as exc:
                conn.rollback()
                if getattr(exc, "pgcode", None) == "42P01":
                    return None
                raise


def _upsert_user_and_book(
    *,
    cur,
    user_id: str,
    username: str,
    book_id: str,
    book_title: str,
    source_type: str,
    book_status: str,
    book_file_url: str,
    err_message: str | None = None,
) -> None:
    # 用户由登录系统（Supabase auth）管理，提取流程不应改动其 username，
    # 否则会撞 users_username_key 唯一约束（把当前用户的 username 更新成别人已占用的值）。
    # 已存在（user_id 或 username 任一冲突）则什么都不做，仅新用户才插入占位行。
    cur.execute(
        """
        INSERT INTO public.users (user_id, username, password_hash)
        SELECT %s, %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM public.users WHERE user_id = %s)
        ON CONFLICT DO NOTHING
        """,
        (user_id, username, "local_placeholder_hash", user_id),
    )

    cur.execute(
        """
        INSERT INTO public.books (
            book_id, user_id, title, source_type, status, book_file_url, err_message
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (book_id) DO UPDATE
        SET title = EXCLUDED.title,
            source_type = EXCLUDED.source_type,
            status = EXCLUDED.status,
            book_file_url = EXCLUDED.book_file_url,
            err_message = EXCLUDED.err_message,
            updated_at = now()
        """,
        (book_id, user_id, book_title, source_type, book_status, book_file_url, err_message),
    )


def mark_book_status(
    *,
    book_id: str,
    status: str,
    progress: int | None = None,
    db_url: str | None = None,
) -> None:
    resolved_db_url = _resolve_db_url(db_url)

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            if progress is not None:
                cur.execute(
                    """
                    UPDATE public.books
                    SET status = %s,
                        progress = %s,
                        updated_at = now()
                    WHERE book_id = %s
                    """,
                    (status, int(progress), book_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE public.books
                    SET status = %s,
                        updated_at = now()
                    WHERE book_id = %s
                    """,
                    (status, book_id),
                )


def initialize_remote_processing(
    *,
    source_file_row: dict[str, Any],
    user_id: str,
    username: str,
    book_id: str,
    book_title: str,
    source_file_id: str,
    db_url: str | None = None,
) -> dict[str, Any]:
    resolved_db_url = _resolve_db_url(db_url)

    source_type = _normalize_source_type_for_db(str(source_file_row.get("source_type", "txt")))
    local_source_url = str(source_file_row.get("local_source_url") or source_file_row.get("unified_format_url") or "")
    book_file_url = local_source_url or str(source_file_row.get("unified_format_url") or "") or f"local://{source_file_id}"

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            _upsert_user_and_book(
                cur=cur,
                user_id=user_id,
                username=username,
                book_id=book_id,
                book_title=book_title,
                source_type=source_type,
                book_status="parsing",
                book_file_url=book_file_url,
            )

    chapter_task_id = create_extraction_task(
        user_id=user_id,
        book_id=book_id,
        task_type="chapter_extraction",
        status="running",
        progress=5,
        db_url=resolved_db_url,
    )

    return {"chapter_task_id": chapter_task_id}


def mark_source_processing_failed(
    *,
    source_file_id: str,
    book_id: str,
    task_id: int | None,
    error_message: str,
    db_url: str | None = None,
) -> None:
    resolved_db_url = _resolve_db_url(db_url)

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.books
                SET status = 'failed',
                    err_message = %s,
                    updated_at = now()
                WHERE book_id = %s
                """,
                (error_message[:2000], book_id),
            )

    update_extraction_task(
        task_id=task_id,
        status="failed",
        progress=0,
        error_message=error_message[:2000],
        db_url=resolved_db_url,
    )


def persist_l0_l1_rows(
    source_file_row: dict[str, Any],
    chapter_rows: list[dict[str, Any]],
    *,
    user_id: str,
    book_id: str,
    source_file_id: str,
    username: str,
    book_title: str,
    db_url: str | None = None,
) -> dict[str, Any]:
    resolved_db_url = _resolve_db_url(db_url)

    source_type = _normalize_source_type_for_db(str(source_file_row.get("source_type", "txt")))
    unified_format_url = str(source_file_row.get("unified_format_url", ""))
    local_source_url = str(source_file_row.get("local_source_url") or unified_format_url)
    file_name = str(source_file_row.get("file_name") or f"{source_file_id}.txt")
    book_file_url = local_source_url or unified_format_url or f"local://{source_file_id}/{file_name}"

    inserted_chapters = 0
    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            _upsert_user_and_book(
                cur=cur,
                user_id=user_id,
                username=username,
                book_id=book_id,
                book_title=book_title,
                source_type=source_type,
                book_status="parsing",
                book_file_url=book_file_url,
            )

            # Updated remote schema keeps L1 chapters in local cache; no chapter table write here.
            inserted_chapters = 0

    return {
        "user_id": user_id,
        "book_id": book_id,
        "source_file_id": source_file_id,
        "uploaded_chapter_count": inserted_chapters,
    }


def persist_l2_rows(
    chapter_extraction_rows: list[dict[str, Any]],
    *,
    user_id: str,
    book_id: str,
    source_file_id: str,
    model_name: str | None = None,
    prompt_version: str | None = None,
    cache_folder: str | None = None,
    oss_prefix: str = "charpick",
    db_url: str | None = None,
) -> dict[str, Any]:
    resolved_db_url = _resolve_db_url(db_url)
    source_rows = sorted(
        chapter_extraction_rows,
        key=lambda item: int(item.get("chapter_no", 0)),
    )

    extractor_map = {
        "character": "characters",
        "plot": "plot",
        "item": "items",
        "location": "world",
    }

    merged_by_type: dict[str, dict[str, Any]] = {}
    for extractor_type in extractor_map:
        merged_by_type[extractor_type] = {
            "book_id": book_id,
            "source_file_id": source_file_id,
            "extractor_type": extractor_type,
            "model_name": model_name,
            "prompt_version": prompt_version,
            "chapters": [],
        }
    merged_by_type["full"] = {
        "book_id": book_id,
        "source_file_id": source_file_id,
        "extractor_type": "full",
        "model_name": model_name,
        "prompt_version": prompt_version,
        "chapters": [],
    }

    for row in source_rows:
        chapter_no = int(row.get("chapter_no", 0))
        chapter_title = str(row.get("chapter_title", ""))
        extraction_path = Path(str(row.get("extraction_json_url", "")))
        if not extraction_path.exists():
            continue

        payload = json.loads(extraction_path.read_text(encoding="utf-8"))
        merged_by_type["full"]["chapters"].append(
            {
                "chapter_no": chapter_no,
                "chapter_title": chapter_title,
                "data": payload,
            }
        )

        for extractor_type, key in extractor_map.items():
            value = payload.get(key)
            if value in (None, "", [], {}, ()):
                continue
            merged_by_type[extractor_type]["chapters"].append(
                {
                    "chapter_no": chapter_no,
                    "chapter_title": chapter_title,
                    "data": value,
                }
            )

    merged_output_dir: Path
    if cache_folder:
        merged_output_dir = Path(cache_folder) / "merged_extraction_json"
    else:
        merged_output_dir = Path("local_cache") / f"{source_file_id}_merged"
    merged_output_dir.mkdir(parents=True, exist_ok=True)

    uploaded_records: list[dict[str, str]] = []
    inserted_extractions = 0
    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            for extractor_type, merged_payload in merged_by_type.items():
                if not merged_payload["chapters"]:
                    continue

                local_file_path = merged_output_dir / f"{source_file_id}_{extractor_type}.json"
                local_file_path.write_text(
                    json.dumps(merged_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                object_key = _object_prefix(
                    oss_prefix,
                    user_id,
                    book_id,
                    source_file_id,
                    "chapter_extractions",
                    f"{extractor_type}.json",
                )
                oss_url = _upload_file_to_oss(local_file_path, object_key)

                extraction_id = f"ce_{book_id}_{extractor_type}"
                cur.execute(
                    """
                    INSERT INTO public.chapter_extractions (
                        id, user_id, book_id, extractor_type,
                        book_extraction_json_local_url, book_extraction_json_oss_url
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET extractor_type = EXCLUDED.extractor_type,
                        book_extraction_json_local_url = EXCLUDED.book_extraction_json_local_url,
                        book_extraction_json_oss_url = EXCLUDED.book_extraction_json_oss_url
                    """,
                    (
                        extraction_id,
                        user_id,
                        book_id,
                        extractor_type,
                        local_file_path.as_posix(),
                        oss_url,
                    ),
                )
                inserted_extractions += 1
                uploaded_records.append(
                    {
                        "extractor_type": extractor_type,
                        "local_url": local_file_path.as_posix(),
                        "oss_url": oss_url,
                    }
                )

    return {
        "user_id": user_id,
        "book_id": book_id,
        "source_file_id": source_file_id,
        "uploaded_extraction_count": inserted_extractions,
        "uploaded_extractions": uploaded_records,
        "merged_output_dir": merged_output_dir.as_posix(),
    }


def persist_summary_rows(
    summary_rows: list[dict[str, Any]],
    *,
    user_id: str,
    book_id: str,
    source_file_id: str,
    oss_prefix: str = "charpick",
    db_url: str | None = None,
) -> dict[str, Any]:
    resolved_db_url = _resolve_db_url(db_url)
    inserted_rows = 0
    uploaded_records: list[dict[str, str]] = []

    display_name_map = {
        "characters": "角色总表",
        "items": "物品总表",
        "storyline_events": "剧情时间线",
        "world_locations": "世界观/地点表",
    }
    file_name_map = {
        "characters": "all_characters.json",
        "items": "items.json",
        "storyline_events": "storyline_events.md",
        "world_locations": "world_locations.md",
    }

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            for row in summary_rows:
                summary_type = str(row.get("dimension", "")).strip()
                if not summary_type:
                    continue

                content_path_str = str(row.get("content_url", "") or row.get("json_url", "") or row.get("md_url", ""))
                content_kind = str(row.get("content_kind", "")).strip()
                content_path = Path(content_path_str)
                if not content_path.exists():
                    continue

                if not content_kind:
                    content_kind = "json" if content_path.suffix.lower() == ".json" else "md"

                summary_prefix = _object_prefix(
                    oss_prefix,
                    user_id,
                    book_id,
                    source_file_id,
                    "summary",
                    summary_type,
                )

                child_uploads: list[dict[str, str]] = []
                if summary_type == "characters" and content_path.suffix.lower() == ".json":
                    try:
                        index_payload = json.loads(content_path.read_text(encoding="utf-8"))
                    except Exception:
                        index_payload = []

                    if isinstance(index_payload, list):
                        changed = False
                        for entry in index_payload:
                            if not isinstance(entry, dict):
                                continue
                            local_url = str(entry.get("summary_local_url") or "").strip()
                            character_name = str(entry.get("name") or entry.get("character_name") or "").strip()
                            local_character_path = Path(local_url)
                            if not local_url or not local_character_path.exists():
                                continue

                            safe_character_name = _safe_file_name(character_name or local_character_path.stem)
                            character_oss_url = _upload_file_to_oss(
                                local_character_path,
                                f"{summary_prefix}/character_json/{safe_character_name}.json",
                            )
                            entry["summary_local_url"] = local_character_path.as_posix()
                            entry["summary_oss_url"] = character_oss_url
                            changed = True
                            child_uploads.append(
                                {
                                    "type": "characters_detail",
                                    "name": character_name or local_character_path.stem,
                                    "local_url": local_character_path.as_posix(),
                                    "oss_url": character_oss_url,
                                }
                            )

                        if changed:
                            content_path.write_text(
                                json.dumps(index_payload, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )

                file_name = file_name_map.get(summary_type, content_path.name)
                oss_url = _upload_file_to_oss(content_path, f"{summary_prefix}/{file_name}")

                summary_id = f"sum_{book_id}_{summary_type}"
                local_path = content_path.as_posix()
                cur.execute(
                    """
                    INSERT INTO public.summary (
                        summary_id, book_id, type, name,
                        content_local_url, content_oss_url
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (summary_id) DO UPDATE
                    SET type = EXCLUDED.type,
                        name = EXCLUDED.name,
                        content_local_url = EXCLUDED.content_local_url,
                        content_oss_url = EXCLUDED.content_oss_url,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        summary_id,
                        book_id,
                        summary_type,
                        display_name_map.get(summary_type, summary_type),
                        local_path,
                        oss_url,
                    ),
                )
                inserted_rows += 1
                uploaded_records.extend(child_uploads)
                uploaded_records.append({
                    "type": summary_type,
                    "local_url": local_path,
                    "oss_url": oss_url,
                })

    return {
        "user_id": user_id,
        "book_id": book_id,
        "source_file_id": source_file_id,
        "uploaded_summary_count": inserted_rows,
        "uploaded_summary_rows": uploaded_records,
    }


def _extract_markdown_section(markdown_text: str, heading: str) -> str:
    lines = markdown_text.splitlines()
    target_heading = heading.strip()
    if not target_heading:
        return ""

    collecting = False
    section_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if collecting:
                break
            if stripped == target_heading:
                collecting = True
                continue
        elif collecting:
            section_lines.append(line)

    return "\n".join(section_lines).strip()


def persist_card_rows(
    card_rows: list[dict[str, Any]],
    *,
    user_id: str,
    book_id: str,
    source_file_id: str,
    character_name: str,
    oss_prefix: str = "charpick",
    db_url: str | None = None,
) -> dict[str, Any]:
    resolved_db_url = _resolve_db_url(db_url)
    inserted_rows = 0
    persisted_rows: list[dict[str, Any]] = []

    with _connect_with_fallback(resolved_db_url) as conn:
        with conn.cursor() as cur:
            for row in card_rows:
                card_type = str(row.get("dimension", "")).strip() or "character_card"

                content_path = Path(str(row.get("content_url", "") or row.get("md_url", "") or row.get("json_url", "")))
                if not content_path.exists():
                    continue

                content_kind = str(row.get("content_kind", "")).strip() or ("md" if content_path.suffix.lower() == ".md" else "json")

                if content_kind != "md":
                    # Keep backward compatibility, but prefer markdown-only cards.
                    content_kind = "md" if content_path.suffix.lower() == ".md" else content_kind

                card_prefix = _object_prefix(
                    oss_prefix,
                    user_id,
                    book_id,
                    source_file_id,
                    "card",
                    character_name,
                    card_type,
                )
                file_name = content_path.name if content_kind == "md" else f"card.{content_path.suffix.lstrip('.') or 'md'}"
                oss_url = _upload_file_to_oss(content_path, f"{card_prefix}/{file_name}")

                intro = ""
                try:
                    if content_kind == "md":
                        markdown_text = content_path.read_text(encoding="utf-8")
                        intro = _extract_markdown_section(markdown_text, "## 简介")
                    else:
                        payload = json.loads(content_path.read_text(encoding="utf-8"))
                        result = payload.get("result") if isinstance(payload, dict) else None
                        if isinstance(result, dict):
                            intro = str(result.get("intro") or result.get("summary") or "")
                except Exception:
                    intro = ""

                card_id = f"card_{book_id}_{_safe_file_name(character_name)}_{card_type}"
                cur.execute(
                    """
                    INSERT INTO public.card (
                        card_id, book_id, type, name, intro,
                        content_local_url, content_oss_url
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (card_id) DO UPDATE
                    SET type = EXCLUDED.type,
                        name = EXCLUDED.name,
                        intro = EXCLUDED.intro,
                        content_local_url = EXCLUDED.content_local_url,
                        content_oss_url = EXCLUDED.content_oss_url,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        card_id,
                        book_id,
                        card_type,
                        character_name,
                        intro,
                        content_path.as_posix(),
                        oss_url,
                    ),
                )
                inserted_rows += 1
                persisted_rows.append({
                    "card_id": card_id,
                    "book_id": book_id,
                    "type": card_type,
                    "name": character_name,
                    "intro": intro,
                    "content_local_url": content_path.as_posix(),
                    "content_oss_url": oss_url,
                })

    return {
        "user_id": user_id,
        "book_id": book_id,
        "source_file_id": source_file_id,
        "character_name": character_name,
        "uploaded_card_count": inserted_rows,
        "uploaded_card_rows": persisted_rows,
    }
