import json
import logging
from pathlib import Path
from urllib.parse import urlsplit
import requests

from backend.app.core.config import ecnu_model_env
from backend.app.ai.providers.llm_client import (
    call_openai_responses_json,
    call_openai_responses_text,
    _normalize_openai_base_url,
    _raise_for_vivo_error,
    _vivo_params,
)
from backend.app.ai.providers.settings_store import AgentSettingsStore

logger = logging.getLogger(__name__)


def error_diagnostics(exc):
    pending, seen, details = [exc], set(), []
    while pending and len(seen) < 12:
        item = pending.pop()
        if not isinstance(item, BaseException) or id(item) in seen:
            continue
        seen.add(id(item))
        codes = [
            f"{name}={value}" for name in ("errno", "winerror")
            if isinstance(value := getattr(item, name, None), int)
        ]
        details.append(type(item).__name__ + (f" ({', '.join(codes)})" if codes else ""))
        pending.extend(getattr(item, name, None) for name in (
            "__cause__", "__context__", "reason", "original_error",
        ))
        pending.extend(arg for arg in item.args if isinstance(arg, BaseException))
    return " -> ".join(details)


def load_settings(db, user_id):
    database_path = getattr(db, "path", None)
    if database_path is not None:
        stored = AgentSettingsStore(Path(database_path).parent).get_user_model(user_id)
        if stored:
            return stored
    row = db.one("SELECT * FROM model_settings WHERE user_id=?", (user_id,))
    if row:
        return {key: value for key, value in row.items() if key != "user_id"}
    settings = {
        "provider": "ollama", "base_url": "http://127.0.0.1:11434",
        "model": "qwen2.5:7b", "api_key": "", "temperature": 0.7,
        "top_p": 0.9, "max_tokens": 2048, "timeout_seconds": 60,
    }
    env = ecnu_model_env()
    if env.get("ECNU_API_BASE_URL") and env.get("ECNU_MODEL_NAME"):
        settings.update(
            provider="remote_api", base_url=env["ECNU_API_BASE_URL"].rstrip("/"),
            model=env["ECNU_MODEL_NAME"], api_key=env.get("ECNU_API_KEY", ""),
        )
        if env.get("ECNU_API_PROTOCOL", "").lower() in {"responses", "openai_responses", "openai-response"}:
            settings["provider"] = "openai_responses"
    return settings


def public_settings(settings):
    return {**{k: v for k, v in settings.items() if k != "api_key"}, "has_api_key": bool(settings["api_key"])}


PROFILE_SETTING_FIELDS = (
    "provider", "base_url", "model", "api_key",
    "temperature", "top_p", "max_tokens", "timeout_seconds",
)


def settings_from_profile(profile):
    """Build a runtime settings dict from a ``model_profiles`` row.

    Mirrors :func:`load_settings` so a conversation can call the same
    ``llm.chat`` path with a per-conversation model selection.
    """

    if not profile:
        return None
    settings = {field: profile.get(field) for field in PROFILE_SETTING_FIELDS}
    settings["api_key"] = profile.get("api_key") or ""
    settings["api_protocol"] = profile.get("api_protocol") or ""
    settings["headers"] = json.loads(profile.get("headers_json") or "{}")
    return settings


def load_settings_for_profile(db, user_id, profile_id):
    """Return settings for ``profile_id`` owned by ``user_id``.

    Falls back to the currently active settings when the profile is missing,
    so a deleted profile never breaks an ongoing conversation.
    """

    if not profile_id:
        return load_settings(db, user_id)
    row = db.one("SELECT * FROM model_profiles WHERE user_id=? AND id=?", (user_id, profile_id))
    if row and row.get("model_type", "llm") != "llm":
        raise ValueError("所选模型不是大语言模型，请在模型设置中重新选择")
    return settings_from_profile(row) or load_settings(db, user_id)


