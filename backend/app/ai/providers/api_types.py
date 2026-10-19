"""HTTP transports for each API type.

Mirrors the per-protocol modules under ``pi-ai/dist/api`` (``openai-completions``,
``openai-responses``, ``anthropic-messages``, ``google-generative-ai``) and keeps
``ollama`` / ``vivo`` which this project already used.

Every transport accepts the same keyword arguments and returns plain text. JSON
parsing is handled by the caller so the request builders stay side-effect free
and easy to test.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import requests

from ..prompts.protocol import ANTHROPIC_JSON_SUFFIX


class ModelResponseError(RuntimeError):
    """Raised when a provider response contains no usable model text."""


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def join_url(base_url: str, *suffixes: str) -> str:
    """Join a base URL with a path, tolerating already-suffixed inputs."""

    value = (base_url or "").rstrip("/")
    for suffix in suffixes:
        if suffix and value.endswith(suffix):
            return value
    return f"{value}/{suffixes[0]}" if suffixes else value


def normalize_openai_base_url(base_url: str) -> str:
    """Return ``<base>/chat/completions`` from any OpenAI-compatible base URL."""

    value = (base_url or "").rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if value.endswith(suffix):
            return f"{value[: -len(suffix)]}/chat/completions"
    return f"{value}/chat/completions"


def normalize_openai_responses_url(base_url: str) -> str:
    """Return ``<base>/responses`` from any OpenAI-compatible base URL."""

    value = (base_url or "").rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return f"{value}/responses"


def avatar_headers(api_key: str, explicit: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if explicit:
        headers.update({str(k): str(v) for k, v in explicit.items() if k})
    return headers


def extract_openai_content(result_json: Any) -> str:
    """Read assistant text from a Chat Completions style payload.

    Never fall back to the raw provider envelope: doing so makes an empty or
    truncated completion look like model-authored JSON and produces confusing
    schema errors much later.
    """

    content: Any = ""
    if isinstance(result_json, str):
        content = result_json
    elif isinstance(result_json, list):
        content = result_json
    elif isinstance(result_json, dict):
        choices = result_json.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                content = message.get("content") or message.get("text") or ""
            if not content and isinstance(choices[0].get("text"), str):
                content = choices[0]["text"]
        if not content and isinstance(result_json.get("message"), dict):
            content = result_json["message"].get("content", "")
        if not content and "output" in result_json:
            output = result_json["output"]
            if isinstance(output, list) and output and isinstance(output[0], dict):
                content = output[0].get("content") or output[0].get("text") or ""
            elif isinstance(output, str):
                content = output
        if not content:
            for key in ("content", "text", "response"):
                value = result_json.get(key)
                if isinstance(value, (str, list)):
                    content = value
                    break
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content
        )
    text = str(content).strip()
    if text:
        return text

    details = []
    if isinstance(result_json, dict):
        choices = result_json.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            reason = choices[0].get("finish_reason")
            if reason:
                details.append(f"finish_reason={reason}")
            message = choices[0].get("message")
            if isinstance(message, dict) and message.get("reasoning_content") and not message.get("content"):
                details.append("仅返回 reasoning_content")
        usage = result_json.get("usage")
        if isinstance(usage, dict):
            tokens = {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                      if usage.get(key) is not None}
            if tokens:
                details.append("usage=" + json.dumps(tokens, ensure_ascii=False))
        error = result_json.get("error")
        if error:
            details.append("error=" + json.dumps(error, ensure_ascii=False)[:300])
    suffix = f"（{'；'.join(details)}）" if details else ""
    raise ModelResponseError(
        "模型接口没有返回可解析的文本内容" + suffix
        + "；请检查是否达到最大输出 token、模型是否只返回推理内容，或更换模型后重试"
    )


def extract_responses_content(result_json: Any) -> str:
    """Read text from a Responses API ``output_text`` or nested ``output`` items."""

    if isinstance(result_json, dict):
        output_text = result_json.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        output = result_json.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append(part["text"])
                elif isinstance(item.get("text"), str):
                    parts.append(item["text"])
            if parts:
                return "".join(parts).strip()
    return ""


def extract_anthropic_content(result_json: Any) -> str:
    """Read text blocks from an Anthropic Messages payload."""

    if isinstance(result_json, dict):
        blocks = result_json.get("content")
        if isinstance(blocks, list):
            parts = [
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") in {None, "text"}
            ]
            if any(part for part in parts):
                return "".join(parts).strip()
        if isinstance(result_json.get("completion"), str):
            return result_json["completion"].strip()
    return ""


def extract_google_content(result_json: Any) -> str:
    """Read text parts from a Google Generative AI payload."""

    if isinstance(result_json, dict):
        candidates = result_json.get("candidates")
        if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
            content = candidates[0].get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    text = "".join(
                        part.get("text", "")
                        for part in parts
                        if isinstance(part, dict) and isinstance(part.get("text"), str)
                    )
                    if text.strip():
                        return text.strip()
    return ""


def parse_json_payload(content: str) -> dict[str, Any]:
    """Parse a model reply into a dict, tolerating ```json fences."""

    try:
        parsed = json.loads(content)
    except Exception:
        cleaned = re.sub(r"```json\s*|```", "", content).strip()
        parsed = json.loads(cleaned)
    return parsed if isinstance(parsed, dict) else {}


def _messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"role": message.get("role", "user"), "content": message.get("content", "")}
        for message in messages
    ]


# --------------------------------------------------------------------------- #
# openai-completions
# --------------------------------------------------------------------------- #
def call_openai_completions(
    *,
    messages: list[dict[str, str]],
    model: str,
    base_url: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    json_mode: bool = False,
    sampling_params: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": _messages(messages),
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if sampling_params:
        payload.update(sampling_params)
    response = requests.post(
        normalize_openai_base_url(base_url),
        headers=avatar_headers(api_key or "", headers),
        json=payload,
        timeout=(10, timeout_seconds),
    )
    response.raise_for_status()
    content = extract_openai_content(response.json()).strip()
    if not content:
        raise ValueError("模型返回空回复")
    return content


# --------------------------------------------------------------------------- #
# openai-responses
# --------------------------------------------------------------------------- #
def call_openai_responses(
    *,
    messages: list[dict[str, str]],
    model: str,
    base_url: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    json_mode: bool = False,
    sampling_params: dict[str, Any] | None = None,
) -> str:
    if not api_key:
        raise ValueError("OpenAI Responses provider requires api_key")
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": message.get("role", "user"),
                "content": [{"type": "input_text", "text": message.get("content", "")}],
            }
            for message in messages
        ],
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if json_mode:
        payload["text"] = {"format": {"type": "json_object"}}
    if sampling_params:
        payload.update(sampling_params)
    response = requests.post(
        normalize_openai_responses_url(base_url),
        headers=avatar_headers(api_key, headers),
        json=payload,
        timeout=(10, timeout_seconds),
    )
    response.raise_for_status()
    content = extract_responses_content(response.json())
    if not content:
        raise ValueError("Responses API 没有返回可读文本")
    return content


# --------------------------------------------------------------------------- #
# anthropic-messages
# --------------------------------------------------------------------------- #
def call_anthropic_messages(
    *,
    messages: list[dict[str, str]],
    model: str,
    base_url: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    json_mode: bool = False,
    sampling_params: dict[str, Any] | None = None,
) -> str:
    if not api_key:
        raise ValueError("Anthropic provider requires api_key")
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    turns = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in messages
        if m.get("role") != "system"
    ]
    if json_mode and system_parts:
        system_parts.append(ANTHROPIC_JSON_SUFFIX)
    payload: dict[str, Any] = {
        "model": model,
        "messages": turns or [{"role": "user", "content": ""}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if sampling_params:
        payload.update(sampling_params)
    request_headers = {
        "anthropic-version": "2023-06-01",
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items() if k})
    response = requests.post(
        join_url(base_url, "messages"),
        headers=request_headers,
        json=payload,
        timeout=(10, timeout_seconds),
    )
    response.raise_for_status()
    content = extract_anthropic_content(response.json())
    if not content:
        raise ValueError("Anthropic API 没有返回可读文本")
    return content


# --------------------------------------------------------------------------- #
# google-generative-ai
# --------------------------------------------------------------------------- #
def call_google_generative_ai(
    *,
    messages: list[dict[str, str]],
    model: str,
    base_url: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    json_mode: bool = False,
    sampling_params: dict[str, Any] | None = None,
) -> str:
    if not api_key:
        raise ValueError("Google Generative AI provider requires api_key")
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    contents = [
        {
            "role": "model" if m.get("role") == "assistant" else "user",
            "parts": [{"text": m.get("content", "")}],
        }
        for m in messages
        if m.get("role") != "system"
    ]
    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
    }
    if json_mode:
        generation_config["responseMimeType"] = "application/json"
    if sampling_params:
        generation_config.update(sampling_params)
    payload: dict[str, Any] = {"contents": contents, "generationConfig": generation_config}
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    url = f"{join_url(base_url, 'models')}/{model}:generateContent"
    request_headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items() if k})
    response = requests.post(
        url,
        headers=request_headers,
        json=payload,
        timeout=(10, timeout_seconds),
    )
    response.raise_for_status()
    content = extract_google_content(response.json())
    if not content:
        raise ValueError("Google Generative AI 没有返回可读文本")
    return content


# --------------------------------------------------------------------------- #
# ollama (native /api/chat)
# --------------------------------------------------------------------------- #
def call_ollama(
    *,
    messages: list[dict[str, str]],
    model: str,
    base_url: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    json_mode: bool = False,
    sampling_params: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": _messages(messages),
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if json_mode:
        payload["format"] = "json"
    if sampling_params:
        payload["options"].update(sampling_params)
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items() if k})
    response = requests.post(
        join_url(base_url, "api/chat"),
        headers=request_headers,
        json=payload,
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    content = extract_openai_content(response.json()).strip()
    if not content:
        raise ValueError("模型返回空回复")
    return content


# --------------------------------------------------------------------------- #
# vivo AIGC
# --------------------------------------------------------------------------- #
VIVO_ERROR_CODES = {1001, 1007, 2003, 30001}


def raise_for_vivo_error(result_json: Any) -> None:
    if not isinstance(result_json, dict):
        return
    code = result_json.get("code")
    msg = result_json.get("msg") or result_json.get("message")
    if code in VIVO_ERROR_CODES:
        raise RuntimeError(f"vivo AIGC error {code}: {msg or result_json}")
    if str(msg).strip() in {"429", "inner error"}:
        raise RuntimeError(f"vivo AIGC rate limit: {msg}")


def call_vivo(
    *,
    messages: list[dict[str, str]],
    model: str,
    base_url: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    json_mode: bool = False,
    sampling_params: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> str:
    if not api_key:
        raise ValueError("vivo AIGC provider requires api_key")
    payload: dict[str, Any] = {
        "model": model,
        "messages": _messages(messages),
        "stream": False,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if sampling_params:
        payload.update(sampling_params)
    request_headers = {"Content-Type": "application/json; charset=utf-8", "Authorization": f"Bearer {api_key}"}
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items() if k})
    response = requests.post(
        normalize_openai_base_url(base_url),
        headers=request_headers,
        params={"request_id": request_id or str(uuid.uuid4())},
        json=payload,
        timeout=(15, min(int(timeout_seconds) if timeout_seconds else 120, 120)),
    )
    response.raise_for_status()
    result_json = response.json()
    raise_for_vivo_error(result_json)
    content = extract_openai_content(result_json).strip()
    if not content:
        raise ValueError("模型返回空回复")
    return content


TRANSPORTS = {
    "openai-completions": call_openai_completions,
    "openai-responses": call_openai_responses,
    "anthropic-messages": call_anthropic_messages,
    "google-generative-ai": call_google_generative_ai,
    "ollama": call_ollama,
    "vivo": call_vivo,
}


def get_transport(api_type: str):
    """Return the transport callable for an API type, defaulting to completions."""

    return TRANSPORTS.get(api_type, call_openai_completions)


__all__ = [
    "TRANSPORTS",
    "get_transport",
    "join_url",
    "normalize_openai_base_url",
    "normalize_openai_responses_url",
    "parse_json_payload",
    "extract_openai_content",
    "extract_responses_content",
    "ModelResponseError",
    "extract_anthropic_content",
    "extract_google_content",
    "raise_for_vivo_error",
    "call_openai_completions",
    "call_openai_responses",
    "call_anthropic_messages",
    "call_google_generative_ai",
    "call_ollama",
    "call_vivo",
]
