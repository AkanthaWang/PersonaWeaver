from __future__ import annotations

import json
import re
import uuid
from typing import Any

import requests


DEFAULT_EXAMPLE = {
    "characters": [
        {
            "name": "石野",
            "behavior": ["大喊", "紧握拳头", "看向镜子"],
            "speech": ["我不信！"],
            "psychology": ["质疑"],
        }
    ]
}


def _extract_json_content(result_json: Any) -> str:
    content: Any = ""

    if isinstance(result_json, dict):
        choices = result_json.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content", "") or message.get("text", "")
                if not content and isinstance(first_choice.get("text"), str):
                    content = first_choice.get("text", "")

        if not content and isinstance(result_json.get("message"), dict):
            content = result_json["message"].get("content", "")

        if not content and "output" in result_json:
            out = result_json["output"]
            if isinstance(out, list) and out and isinstance(out[0], dict):
                content = out[0].get("content", "") or out[0].get("text", "")
            elif isinstance(out, str):
                content = out

    if not content:
        content = json.dumps(result_json, ensure_ascii=False)

    return str(content)


def _extract_text_content(result_json: Any) -> str:
    return _extract_json_content(result_json).strip()


def _normalize_openai_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _build_messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _vivo_params(request_id: str | None = None) -> dict[str, str]:
    return {"request_id": request_id or str(uuid.uuid4())}


def _raise_for_vivo_error(result_json: Any) -> None:
    if not isinstance(result_json, dict):
        return
    code = result_json.get("code")
    msg = result_json.get("msg") or result_json.get("message")
    if code in {1001, 1007, 2003, 30001}:
        raise RuntimeError(f"vivo AIGC error {code}: {msg or result_json}")
    if str(msg).strip() in {"429", "inner error"}:
        raise RuntimeError(f"vivo AIGC rate limit: {msg}")