def _legacy_chat(settings, messages, json_mode=False):
    provider = settings["provider"]
    if provider == "openai_responses":
        if json_mode:
            return json.dumps(call_openai_responses_json(
                messages=messages, model=settings["model"], base_url=settings["base_url"],
                api_key=settings["api_key"], temperature=settings["temperature"],
                max_tokens=settings["max_tokens"], timeout_seconds=settings["timeout_seconds"],
            ), ensure_ascii=False)
        return call_openai_responses_text(
            messages=messages, model=settings["model"], base_url=settings["base_url"],
            api_key=settings["api_key"], temperature=settings["temperature"],
            max_tokens=settings["max_tokens"], timeout_seconds=settings["timeout_seconds"],
        )
    base = settings["base_url"].rstrip("/")
    headers = {"Content-Type": "application/json"}
    payload = {"model": settings["model"], "messages": messages, "stream": False}
    params = None
    if provider == "ollama":
        url = f"{base}/api/chat"
        payload["options"] = {
            "temperature": settings["temperature"], "top_p": settings["top_p"],
            "num_predict": settings["max_tokens"],
        }
        if json_mode:
            payload["format"] = "json"
    else:
        url = _normalize_openai_base_url(base)
        if urlsplit(url).hostname == "chat.ecnu.edu.cn" and not settings["api_key"]:
            raise ValueError("ECNU API Key 未配置，请填写 .env 的 ECNU_API_KEY 或在设置中保存密钥")
        if settings["api_key"]:
            headers["Authorization"] = f"Bearer {settings['api_key']}"
        payload.update({k: settings[k] for k in ("temperature", "top_p", "max_tokens")})
        if provider == "vivo":
            payload["thinking"] = {"type": "disabled"}
            params = _vivo_params()
    try:
        response = requests.post(
            url, headers=headers, params=params, json=payload,
            timeout=(10, settings["timeout_seconds"]),
        )
    except requests.RequestException as exc:
        logger.warning("Model transport failed: %s", error_diagnostics(exc))
        raise
    response.raise_for_status()
    result = response.json()
    if provider == "vivo":
        _raise_for_vivo_error(result)
    # Reject provider error objects rather than displaying JSON as a reply.
    if not isinstance(result, dict) or not (result.get("choices") or result.get("message")):
        raise ValueError("模型接口没有返回有效回复")
    message = result.get("message")
    choices = result.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("模型返回空回复")
    return content.strip()


def chat(settings, messages, json_mode=False):
    """Use the LangChain runtime when installed, with a HTTP compatibility path."""
    from backend.app.ai.providers.api_types import TRANSPORTS, get_transport
    from backend.app.ai.providers.schemas import normalize_api_type

    api = normalize_api_type(settings.get("api_protocol") or settings.get("provider"))
    if api in {"anthropic-messages", "google-generative-ai", "vivo", "openai-responses"} or (
        settings.get("api_protocol") and api in TRANSPORTS
    ):
        return get_transport(api)(
            messages=messages, model=settings["model"], base_url=settings["base_url"],
            api_key=settings.get("api_key"), temperature=settings.get("temperature", 0.7),
            max_tokens=settings.get("max_tokens", 2048), timeout_seconds=settings.get("timeout_seconds", 60),
            headers=settings.get("headers"), json_mode=json_mode,
        )
    if settings.get("provider") == "openai_responses":
        return _legacy_chat(settings, messages, json_mode=json_mode)
    try:
        from backend.app.ai.runtime import invoke_chat, invoke_json
        if json_mode:
            return json.dumps(invoke_json(settings, messages), ensure_ascii=False)
        return invoke_chat(settings, messages)
    except (ImportError, ModuleNotFoundError):
        return _legacy_chat(settings, messages, json_mode=json_mode)


def extract(settings, chapter):
    from backend.app.ai.extraction_graph import extract_chapter
    return extract_chapter(settings, chapter["title"], chapter["content"], chapter)


def _legacy_extract(settings, chapter):
    return extract(settings, chapter)


def error_message(exc):
    if isinstance(exc, requests.Timeout):
        return "模型请求超时，请检查模型状态或增加超时时间"
    if isinstance(exc, requests.exceptions.ProxyError):
        return "连接模型服务的代理失败，请检查后端使用的系统代理或 HTTP_PROXY / HTTPS_PROXY"
    if isinstance(exc, requests.exceptions.SSLError):
        return "模型服务 TLS 连接或证书校验失败，请检查证书、系统时间及 HTTPS 代理"
    if isinstance(exc, requests.ConnectionError):
        return "无法连接模型服务，请检查服务地址、DNS、网络、防火墙及代理；仅本地 Ollama 需要启动模型"
    if isinstance(exc, requests.HTTPError):
        return f"模型接口返回 HTTP {exc.response.status_code}，请检查凭据、模型名称和额度"
    status = getattr(exc, "status_code", None)
    if status is not None:
        return f"模型接口返回 HTTP {status}，请检查凭据、模型名称和额度"
    if type(exc).__name__ in {"APITimeoutError", "ReadTimeout", "ConnectTimeout"}:
        return "模型请求超时，请检查模型状态或增加超时时间"
    if type(exc).__name__ in {"APIConnectionError", "ConnectError", "RemoteProtocolError"}:
        return "无法连接模型服务，请检查地址、网络、代理和证书"
    if isinstance(exc, (ValueError, RuntimeError)):
        return str(exc)[:500]
    return "处理失败，请查看后端日志"
