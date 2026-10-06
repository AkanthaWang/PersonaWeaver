from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import requests
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.long import EXAMPLES, advanced_split_novel, get_ollama_embedding, local_model
from backend.remote_persistence import _connect_with_fallback, _resolve_db_url, mark_book_status
from backend.workflow_runner import run_l0_to_l2_pipeline

try:
    from psycopg2 import Error as PsycopgError
except Exception:  # pragma: no cover - psycopg2 is already required by remote_persistence
    PsycopgError = Exception

def _load_dotenv_simple(env_path: Path | None = None) -> None:
    """加载项目根目录 .env，避免公开配置文件保存真实密钥。"""
    target = env_path or ROOT_DIR / ".env"
    if not target.exists():
        return
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = value


_load_dotenv_simple()


app = FastAPI(
    title="CharPick Unified API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parents[1]
LOG_FILE = BASE_DIR / "output" / "process.log"
OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_OUTPUT_FILE = OUTPUT_DIR / "charpick_v3_database.jsonl"

_TASKS: dict[str, dict[str, Any]] = {}
_TASKS_LOCK = Lock()

# 正在提取中的 book_id 集合，防止同一本书被重复并发提取。
_RUNNING_BOOKS: set[str] = set()
_RUNNING_BOOKS_LOCK = Lock()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _set_task_state(task_id: str, **fields: Any) -> None:
    with _TASKS_LOCK:
        previous = _TASKS.get(task_id, {})
        merged = {**previous, **fields}
        merged.setdefault("task_id", task_id)
        merged.setdefault("created_at", _now_iso())
        merged["updated_at"] = _now_iso()
        _TASKS[task_id] = merged


def _write_log(message: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%H:%M:%S", time.localtime())
    line = f"[{timestamp}] {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _extract_bearer_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="缺少 Authorization 头")

    prefix = "Bearer "
    if raw.lower().startswith(prefix.lower()):
        token = raw[len(prefix) :].strip()
        if token:
            return token

    raise HTTPException(status_code=401, detail="Authorization 格式错误，必须为 Bearer <token>")


def _resolve_user_context(access_token: str) -> dict[str, str]:
    db_url = _resolve_db_url()
    sql = """
    SELECT u.user_id, u.username
    FROM public.auth_sessions s
    JOIN public.users u ON u.user_id = s.user_id
    WHERE s.access_token_jti = %s
      AND (s.revoked_at IS NULL)
      AND (s.expires_at IS NULL OR s.expires_at > now())
    LIMIT 1
    """

    with _connect_with_fallback(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (access_token,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="登录态无效或已过期")

    return {
        "user_id": str(row[0]),
        "username": str(row[1] or "user"),
    }


def _fetch_book_for_user(user_id: str, book_id: str) -> dict[str, str]:
    db_url = _resolve_db_url()
    sql = """
    SELECT book_id, title, source_type, book_file_url
    FROM public.books
    WHERE user_id = %s AND book_id = %s
    LIMIT 1
    """

    with _connect_with_fallback(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, book_id))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"book_id={book_id} 不存在或不属于当前用户")

    return {
        "book_id": str(row[0]),
        "title": str(row[1] or book_id),
        "source_type": str(row[2] or "txt").lower(),
        "book_file_url": str(row[3] or "").strip(),
    }


def _resolve_character_name_from_roles(user_id: str, book_id: str, roles: list[str]) -> str:
    if not roles:
        return ""

    clean_roles = [str(item).strip() for item in roles if str(item).strip()]
    if not clean_roles:
        return ""

    db_url = _resolve_db_url()
    sql = """
    SELECT name
    FROM public.characters
    WHERE user_id = %s
      AND book_id = %s
      AND id = ANY(%s::text[])
    ORDER BY appearance_count DESC NULLS LAST, updated_at DESC NULLS LAST
    LIMIT 1
    """

    with _connect_with_fallback(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, book_id, clean_roles))
            row = cur.fetchone()

    if row and str(row[0] or "").strip():
        return str(row[0]).strip()

    return clean_roles[0]


def _guess_file_name_from_url(file_url: str, fallback: str) -> str:
    parsed = urlparse(file_url)
    tail = Path(parsed.path).name
    return tail or fallback


def _load_backend_config() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parent / "config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def _env_or_config(cfg: dict[str, Any], env_key_field: str, value_field: str, default: str = "") -> str:
    env_name = str(cfg.get(env_key_field) or "").strip()
    if env_name:
        env_value = os.getenv(env_name)
        if env_value:
            return env_value
    value = cfg.get(value_field, default)
    return str(value or default)



def _extract_text_from_llm_response(result_json: Any) -> str:
    if isinstance(result_json, dict):
        choices = result_json.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
                text = first.get("text")
                if isinstance(text, str):
                    return text

        message = result_json.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]

        output = result_json.get("output")
        if isinstance(output, str):
            return output
        if isinstance(output, list) and output and isinstance(output[0], dict):
            content = output[0].get("content") or output[0].get("text")
            if isinstance(content, str):
                return content

    return ""


def _normalize_chat_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/open/api/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/chat/completions"


def _chat_with_remote_api(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout_seconds: int,
) -> tuple[str, int | None]:
    url = _normalize_chat_base_url(base_url)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": False,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    result_json = resp.json()
    content = _extract_text_from_llm_response(result_json)

    usage = result_json.get("usage") if isinstance(result_json, dict) else None
    tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
    return content, int(tokens) if isinstance(tokens, int) else None


def _chat_with_vivo_api(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout_seconds: int,
) -> tuple[str, int | None]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": False,
        "thinking": {"type": "disabled"},
    }

    resp = requests.post(
        _normalize_chat_base_url(base_url),
        headers=headers,
        params={"request_id": str(uuid.uuid4())},
        json=payload,
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    result_json = resp.json()
    if isinstance(result_json, dict):
        code = result_json.get("code")
        msg = result_json.get("msg") or result_json.get("message")
        if code in {1001, 1007, 2003, 30001} or str(msg).strip() in {"429", "inner error"}:
            raise RuntimeError(f"vivo AIGC error {code}: {msg or result_json}")
    content = _extract_text_from_llm_response(result_json)
    usage = result_json.get("usage") if isinstance(result_json, dict) else None
    tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
    return content, int(tokens) if isinstance(tokens, int) else None


def _chat_with_ollama(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout_seconds: int,
) -> tuple[str, int | None]:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }

    resp = requests.post(url, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    result_json = resp.json()
    content = _extract_text_from_llm_response(result_json)
    return content, None


def _normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        import re

        parts = [p.strip() for p in re.split(r"[，,、；;\n]+", value) if p.strip()]
        return parts
    return []


def _normalize_extraction_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    normalized = dict(data)
    if "timeline" in normalized:
        normalized["timeline"] = _normalize_text_list(normalized.get("timeline"))

    top_characters = normalized.get("characters")
    if isinstance(top_characters, list):
        normalized_chars = []
        for item in top_characters:
            if isinstance(item, str):
                normalized_chars.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue

            char = dict(item)
            if "behavior" in char:
                char["behavior"] = _normalize_text_list(char.get("behavior"))
            if "role_behavior" in char and "behavior" not in char:
                char["behavior"] = _normalize_text_list(char.get("role_behavior"))
            if "speech" in char:
                char["speech"] = _normalize_text_list(char.get("speech"))
            if "actions" in char and "behavior" not in char:
                char["behavior"] = _normalize_text_list(char.get("actions"))
            if "psychology" in char:
                char["psychology"] = _normalize_text_list(char.get("psychology"))
            if "personality" in char:
                char["personality"] = _normalize_text_list(char.get("personality"))
            if "emotion" in char:
                char["emotion"] = _normalize_text_list(char.get("emotion"))
            normalized_chars.append(char)
        normalized["characters"] = normalized_chars
    elif isinstance(top_characters, str):
        normalized["characters"] = _normalize_text_list(top_characters)

    return normalized


class ExtractionRequest(BaseModel):
    file_name: str
    prompt: str
    filter_noise: bool = False


class ExtractDispatchRequest(BaseModel):
    book_id: str = Field(..., description="书籍 ID")
    roles: list[str] = Field(default_factory=list, description="角色 ID 列表")
    is_dynamic: bool = Field(default=False, description="是否动态角色卡，当前保留")
    source_file_id: str | None = Field(default=None, description="可选，覆盖 source_file_id")
    source_type: str | None = Field(default=None, description="可选，覆盖 source_type")
    file_url: str | None = Field(default=None, description="可选，覆盖 books.book_file_url")
    file_name: str | None = Field(default=None, description="可选，覆盖文件名")
    book_title: str | None = Field(default=None, description="可选，覆盖书名")
    card_character_name: str | None = Field(default=None, description="可选，指定角色卡角色")
    selected_summary_character: dict[str, Any] | None = Field(default=None, description="可选，summary 角色总表中选中的角色条目")
    filter_noise: bool = Field(default=True, description="是否过滤噪声")
    run_summary: bool = Field(default=True, description="是否生成 summary")
    run_card: bool = Field(default=True, description="是否生成 card")
    upload_summary_to_remote: bool = Field(default=True, description="是否上传 summary")
    upload_card_to_remote: bool = Field(default=True, description="是否上传 card")
    remote_db_url: str | None = Field(default=None, description="可选，覆盖远程 DB URL")
    max_chapters: int | None = Field(default=None, ge=1, description="可选，仅处理前 N 章，用于小规模联调测试")


class ChatRequest(BaseModel):
    message: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    system_prompt: str | None = None
    provider: str | None = Field(default=None, description="可选：vivo / remote_api / ecnu / glm / ollama")
    model: str | None = None
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 1024


def _require_user_context(authorization: str | None) -> dict[str, str]:
    token = _extract_bearer_token(authorization)
    return _resolve_user_context(token)


def _is_missing_relation_error(exc: Exception, relation_name: str) -> bool:
    if getattr(exc, "pgcode", None) == "42P01":
        return True
    message = str(exc).lower()
    return "relation" in message and relation_name.lower() in message


def _book_status_label(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"pending", "queued", "ready", "待解析"}:
        return "待解析"
    if normalized in {"parsing", "processing", "running", "解析中"}:
        return "解析中"
    if normalized in {"done", "completed", "success", "已完成"}:
        return "已完成"
    if normalized in {"failed", "error", "失败"}:
        return "失败"
    return str(status or "待解析")


def _task_status_label(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"done", "completed", "success", "已完成"}:
        return "completed"
    if normalized in {"failed", "error", "失败"}:
        return "failed"
    if normalized in {"running", "processing", "parsing", "进行中", "解析中"}:
        return "running"
    return "pending"


def _summary_name_by_type(summary_type: Any) -> str:
    normalized = str(summary_type or "").strip().lower()
    if normalized == "characters":
        return "角色总表"
    if normalized == "items":
        return "物品总表"
    if normalized == "storyline_events":
        return "剧情时间线"
    if normalized == "world_locations":
        return "世界观/地点表"
    return "汇总结果"


def _safe_progress(value: Any, status: Any = None) -> int:
    try:
        return max(0, min(100, round(float(value))))
    except Exception:
        normalized = _task_status_label(status)
        if normalized == "completed":
            return 100
        if normalized == "running":
            return 35
        return 0


def _verify_book_owner(user_id: str, book_id: str) -> dict[str, Any]:
    db_url = _resolve_db_url()
    sql = """
    SELECT book_id, title, author, source_type, language, status, progress,
           book_file_url, err_message, created_at, updated_at
    FROM public.books
    WHERE user_id = %s AND book_id = %s
    LIMIT 1
    """

    with _connect_with_fallback(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, book_id))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"book_id={book_id} 不存在或不属于当前用户")

    return {
        "book_id": str(row[0]),
        "book_name": str(row[1] or row[0]),
        "title": str(row[1] or row[0]),
        "author": row[2],
        "source_type": str(row[3] or "txt"),
        "language": row[4],
        "status": _book_status_label(row[5]),
        "raw_status": str(row[5] or ""),
        "progress": _safe_progress(row[6], row[5]),
        "file_name": _guess_file_name_from_url(str(row[7] or ""), "source.txt"),
        "file_url": str(row[7] or "") or None,
        "book_file_url": str(row[7] or "") or None,
        "err_message": row[8],
        "created_at": str(row[9] or ""),
        "updated_at": str(row[10] or "") if row[10] else None,
    }


def _load_json_from_local_url(local_url: str | None) -> Any:
    raw = str(local_url or "").strip()
    if not raw:
        return None

    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / raw
    if not path.exists() or path.suffix.lower() != ".json":
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_safe_local_output_path(local_url: str | None) -> Path:
    raw = str(local_url or "").strip()
    if not raw:
        raise HTTPException(status_code=404, detail="本地文件路径为空")

    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / raw

    resolved = path.resolve()
    output_root = (ROOT_DIR / "output").resolve()
    cache_root = (ROOT_DIR / "local_cache").resolve()
    allowed_roots = (output_root, cache_root)
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise HTTPException(status_code=403, detail="不允许读取该本地文件")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="本地文件不存在")
    return resolved


def root() -> dict[str, Any]:
    return {
        "name": "CharPick Unified API",
        "version": "1.0.0",
        "status": "ok",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/debug/oss-import")
def debug_oss_import() -> dict[str, Any]:
    """诊断：报告 exe 内 oss2 是否成功导入（不跑提取，单独验证 OSS 依赖打包）。"""
    from backend import remote_persistence as rp
    ok = rp.oss2 is not None
    result: dict[str, Any] = {
        "oss2_imported": ok,
        "import_error": getattr(rp, "_OSS2_IMPORT_ERROR", ""),
    }
    if ok:
        result["oss2_version"] = getattr(rp.oss2, "__version__", "unknown")
    # 也直接现场尝试 import，捕获真实错误
    try:
        import oss2 as _live  # noqa: F401
        result["live_import"] = "ok"
    except Exception as exc:  # noqa: BLE001
        import traceback
        result["live_import"] = f"{type(exc).__name__}: {exc}"
        result["live_traceback"] = traceback.format_exc()
    return result


def _run_dispatch_pipeline_task(
    *,
    task_id: str,
    req: ExtractDispatchRequest,
    user_ctx: dict[str, str],
    book: dict[str, str],
    source_file_id: str,
    source_type: str,
    file_url: str,
    card_character_name: str,
) -> None:
    print(f"[dispatch:{task_id}] 线程启动，book={book.get('book_id')} file_url={file_url[:60]}", flush=True)
    _set_task_state(
        task_id,
        status="running",
        progress=1,
        stage="dispatch",
        message="任务开始执行",
    )

    # 把书籍状态置为解析中（前端轮询 books 表）
    try:
        mark_book_status(book_id=book["book_id"], status="parsing", progress=1, db_url=req.remote_db_url)
        print(f"[dispatch:{task_id}] 已标记 parsing，开始 pipeline", flush=True)
    except Exception as exc:  # noqa: BLE001
        _write_log(f"[dispatch:{task_id}] mark parsing failed: {exc}")
        print(f"[dispatch:{task_id}] mark parsing 失败: {exc}", flush=True)

    # 进度回写节流：避免每个事件都写库
    _last_written = {"pct": -10}

    def on_progress(event: dict[str, Any]) -> None:
        pct = int(event.get("percent", 1))
        print(f"[dispatch:{task_id}] {pct}% {event.get('stage','')} {event.get('event','')} {str(event.get('message',''))[:50]}", flush=True)
        _set_task_state(
            task_id,
            status="running",
            progress=pct,
            stage=str(event.get("stage", "dispatch")),
            event=str(event.get("event", "running")),
            message=str(event.get("message", "")),
            detail=event,
        )
        # 进度每增长 >=20% 才写一次 books 表，减少 pooler 连接开销；不覆盖最终 done。
        if pct - _last_written["pct"] >= 20 and pct < 100:
            _last_written["pct"] = pct
            try:
                mark_book_status(book_id=book["book_id"], status="parsing", progress=pct, db_url=req.remote_db_url)
            except Exception:  # noqa: BLE001
                pass

    try:
        result = run_l0_to_l2_pipeline(
            source_path=None,
            source_type=source_type,
            source_file_id=source_file_id,
            file_name=req.file_name or _guess_file_name_from_url(file_url, f"{source_file_id}.txt"),
            file_url=file_url,
            filter_noise=req.filter_noise,
            upload_chapters_to_remote=True,
            upload_summary_to_remote=req.upload_summary_to_remote,
            upload_card_to_remote=req.upload_card_to_remote,
            run_summary=req.run_summary,
            run_card=req.run_card,
            card_character_name=card_character_name,
            selected_summary_character=req.selected_summary_character,
            remote_db_url=req.remote_db_url,
            user_id=user_ctx["user_id"],
            username=user_ctx["username"],
            book_id=book["book_id"],
            book_title=req.book_title or book["title"],
            max_chapters=req.max_chapters,
            show_progress=False,
            progress_callback=on_progress,
        )

        _set_task_state(
            task_id,
            status="completed",
            progress=100,
            stage="done",
            message="任务执行完成",
            result={
                "book_id": book["book_id"],
                "source_file_id": source_file_id,
                "summary": result.get("summary"),
                "card": result.get("card"),
                "remote_persist": result.get("remote_persist"),
            },
        )
    except Exception as exc:
        _set_task_state(
            task_id,
            status="failed",
            progress=0,
            stage="error",
            message=str(exc),
        )
        _write_log(f"[dispatch:{task_id}] failed: {exc}")
        import traceback
        print(f"[dispatch:{task_id}] 任务异常:", flush=True)
        traceback.print_exc()
    finally:
        # 无论成败，从"正在提取"集合移除，允许该书重新提取。
        with _RUNNING_BOOKS_LOCK:
            _RUNNING_BOOKS.discard(book["book_id"])


@app.post("/api/v1/extract")
def extract_dispatch(
    req: ExtractDispatchRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = _extract_bearer_token(authorization)
    user_ctx = _resolve_user_context(token)
    book = _fetch_book_for_user(user_ctx["user_id"], req.book_id)

    # 防重复并发：同一本书已在提取中则拒绝，避免重复点击起多个任务。
    with _RUNNING_BOOKS_LOCK:
        if book["book_id"] in _RUNNING_BOOKS:
            raise HTTPException(status_code=409, detail="该书籍正在提取中，请勿重复提交")
        _RUNNING_BOOKS.add(book["book_id"])

    try:
        file_url = str(req.file_url or book["book_file_url"] or "").strip()
        if not file_url:
            raise HTTPException(status_code=400, detail="book_file_url 为空，无法开始提取")

        source_type = str(req.source_type or book["source_type"] or "txt").lower()
        source_file_id = req.source_file_id or f"sf_{book['book_id']}_{int(time.time())}"
        card_character_name = str(req.card_character_name or "").strip()
        if req.run_card and not card_character_name:
            card_character_name = _resolve_character_name_from_roles(user_ctx["user_id"], book["book_id"], req.roles)
        if req.run_card and not card_character_name:
            raise HTTPException(status_code=400, detail="请先从 summary 角色总表中选择角色，再提取角色卡")

        task_id = f"dispatch_{uuid.uuid4().hex[:12]}"
        _set_task_state(
            task_id,
            status="queued",
            progress=0,
            stage="queued",
            message="任务已入队",
            book_id=book["book_id"],
            user_id=user_ctx["user_id"],
        )

        # 用原生线程而非 FastAPI BackgroundTasks 启动后台提取：
        # PyInstaller 打包的 exe 里 Starlette BackgroundTasks 不可靠（任务不执行），
        # threading.Thread 在 frozen 环境下能正常运行。
        worker = threading.Thread(
            target=_run_dispatch_pipeline_task,
            kwargs=dict(
                task_id=task_id,
                req=req,
                user_ctx=user_ctx,
                book=book,
                source_file_id=source_file_id,
                source_type=source_type,
                file_url=file_url,
                card_character_name=card_character_name,
            ),
            daemon=True,
        )
        worker.start()
    except Exception:
        # 启动失败则释放占用，允许重试
        with _RUNNING_BOOKS_LOCK:
            _RUNNING_BOOKS.discard(book["book_id"])
        raise

    return {
        "task_id": task_id,
        "book_id": book["book_id"],
        "status": "started",
        "message": f"提取任务已启动，角色卡目标：{card_character_name}" if req.run_card else "summary 提取任务已启动",
        "source_file_id": source_file_id,
    }


@app.get("/api/v1/tasks/{task_id}")
def get_dispatch_task(task_id: str) -> dict[str, Any]:
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"task_id={task_id} 不存在")

    return task


@app.get("/api/v1/books")
def list_books(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_ctx = _require_user_context(authorization)
    db_url = _resolve_db_url()

    sql = """
    SELECT book_id, title, author, source_type, language, status, progress,
           book_file_url, err_message, created_at, updated_at
    FROM public.books
    WHERE user_id = %s
    ORDER BY created_at DESC NULLS LAST, updated_at DESC NULLS LAST
    """

    try:
        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_ctx["user_id"],))
                rows = cur.fetchall()
    except Exception as exc:
        _write_log(f"list_books failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    books = []
    for row in rows:
        file_url = str(row[7] or "")
        status = _book_status_label(row[5])
        books.append(
            {
                "book_id": str(row[0]),
                "book_name": str(row[1] or row[0]),
                "title": str(row[1] or row[0]),
                "author": row[2],
                "source_type": str(row[3] or "txt"),
                "language": row[4],
                "status": status,
                "raw_status": str(row[5] or ""),
                "file_name": _guess_file_name_from_url(file_url, "source.txt"),
                "file_url": file_url or None,
                "book_file_url": file_url or None,
                "source_file_id": None,
                "progress": _safe_progress(row[6], row[5]),
                "err_message": row[8],
                "created_at": str(row[9] or ""),
                "updated_at": str(row[10] or "") if row[10] else None,
            }
        )

    return {"total": len(books), "books": books}


@app.get("/api/v1/books/{book_id}/roles")
def list_book_roles(
    book_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_ctx = _require_user_context(authorization)
    _verify_book_owner(user_ctx["user_id"], book_id)
    db_url = _resolve_db_url()

    sql = """
    SELECT id, name, appearance_count, status
    FROM public.characters
    WHERE user_id = %s AND book_id = %s
    ORDER BY appearance_count DESC NULLS LAST, updated_at DESC NULLS LAST
    """

    try:
        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_ctx["user_id"], book_id))
                rows = cur.fetchall()
    except Exception as exc:
        if _is_missing_relation_error(exc, "characters"):
            return {"book_id": book_id, "roles": []}
        _write_log(f"list_book_roles failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "book_id": book_id,
        "roles": [
            {
                "role_id": str(row[0]),
                "name": str(row[1] or "未命名角色"),
                "occurrence_count": int(row[2] or 0),
                "extraction_status": 1 if str(row[3] or "").strip() else 0,
                "status": str(row[3] or ""),
            }
            for row in rows
        ],
    }