def _parse_json_payload(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except Exception:
        cleaned = re.sub(r"```json\s*|```", "", content).strip()
        parsed = json.loads(cleaned)

    return parsed if isinstance(parsed, dict) else {}


def _call_ollama_json(
    *,
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    temperature: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    system_prompt = f"""
你是一个专业的小说分析助手。请根据用户提供的文本片段，提取关键信息。
请严格输出合法 JSON，不要输出 Markdown 代码块。
如果某项没有信息，请不要输出该字段。
参考结构：{json.dumps(DEFAULT_EXAMPLE, ensure_ascii=False)}
"""

    user_prompt = f"""
【提取任务】：{prompt_description}
【原文片段】：
{text_or_documents}
"""

    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature},
    }

    resp = requests.post(url, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    result_json = resp.json()
    content = _extract_json_content(result_json)
    return _parse_json_payload(content)


def _call_remote_chat_json(
    *,
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    system_prompt = f"""
你是一个专业的小说分析助手。请根据用户提供的文本片段，提取关键信息。
请严格输出合法 JSON，不要输出 Markdown 代码块。
如果某项没有信息，请不要输出该字段。
参考结构：{json.dumps(DEFAULT_EXAMPLE, ensure_ascii=False)}
"""

    user_prompt = f"""
【提取任务】：{prompt_description}
【原文片段】：
{text_or_documents}
"""

    url = _normalize_openai_base_url(base_url)
    payload = {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "stream": False,
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    result_json = resp.json()
    content = _extract_json_content(result_json)
    return _parse_json_payload(content)


def _call_vivo_chat_json(
    *,
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    timeout_seconds: int,
    request_id: str | None = None,
) -> dict[str, Any]:
    system_prompt = f"""
你是一个专业的小说分析助手。请根据用户提供的文本片段，提取关键信息。
请严格输出合法 JSON，不要输出 Markdown 代码块。
如果某项没有信息，请不要输出该字段。
参考结构：{json.dumps(DEFAULT_EXAMPLE, ensure_ascii=False)}
"""

    user_prompt = f"""
【提取任务】：{prompt_description}
【原文片段】：
{text_or_documents}
"""

    payload = {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "stream": False,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {api_key}",
    }

    resp = requests.post(
        _normalize_openai_base_url(base_url),
        headers=headers,
        params=_vivo_params(request_id),
        json=payload,
        # (连接超时, 读取超时)：避免 vivo 响应挂起时傻等单一大超时。
        # 连接 15s；读取上限取 timeout_seconds 与 120s 的较小值。
        timeout=(15, min(int(timeout_seconds) if timeout_seconds else 120, 120)),
    )
    resp.raise_for_status()
    result_json = resp.json()
    _raise_for_vivo_error(result_json)
    content = _extract_json_content(result_json)
    return _parse_json_payload(content)


def _call_ollama_text(
    *,
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    temperature: float,
    timeout_seconds: int,
) -> str:
    system_prompt = """
你是一个专业的小说分析助手。请根据用户提供的文本片段，直接输出符合要求的 Markdown 内容。
不要输出 JSON，不要输出代码块，不要输出额外解释。
"""

    user_prompt = f"""
【提取任务】：{prompt_description}
【原文片段】：
{text_or_documents}
"""

    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "stream": False,
        "options": {"temperature": temperature},
    }

    resp = requests.post(url, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    result_json = resp.json()
    return _extract_text_content(result_json)


def _call_remote_chat_text(
    *,
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    timeout_seconds: int,
) -> str:
    system_prompt = """
你是一个专业的小说分析助手。请根据用户提供的文本片段，直接输出符合要求的 Markdown 内容。
不要输出 JSON，不要输出代码块，不要输出额外解释。
"""

    user_prompt = f"""
【提取任务】：{prompt_description}
【原文片段】：
{text_or_documents}
"""

    url = _normalize_openai_base_url(base_url)
    payload = {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "stream": False,
        "temperature": temperature,
    }
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    result_json = resp.json()
    return _extract_text_content(result_json)


def _call_vivo_chat_text(
    *,
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    timeout_seconds: int,
    request_id: str | None = None,
) -> str:
    system_prompt = """
你是一个专业的小说分析助手。请根据用户提供的文本片段，直接输出符合要求的 Markdown 内容。
不要输出 JSON，不要输出代码块，不要输出额外解释。
"""

    user_prompt = f"""
【提取任务】：{prompt_description}
【原文片段】：
{text_or_documents}
"""

    payload = {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "stream": False,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
    }
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {api_key}",
    }

    resp = requests.post(
        _normalize_openai_base_url(base_url),
        headers=headers,
        params=_vivo_params(request_id),
        json=payload,
        timeout=(15, min(int(timeout_seconds) if timeout_seconds else 120, 120)),
    )
    resp.raise_for_status()
    result_json = resp.json()
    _raise_for_vivo_error(result_json)
    return _extract_text_content(result_json)


def call_llm_json(
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    temperature: float = 0.1,
    timeout_seconds: int = 60,
    provider: str | None = None,
    api_key: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    resolved_provider = (provider or "").strip().lower()
    if not resolved_provider:
        if api_key or "chat/completions" in base_url or "/open/api/v1" in base_url:
            resolved_provider = "remote_api"
        else:
            resolved_provider = "ollama"

    if resolved_provider in {"vivo", "vivo_aigc"}:
        if not api_key:
            raise ValueError("vivo AIGC provider requires api_key")
        return _call_vivo_chat_json(
            text_or_documents=text_or_documents,
            prompt_description=prompt_description,
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            request_id=request_id,
        )

    if resolved_provider in {"remote_api", "openai", "openai_compatible", "ecnu", "glm", "bigmodel"}:
        if not api_key:
            raise ValueError("Remote LLM provider requires api_key")
        return _call_remote_chat_json(
            text_or_documents=text_or_documents,
            prompt_description=prompt_description,
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    return _call_ollama_json(
        text_or_documents=text_or_documents,
        prompt_description=prompt_description,
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )


def call_llm_text(
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    temperature: float = 0.1,
    timeout_seconds: int = 60,
    provider: str | None = None,
    api_key: str | None = None,
    request_id: str | None = None,
) -> str:
    resolved_provider = (provider or "").strip().lower()
    if not resolved_provider:
        if api_key or "chat/completions" in base_url or "/open/api/v1" in base_url:
            resolved_provider = "remote_api"
        else:
            resolved_provider = "ollama"

    if resolved_provider in {"vivo", "vivo_aigc"}:
        if not api_key:
            raise ValueError("vivo AIGC provider requires api_key")
        return _call_vivo_chat_text(
            text_or_documents=text_or_documents,
            prompt_description=prompt_description,
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            request_id=request_id,
        )

    if resolved_provider in {"remote_api", "openai", "openai_compatible", "ecnu", "glm", "bigmodel"}:
        if not api_key:
            raise ValueError("Remote LLM provider requires api_key")
        return _call_remote_chat_text(
            text_or_documents=text_or_documents,
            prompt_description=prompt_description,
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    return _call_ollama_text(
        text_or_documents=text_or_documents,
        prompt_description=prompt_description,
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )
