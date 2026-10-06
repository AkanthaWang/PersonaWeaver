import json
from pathlib import Path
from typing import Any, Callable

from backend.llm_dispatcher import (
    build_chapter_dispatch_from_source,
    dispatch_card_prompts,
    dispatch_summary_prompts,
)
from backend.remote_persistence import (
    create_extraction_task,
    initialize_remote_processing,
    mark_source_processing_failed,
    persist_card_rows,
    persist_l0_l1_rows,
    persist_l2_rows,
    persist_summary_rows,
    mark_book_status,
    update_extraction_task,
)


ProgressCallback = Callable[[dict[str, Any]], None]


def _clamp_percent(value: int | float) -> int:
    return max(0, min(100, int(value)))


def _progress_bar(percent: int, width: int = 20) -> str:
    safe_percent = _clamp_percent(percent)
    filled = int((safe_percent / 100) * width)
    return "#" * filled + "-" * (width - filled)


def _build_message(event: dict[str, Any]) -> str:
    message = event.get("message")
    if message:
        return str(message)
    stage = event.get("stage") or "stage"
    status = event.get("status") or "running"
    return f"{stage}:{status}"


def _text_matches_name(value: Any, needle: str) -> bool:
    if not needle:
        return False
    if isinstance(value, str):
        return needle in value or value in needle
    return needle in str(value)


def _load_summary_character(summary_result: dict[str, Any] | None, character_name: str) -> dict[str, Any] | None:
    if not summary_result:
        return None

    def load_character_entry(entry: dict[str, Any], base_dir: Path) -> dict[str, Any]:
        local_url = str(entry.get("summary_local_url") or "").strip()
        if local_url:
            detail_path = Path(local_url)
            if not detail_path.is_absolute():
                detail_path = base_dir / detail_path
            if detail_path.exists():
                try:
                    payload = json.loads(detail_path.read_text(encoding="utf-8"))
                    if isinstance(payload, dict):
                        return payload
                except Exception:
                    pass
        return entry

    for row in summary_result.get("summary_rows", []) or []:
        if str(row.get("dimension", "")).strip() != "characters":
            continue

        content_path = Path(str(row.get("content_url") or row.get("json_url") or ""))
        if not content_path.exists():
            continue

        try:
            payload = json.loads(content_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        candidates: list[dict[str, Any]] = []
        if isinstance(payload, list):
            candidates = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            if isinstance(payload.get("characters"), list):
                candidates = [item for item in payload["characters"] if isinstance(item, dict)]
            else:
                candidates = [payload]

        for entry in candidates:
            name = entry.get("name") or entry.get("character_name")
            if _text_matches_name(name, character_name):
                return load_character_entry(entry, content_path.parent)

        if candidates:
            return load_character_entry(candidates[0], content_path.parent)

    return None


def _resolve_summary_character(
    summary_result: dict[str, Any] | None,
    character_name: str,
    selected_summary_character: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if selected_summary_character:
        return selected_summary_character
    return _load_summary_character(summary_result, character_name)


def run_l0_to_l2_pipeline(
    source_path: str | None = None,
    source_type: str = "txt",
    source_file_id: str = "sf_local_001",
    file_name: str | None = None,
    file_url: str | None = None,
    filter_noise: bool = True,
    enabled_dimensions: list[str] | None = None,
    upload_chapters_to_remote: bool = False,
    upload_summary_to_remote: bool = True,
    upload_card_to_remote: bool = True,
    run_summary: bool = True,
    run_card: bool = True,
    card_character_name: str = "石野",
    selected_summary_character: dict[str, Any] | None = None,
    remote_db_url: str | None = None,
    user_id: str = "u_local_runner",
    username: str = "local_runner",
    book_id: str | None = None,
    book_title: str | None = None,
    max_chapters: int | None = None,
    show_progress: bool = False,
    progress_prefix: str = "PIPELINE",
    progress_callback: ProgressCallback | None = None,
) -> dict:
    def emit_progress(
        *,
        stage: str,
        percent: int,
        status: str,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "stage": stage,
            "percent": _clamp_percent(percent),
            "status": status,
            "message": message,
        }
        if extra:
            payload.update(extra)

        if show_progress:
            bar = _progress_bar(payload["percent"])
            print(f"[{progress_prefix}] {payload['percent']:>3}% [{bar}] {stage} | {status} | {message}")

        if progress_callback is not None:
            progress_callback(payload)

    def on_dispatch_progress(event: dict[str, Any]) -> None:
        stage = str(event.get("stage") or "dispatch")
        evt = str(event.get("event") or "running")

        if stage == "l2_chapter":
            total = int(event.get("total_chapters") or 0)
            completed = int(event.get("completed_chapters") or 0)
            if evt == "chapter_batch_start":
                emit_progress(stage="L2章节提取", percent=8, status="start", message=f"共 {total} 章，开始提取")
                return
            if evt in ("chapter_start", "chapter_dimension_done"):
                # 章节内部平滑进度：8%~60% 区间，按 (已完成章 + 本章维度进度) / 总章 线性推进。
                ch_idx = int(event.get("chapter_index") or 0)      # 当前第几章(从1)
                dim_idx = int(event.get("dimension_index") or 0)    # 本章第几个维度(从1)
                total_dim = int(event.get("total_dimensions") or 0)
                if total > 0:
                    chapter_frac = (dim_idx / total_dim) if total_dim else 0.0
                    done_frac = (max(ch_idx - 1, 0) + chapter_frac) / total
                    pct = 8 + int(done_frac * 52)
                    title = str(event.get("chapter_title") or "")
                    emit_progress(
                        stage="L2章节提取",
                        percent=pct,
                        status="running",
                        message=f"第 {ch_idx}/{total} 章提取中：{title}",
                    )
                return
            if evt == "chapter_done":
                pct = 8 + int((completed / total) * 52) if total else 8
                title = str(event.get("chapter_title") or "")
                emit_progress(
                    stage="L2章节提取",
                    percent=pct,
                    status="running",
                    message=f"章节 {completed}/{total} 完成：{title}",
                )
                return
            if evt == "chapter_batch_done":
                emit_progress(stage="L2章节提取", percent=60, status="done", message="章节提取全部完成")
                return

        if stage == "summary":
            total = int(event.get("total_dimensions") or 0)
            idx = int(event.get("dimension_index") or 0)
            dim = str(event.get("dimension") or "")
            if evt == "summary_start":
                emit_progress(stage="Summary汇总", percent=61, status="start", message=f"共 {total} 个维度")
                return
            if evt == "summary_dimension_start":
                pct = 61 + int((max(idx - 1, 0) / total) * 12) if total else 61
                emit_progress(stage="Summary汇总", percent=pct, status="running", message=f"汇总维度中：{dim}")
                return
            if evt == "summary_dimension_done":
                pct = 61 + int((idx / total) * 12) if total else 61
                emit_progress(stage="Summary汇总", percent=pct, status="running", message=f"维度完成：{dim}")
                return
            if evt == "summary_done":
                emit_progress(stage="Summary汇总", percent=73, status="done", message="Summary 已完成")
                return

        if stage == "card":
            total = int(event.get("total_dimensions") or 0)
            idx = int(event.get("dimension_index") or 0)
            dim = str(event.get("dimension") or "")
            character_name = str(event.get("character_name") or card_character_name)
            if evt == "card_start":
                emit_progress(stage="角色卡生成", percent=74, status="start", message=f"角色 {character_name}，共 {total} 个维度")
                return
            if evt == "card_dimension_done":
                pct = 74 + int((idx / total) * 10) if total else 74
                emit_progress(stage="角色卡生成", percent=pct, status="running", message=f"维度完成：{dim}")
                return
            if evt == "card_done":
                emit_progress(stage="角色卡生成", percent=84, status="done", message=f"角色卡已完成：{character_name}")
                return

        emit_progress(stage=f"dispatch:{stage}", percent=50, status=evt, message=_build_message(event), extra=event)

    resolved_book_id = book_id or f"b_{source_file_id}"
    fallback_title = file_name or (Path(source_path).stem if source_path else None) or source_file_id
    resolved_book_title = book_title or fallback_title

    chapter_task_id: int | None = None

    emit_progress(stage="初始化", percent=1, status="start", message="流水线启动")

    if upload_chapters_to_remote:
        emit_progress(stage="远程初始化", percent=2, status="start", message="准备初始化远程任务")
        bootstrap_row = {
            "source_type": source_type,
            "file_name": file_name or f"{source_file_id}.txt",
            "local_source_url": file_url or source_path or "",
            "unified_format_url": "",
        }
        bootstrap_result = initialize_remote_processing(
            source_file_row=bootstrap_row,
            user_id=user_id,
            username=username,
            book_id=resolved_book_id,
            book_title=resolved_book_title,
            source_file_id=source_file_id,
            db_url=remote_db_url,
        )
        raw_task_id = bootstrap_result.get("chapter_task_id")
        chapter_task_id = int(raw_task_id) if raw_task_id is not None else None
        emit_progress(stage="远程初始化", percent=5, status="done", message=f"远程任务初始化完成，task_id={chapter_task_id}")

    try:
        emit_progress(stage="L0/L1预处理", percent=6, status="start", message="开始解析文本、清洗并切章")
        dispatch_result = build_chapter_dispatch_from_source(
            source_path=source_path,
            source_type=source_type,
            source_file_id=source_file_id,
            file_name=file_name,
            file_url=file_url,
            filter_noise=filter_noise,
            book_id=resolved_book_id,
            book_title=resolved_book_title,
            enabled_dimensions=enabled_dimensions,
            max_chapters=max_chapters,
            progress_callback=on_dispatch_progress,
        )
        emit_progress(stage="L0/L1预处理", percent=7, status="done", message="预处理完成，已进入 L2 提取")
    except Exception as exc:
        emit_progress(stage="流程", percent=0, status="failed", message=f"预处理失败：{exc}")
        if upload_chapters_to_remote:
            mark_source_processing_failed(
                source_file_id=source_file_id,
                book_id=resolved_book_id,
                task_id=chapter_task_id,
                error_message=str(exc),
                db_url=remote_db_url,
            )
        raise

    l0_l1 = {
        "source_type": dispatch_result["source_file_row"]["source_type"],
        "file_name": dispatch_result["source_file_row"]["file_name"],
        "local_source_url": dispatch_result["source_file_row"]["local_source_url"],
        "unified_format_url": dispatch_result["source_file_row"]["unified_format_url"],
        "cache_folder": dispatch_result["cache_folder"],
    }

    l2_records = dispatch_result["chapter_extraction_rows"]
    chapter_rows = dispatch_result["chapter_rows"]
    extraction_output_dir = Path(dispatch_result["chapter_extraction_cache_dir"])

    summary_result = None
    if run_summary:
        emit_progress(stage="Summary汇总", percent=61, status="start", message="开始 Summary 聚合")
        summary_result = dispatch_summary_prompts(
            chapter_json_dir=dispatch_result["chapter_extraction_cache_dir"],
            source_file_id=source_file_id,
            book_title=resolved_book_title,
            progress_callback=on_dispatch_progress,
        )
    else:
        emit_progress(stage="Summary汇总", percent=73, status="skip", message="已跳过 Summary")

    card_result = None
    if run_card:
        emit_progress(stage="角色卡生成", percent=74, status="start", message=f"开始生成角色卡：{card_character_name}")
        summary_character = _resolve_summary_character(
            summary_result,
            card_character_name,
            selected_summary_character,
        )
        card_result = dispatch_card_prompts(
            chapter_json_dir=dispatch_result["chapter_extraction_cache_dir"],
            source_file_id=source_file_id,
            character_name=card_character_name,
            book_title=resolved_book_title,
            summary_character=summary_character,
            progress_callback=on_dispatch_progress,
        )
    else:
        emit_progress(stage="角色卡生成", percent=84, status="skip", message="已跳过角色卡")

    persisted = None
    if upload_chapters_to_remote:
        source_file_row = {
            "source_type": l0_l1["source_type"],
            "file_name": l0_l1.get("file_name") or file_name or f"{source_file_id}.txt",
            "local_source_url": l0_l1.get("local_source_url", ""),
            "unified_format_url": l0_l1["unified_format_url"],
        }

        if chapter_task_id is not None:
            update_extraction_task(
                task_id=chapter_task_id,
                status="running",
                progress=40,
                db_url=remote_db_url,
            )
        emit_progress(stage="远程上传", percent=85, status="running", message="开始写入 L0/L1 到远程数据库")

        llm_cfg = dispatch_result.get("llm", {})

        try:
            persisted_l0_l1 = persist_l0_l1_rows(
                source_file_row=source_file_row,
                chapter_rows=chapter_rows,
                user_id=user_id,
                book_id=resolved_book_id,
                source_file_id=source_file_id,
                username=username,
                book_title=resolved_book_title,
                db_url=remote_db_url,
            )
            emit_progress(stage="远程上传", percent=89, status="running", message="L0/L1 写入完成，开始上传 L2 聚合 JSON")
            if chapter_task_id is not None:
                update_extraction_task(
                    task_id=chapter_task_id,
                    status="running",
                    progress=70,
                    db_url=remote_db_url,
                )

            persisted_l2 = persist_l2_rows(
                chapter_extraction_rows=l2_records,
                user_id=user_id,
                book_id=resolved_book_id,
                source_file_id=source_file_id,
                model_name=llm_cfg.get("model_name") or llm_cfg.get("model"),
                prompt_version="v1",
                cache_folder=dispatch_result["cache_folder"],
                db_url=remote_db_url,
            )
            emit_progress(stage="远程上传", percent=94, status="running", message="L2 上传完成，更新书籍状态")
            if chapter_task_id is not None:
                update_extraction_task(
                    task_id=chapter_task_id,
                    status="completed",
                    progress=100,
                    db_url=remote_db_url,
                )
            mark_book_status(
                book_id=resolved_book_id,
                status="done",
                progress=100,
                db_url=remote_db_url,
            )
            emit_progress(stage="远程上传", percent=96, status="running", message="书籍状态更新完成")

            persisted = {
                "l0_l1": persisted_l0_l1,
                "l2": persisted_l2,
                "tasks": {
                    "chapter_extraction_task_id": chapter_task_id,
                },
            }

            if run_summary and upload_summary_to_remote and summary_result is not None:
                emit_progress(stage="远程上传", percent=97, status="running", message="开始上传 Summary")
                summary_task_id = create_extraction_task(
                    user_id=user_id,
                    book_id=resolved_book_id,
                    task_type="summary",
                    status="running",
                    progress=20,
                    db_url=remote_db_url,
                )
                persisted_summary = persist_summary_rows(
                    summary_rows=summary_result.get("summary_rows", []),
                    user_id=user_id,
                    book_id=resolved_book_id,
                    source_file_id=source_file_id,
                    db_url=remote_db_url,
                )
                if summary_task_id is not None:
                    update_extraction_task(
                        task_id=summary_task_id,
                        status="completed",
                        progress=100,
                        db_url=remote_db_url,
                    )
                persisted["summary"] = persisted_summary
                persisted["tasks"]["summary_task_id"] = summary_task_id
                emit_progress(stage="远程上传", percent=98, status="running", message="Summary 上传完成")

            if run_card and upload_card_to_remote and card_result is not None:
                emit_progress(stage="远程上传", percent=99, status="running", message="开始上传角色卡")
                card_task_id = create_extraction_task(
                    user_id=user_id,
                    book_id=resolved_book_id,
                    task_type="card",
                    status="running",
                    progress=20,
                    db_url=remote_db_url,
                )
                persisted_card = persist_card_rows(
                    card_rows=card_result.get("card_rows", []),
                    user_id=user_id,
                    book_id=resolved_book_id,
                    source_file_id=source_file_id,
                    character_name=card_character_name,
                    db_url=remote_db_url,
                )
                if card_task_id is not None:
                    update_extraction_task(
                        task_id=card_task_id,
                        status="completed",
                        progress=100,
                        db_url=remote_db_url,
                    )
                persisted["card"] = persisted_card
                persisted["tasks"]["card_task_id"] = card_task_id
                emit_progress(stage="远程上传", percent=100, status="done", message="远程上传全部完成")
        except Exception as exc:
            emit_progress(stage="远程上传", percent=0, status="failed", message=f"远程上传失败：{exc}")
            mark_source_processing_failed(
                source_file_id=source_file_id,
                book_id=resolved_book_id,
                task_id=chapter_task_id,
                error_message=str(exc),
                db_url=remote_db_url,
            )
            raise
    else:
        emit_progress(stage="远程上传", percent=100, status="skip", message="本次未启用远程上传")

    emit_progress(stage="流程", percent=100, status="done", message="流水线执行完成")

    # Prefer OSS URLs in returned summary/card structures when available
    try:
        if isinstance(persisted.get("summary"), dict) and isinstance(summary_result, dict):
            uploaded = {r.get("type"): r for r in persisted["summary"].get("uploaded_summary_rows", [])}
            for row in (summary_result.get("summary_rows") or []):
                dim = str(row.get("dimension", "")).strip()
                if dim and dim in uploaded and uploaded[dim].get("oss_url"):
                    row["content_url"] = uploaded[dim].get("oss_url")
    except Exception:
        pass

    try:
        if isinstance(persisted.get("card"), dict) and isinstance(card_result, dict):
            uploaded_cards = persisted["card"].get("uploaded_card_rows", [])
            # map by name+type or by file name
            for crow in (card_result.get("card_rows") or []):
                # find matching uploaded card by name and dimension
                name = str(crow.get("character_name", "")).strip()
                dim = str(crow.get("dimension", "")).strip()
                match = None
                for u in uploaded_cards:
                    if u.get("name") == name or (u.get("type") == dim and u.get("name") == name):
                        match = u
                        break
                # fallback: if only one uploaded row, use it
                if not match and len(uploaded_cards) == 1:
                    match = uploaded_cards[0]
                if match and match.get("content_oss_url"):
                    crow["content_url"] = match.get("content_oss_url")
    except Exception:
        pass

    return {
        "source_file_row": {
            "source_file_id": source_file_id,
            "source_type": l0_l1["source_type"],
            "unified_format_url": l0_l1["unified_format_url"],
            "file_name": l0_l1.get("file_name"),
            "local_source_url": l0_l1.get("local_source_url"),
        },
        "chapter_rows": chapter_rows,
        "chapter_extraction_rows": l2_records,
        "chapter_extraction_cache_dir": extraction_output_dir.as_posix(),
        "summary": summary_result,
        "card": card_result,
        "remote_persist": persisted,
        "cache_folder": dispatch_result["cache_folder"],
    }


if __name__ == "__main__":
    result = run_l0_to_l2_pipeline(
        source_path="data/神游.txt",
        source_type="txt",
        source_file_id="sf_shenyou_demo",
        filter_noise=True,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