@app.get("/api/v1/tasks")
def list_extraction_tasks(
    book_id: str | None = Query(default=None),
    limit: int = Query(default=0, ge=0),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_ctx = _require_user_context(authorization)
    if book_id:
        _verify_book_owner(user_ctx["user_id"], book_id)

    db_url = _resolve_db_url()
    sql = """
    SELECT id, user_id, book_id, task_type, status, progress, error_message, created_at, updated_at
    FROM public.extraction_tasks
    WHERE user_id = %s
    """
    params: list[Any] = [user_ctx["user_id"]]
    if book_id:
        sql += " AND book_id = %s"
        params.append(book_id)
    sql += " ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST"
    if limit > 0:
        sql += " LIMIT %s"
        params.append(limit)

    try:
        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    except Exception as exc:
        if _is_missing_relation_error(exc, "extraction_tasks"):
            return {"tasks": []}
        _write_log(f"list_extraction_tasks failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    items = []
    for row in rows:
        status = _task_status_label(row[4])
        items.append(
            {
                "id": str(row[0]),
                "task_id": str(row[0]),
                "user_id": str(row[1]),
                "book_id": str(row[2]),
                "task_type": str(row[3] or "unknown"),
                "status": status,
                "status_label": {"pending": "等待中", "running": "进行中", "completed": "已完成", "failed": "失败"}[status],
                "progress": _safe_progress(row[5], row[4]),
                "error_message": row[6],
                "created_at": str(row[7] or ""),
                "updated_at": str(row[8] or "") if row[8] else None,
            }
        )

    return {"tasks": items}


@app.get("/api/v1/task-logs")
def list_task_logs(
    task_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=0),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_ctx = _require_user_context(authorization)
    db_url = _resolve_db_url()
    sql = """
    SELECT id, task_id, user_id, level, message, detail_json, created_at
    FROM public.task_logs
    WHERE user_id = %s
    """
    params: list[Any] = [user_ctx["user_id"]]
    if task_id:
        sql += " AND task_id = %s"
        params.append(task_id)
    sql += " ORDER BY created_at DESC NULLS LAST"
    if limit > 0:
        sql += " LIMIT %s"
        params.append(limit)

    try:
        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    except Exception as exc:
        if _is_missing_relation_error(exc, "task_logs"):
            return {"logs": []}
        _write_log(f"list_task_logs failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "logs": [
            {
                "id": str(row[0]),
                "task_id": str(row[1] or ""),
                "user_id": str(row[2] or ""),
                "level": str(row[3] or "info").lower(),
                "message": str(row[4] or ""),
                "detail_json": row[5],
                "created_at": str(row[6] or ""),
            }
            for row in rows
        ]
    }


@app.get("/api/v1/chapter-extractions")
def list_chapter_extractions(
    book_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_ctx = _require_user_context(authorization)
    _verify_book_owner(user_ctx["user_id"], book_id)
    db_url = _resolve_db_url()

    sql = """
    SELECT id, user_id, book_id, extractor_type,
           book_extraction_json_local_url, book_extraction_json_oss_url
    FROM public.chapter_extractions
    WHERE user_id = %s AND book_id = %s
    ORDER BY extractor_type ASC
    """

    try:
        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_ctx["user_id"], book_id))
                rows = cur.fetchall()
    except Exception as exc:
        if _is_missing_relation_error(exc, "chapter_extractions"):
            return {"extractions": []}
        _write_log(f"list_chapter_extractions failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "extractions": [
            {
                "id": str(row[0]),
                "user_id": str(row[1]),
                "book_id": str(row[2]),
                "extractor_type": str(row[3] or "unknown"),
                "book_extraction_json_local_url": str(row[4] or "") or None,
                "book_extraction_json_oss_url": str(row[5] or "") or None,
                "model_name": None,
                "created_at": None,
                "updated_at": None,
            }
            for row in rows
        ]
    }


@app.get("/api/v1/summaries")
def list_summaries(
    book_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_ctx = _require_user_context(authorization)
    _verify_book_owner(user_ctx["user_id"], book_id)
    db_url = _resolve_db_url()

    sql = """
    SELECT s.summary_id, s.book_id, s.type, s.name,
           s.content_local_url, s.content_oss_url, s.created_at, s.updated_at
    FROM public.summary s
    JOIN public.books b ON b.book_id = s.book_id
    WHERE b.user_id = %s AND s.book_id = %s
    ORDER BY s.updated_at DESC NULLS LAST, s.created_at DESC NULLS LAST
    """

    try:
        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_ctx["user_id"], book_id))
                rows = cur.fetchall()
    except Exception as exc:
        if _is_missing_relation_error(exc, "summary"):
            return {"summaries": []}
        _write_log(f"list_summaries failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "summaries": [
            {
                "id": str(row[0]),
                "summary_id": str(row[0]),
                "user_id": user_ctx["user_id"],
                "book_id": str(row[1]),
                "type": str(row[2] or ""),
                "name": str(row[3] or "") or _summary_name_by_type(row[2]),
                "content_local_url": str(row[4] or "") or None,
                "content_oss_url": str(row[5] or "") or None,
                "created_at": str(row[6] or "") if row[6] else None,
                "updated_at": str(row[7] or "") if row[7] else None,
            }
            for row in rows
        ]
    }


@app.get("/api/v1/summaries/{summary_id}/content")
def get_summary_content(
    summary_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_ctx = _require_user_context(authorization)
    db_url = _resolve_db_url()

    sql = """
    SELECT s.summary_id, s.book_id, s.type, s.name,
           s.content_local_url, s.content_oss_url, s.created_at, s.updated_at
    FROM public.summary s
    JOIN public.books b ON b.book_id = s.book_id
    WHERE b.user_id = %s AND s.summary_id = %s
    LIMIT 1
    """

    try:
        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_ctx["user_id"], summary_id))
                row = cur.fetchone()
    except Exception as exc:
        if _is_missing_relation_error(exc, "summary"):
            raise HTTPException(status_code=404, detail="summary 记录不存在") from exc
        _write_log(f"get_summary_content failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not row:
        raise HTTPException(status_code=404, detail="summary 记录不存在")

    content_local_url = str(row[4] or "") or None
    content: Any = None
    content_format = "text"
    if content_local_url:
        local_path = _resolve_safe_local_output_path(content_local_url)
        suffix = local_path.suffix.lower()
        if suffix == ".json":
            content = json.loads(local_path.read_text(encoding="utf-8"))
            content_format = "json"
        else:
            content = local_path.read_text(encoding="utf-8")
            content_format = "markdown" if suffix in {".md", ".markdown"} else "text"

    return {
        "summary": {
            "id": str(row[0]),
            "summary_id": str(row[0]),
            "user_id": user_ctx["user_id"],
            "book_id": str(row[1]),
            "type": str(row[2] or ""),
            "name": str(row[3] or "") or _summary_name_by_type(row[2]),
            "content_local_url": content_local_url,
            "content_oss_url": str(row[5] or "") or None,
            "created_at": str(row[6] or "") if row[6] else None,
            "updated_at": str(row[7] or "") if row[7] else None,
        },
        "format": content_format,
        "content": content,
    }


@app.get("/api/v1/local-files")
def get_local_file(
    path: str,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    _require_user_context(authorization)
    local_path = _resolve_safe_local_output_path(path)
    return FileResponse(local_path)


@app.get("/api/v1/cards")
def list_cards(
    book_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_ctx = _require_user_context(authorization)
    if book_id:
        _verify_book_owner(user_ctx["user_id"], book_id)

    db_url = _resolve_db_url()
    sql = """
    SELECT c.card_id, c.book_id, c.type, c.name, c.intro,
           c.content_local_url, c.content_oss_url, c.created_at, c.updated_at
    FROM public.card c
    JOIN public.books b ON b.book_id = c.book_id
    WHERE b.user_id = %s
    """
    params: list[Any] = [user_ctx["user_id"]]
    if book_id:
        sql += " AND c.book_id = %s"
        params.append(book_id)
    sql += " ORDER BY c.updated_at DESC NULLS LAST, c.created_at DESC NULLS LAST"

    try:
        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    except Exception as exc:
        if _is_missing_relation_error(exc, "card"):
            return {"cards": []}
        _write_log(f"list_cards failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "cards": [
            {
                "id": str(row[0]),
                "card_id": str(row[0]),
                "user_id": user_ctx["user_id"],
                "book_id": str(row[1] or ""),
                "type": str(row[2] or "character"),
                "name": str(row[3] or "未命名卡片"),
                "intro": str(row[4] or ""),
                "content_local_url": str(row[5] or "") or None,
                "content_oss_url": str(row[6] or "") or None,
                "created_at": str(row[7] or "") if row[7] else None,
                "updated_at": str(row[8] or "") if row[8] else None,
            }
            for row in rows
        ]
    }


@app.get("/api/v1/characters")
def list_characters(
    book_id: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        token = _extract_bearer_token(authorization)
        user_ctx = _resolve_user_context(token)
        db_url = _resolve_db_url()

        sql = """
        SELECT c.card_id, c.book_id, c.type, c.name, c.intro,
               c.content_local_url, c.content_oss_url, c.created_at, c.updated_at
        FROM public.card c
        JOIN public.books b ON b.book_id = c.book_id
        WHERE b.user_id = %s
        """
        params: list[Any] = [user_ctx["user_id"]]
        if book_id:
            sql += " AND c.book_id = %s"
            params.append(book_id)
        sql += " ORDER BY c.updated_at DESC NULLS LAST, c.created_at DESC NULLS LAST"

        with _connect_with_fallback(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()

        items = []
        for row in rows:
            card_id = row[0]
            items.append(
                {
                    "role_id": str(card_id),
                    "id": str(card_id),
                    "user_id": str(user_ctx.get("user_id") or ""),
                    "book_id": str(row[1] or ""),
                    "type": str(row[2] or "character"),
                    "name": str(row[3] or "未命名角色"),
                    "intro": str(row[4] or ""),
                    "content_local_url": str(row[5] or "") or None,
                    "content_oss_url": str(row[6] or "") or None,
                    "created_at": str(row[7] or ""),
                    "updated_at": str(row[8] or ""),
                }
            )

        return {"characters": items}
    except HTTPException:
        raise
    except Exception as exc:
        _write_log(f"list_characters failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/characters/{character_id}")
def get_character_detail(
    character_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = _extract_bearer_token(authorization)
    user_ctx = _resolve_user_context(token)
    db_url = _resolve_db_url()

    sql = """
    SELECT c.card_id, c.book_id, c.type, c.name, c.intro,
           c.content_local_url, c.content_oss_url, c.created_at, c.updated_at
    FROM public.card c
    JOIN public.books b ON b.book_id = c.book_id
    WHERE b.user_id = %s
      AND c.card_id = %s
    LIMIT 1
    """

    with _connect_with_fallback(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_ctx["user_id"], character_id))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"character_id={character_id} 不存在")

    card_id = row[0]
    return {
        "role_id": str(card_id),
        "id": str(card_id),
        "user_id": str(user_ctx.get("user_id") or ""),
        "book_id": str(row[1] or ""),
        "type": str(row[2] or "character"),
        "name": str(row[3] or "未命名角色"),
        "intro": str(row[4] or ""),
        "content_local_url": str(row[5] or "") or None,
        "content_oss_url": str(row[6] or "") or None,
        "created_at": str(row[7] or ""),
        "updated_at": str(row[8] or ""),
    }


@app.post("/chat")
def chat(request: ChatRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    config = _load_backend_config()
    llm_cfg = config.get("llm", {})
    provider = str(request.provider or llm_cfg.get("provider") or "ollama").strip().lower()

    messages: list[dict[str, str]] = []
    if request.system_prompt and request.system_prompt.strip():
        messages.append({"role": "system", "content": request.system_prompt.strip()})

    for item in request.history:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role in {"system", "user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    if request.message and request.message.strip():
        msg = request.message.strip()
        if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != msg:
            messages.append({"role": "user", "content": msg})

    if not messages:
        raise HTTPException(status_code=400, detail="message 或 history 至少需要一个")

    timeout_seconds = int(llm_cfg.get("timeout_seconds", 120))
    model = str(request.model or llm_cfg.get("model") or "qwen2.5:0.5b")

    if provider in {"vivo", "vivo_aigc"}:
        vivo_cfg = llm_cfg.get("vivo") if isinstance(llm_cfg.get("vivo"), dict) else {}
        base_url = _env_or_config(vivo_cfg, "base_url_env", "base_url", "https://api-ai.vivo.com.cn/v1/chat/completions").strip()
        api_key = str(x_api_key or _env_or_config(vivo_cfg, "api_key_env", "api_key", llm_cfg.get("api_key", ""))).strip()
        model = str(request.model or _env_or_config(vivo_cfg, "model_name_env", "model_name", vivo_cfg.get("model", "Volc-DeepSeek-V3.2")))
        timeout_seconds = int(vivo_cfg.get("timeout_seconds", timeout_seconds))
        if not base_url or not api_key:
            raise HTTPException(status_code=500, detail="vivo 配置不完整（base_url/api_key）")
        try:
            content, tokens = _chat_with_vivo_api(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=float(request.temperature),
                top_p=float(request.top_p),
                max_tokens=int(request.max_tokens),
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"vivo AIGC 调用失败: {exc}") from exc
    elif provider in {"remote_api", "ecnu", "glm", "bigmodel"}:
        if provider == "glm" or provider == "bigmodel":
            glm_cfg = llm_cfg.get("glm") if isinstance(llm_cfg.get("glm"), dict) else {}
            base_url = _env_or_config(glm_cfg, "base_url_env", "base_url", "https://open.bigmodel.cn/api/paas/v4").strip()
            api_key = str(x_api_key or _env_or_config(glm_cfg, "api_key_env", "api_key", os.getenv("BIGMODEL_API_KEY", "")) or llm_cfg.get("api_key") or "").strip()
            model = str(request.model or _env_or_config(glm_cfg, "model_name_env", "model_name", glm_cfg.get("model", "glm-4.5-air")))
        else:
            remote_cfg = llm_cfg.get("remote_api") if isinstance(llm_cfg.get("remote_api"), dict) else {}
            base_url = _env_or_config(remote_cfg, "base_url_env", "base_url", llm_cfg.get("base_url", "")).strip()
            api_key = str(x_api_key or _env_or_config(remote_cfg, "api_key_env", "api_key", llm_cfg.get("api_key", ""))).strip()
            model = str(request.model or _env_or_config(remote_cfg, "model_name_env", "model_name", remote_cfg.get("model", model)))

        if not base_url or not api_key:
            raise HTTPException(status_code=500, detail=f"{provider} 配置不完整（base_url/api_key）")

        try:
            content, tokens = _chat_with_remote_api(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=float(request.temperature),
                top_p=float(request.top_p),
                max_tokens=int(request.max_tokens),
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"远程模型调用失败: {exc}") from exc
    else:
        ollama_cfg = llm_cfg.get("ollama") if isinstance(llm_cfg.get("ollama"), dict) else {}
        base_url = str(ollama_cfg.get("base_url") or llm_cfg.get("base_url") or "http://localhost:11434").strip()
        model = str(request.model or ollama_cfg.get("model") or llm_cfg.get("model") or model)

        try:
            content, tokens = _chat_with_ollama(
                base_url=base_url,
                model=model,
                messages=messages,
                temperature=float(request.temperature),
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"本地模型调用失败: {exc}") from exc

    return {
        "response": content,
        "model": model,
        "tokens_used": tokens,
    }


# --- Legacy compatibility endpoints ---

def _legacy_background_extraction_task(file_path: str, custom_prompt: str, filter_noise: bool, output_file: str) -> None:
    _write_log(f"🚀 开始任务: 处理文件 {os.path.basename(file_path)}")
    try:
        _write_log(f"🧹 噪声过滤: {'开启' if filter_noise else '关闭'}")
        chapters = advanced_split_novel(file_path, filter_noise=filter_noise)
        _write_log(f"📚 小说切分完成，共 {len(chapters)} 章")

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        _write_log(f"📝 输出文件: {os.path.basename(output_file)}")

        with open(output_file, "a", encoding="utf-8") as f_out:
            for idx, chapter in enumerate(chapters):
                _write_log(f"⏳ 正在处理: {chapter['title']} ({idx + 1}/{len(chapters)})...")
                chunk_text = f"{chapter['title']}\n{chapter['content'][:3500]}"
                try:
                    try:
                        from backend import langextract as lx

                        result = lx.extract(
                            text_or_documents=chunk_text,
                            prompt_description=custom_prompt,
                            examples=EXAMPLES,
                            model=local_model,
                        )
                        extraction_data = {}
                        if isinstance(result, dict):
                            extractions = result.get("extractions") or []
                            if extractions and isinstance(extractions[0], dict):
                                extraction_data = extractions[0].get("attributes", {}) or {}
                        extraction_data = _normalize_extraction_data(extraction_data)
                    except Exception as exc:
                        extraction_data = {"note": "提取失败或库不可用", "error": str(exc)}

                    plot_text = extraction_data.get("plot_summary", "") if isinstance(extraction_data, dict) else ""
                    vector = get_ollama_embedding(plot_text) if plot_text else []

                    record = {
                        "id": idx,
                        "title": chapter["title"],
                        "metadata": extraction_data,
                        "vector": vector,
                    }
                    f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f_out.flush()
                    _write_log(f"✅ 完成: {chapter['title']}")
                except Exception as exc:
                    _write_log(f"❌ 章节处理失败: {chapter['title']} - {exc}")

        _write_log("🎉 所有章节提取任务已完成！")
    except Exception as exc:
        _write_log(f"💥 致命错误: {exc}")


async def log_stream() -> StreamingResponse:
    async def log_generator():
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_FILE.exists():
            LOG_FILE.write_text("[System] Log stream started...\n", encoding="utf-8")

        with LOG_FILE.open("r", encoding="utf-8") as f:
            f.seek(0, 2)
            while True:
                try:
                    if LOG_FILE.stat().st_size < f.tell():
                        f.seek(0)
                except OSError:
                    pass

                line = f.readline()
                if line:
                    yield f"data: {line}\n\n"
                else:
                    await asyncio.sleep(0.5)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(log_generator(), media_type="text/event-stream", headers=headers)


def list_files() -> list[str]:
    data_dir = BASE_DIR / "data"
    if not data_dir.exists():
        return []
    return [f.name for f in data_dir.iterdir() if f.is_file() and f.suffix.lower() == ".txt"]


def start_legacy_extraction(req: ExtractionRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    file_path = BASE_DIR / "data" / req.file_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(f"[System] 新任务启动 - {req.file_name}\n", encoding="utf-8")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    output_file = OUTPUT_DIR / f"charpick_v3_database_{timestamp}.jsonl"

    background_tasks.add_task(
        _legacy_background_extraction_task,
        str(file_path),
        req.prompt,
        req.filter_noise,
        str(output_file),
    )
    return {
        "status": "started",
        "output_file": output_file.name,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
