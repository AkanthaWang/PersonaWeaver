"""Provider-neutral LangChain runtime.

Imports are intentionally lazy so the existing local API can still boot while
optional AI packages are being installed or when a user only needs parsing.
"""

from __future__ import annotations

import json
from typing import Any


def _base_url(settings: dict[str, Any]) -> str:
    value = str(settings.get("base_url") or "").rstrip("/")
    if value.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")]
    return value


def _model(settings: dict[str, Any]):
    provider = settings.get("provider", "ollama")
    common = {"model": settings.get("model", "qwen2.5:7b"), "temperature": settings.get("temperature", 0.7)}
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            base_url=_base_url(settings),
            num_predict=settings.get("max_tokens", 2048),
            timeout=settings.get("timeout_seconds", 60),
            **common,
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        base_url=_base_url(settings),
        api_key=settings.get("api_key") or "local-placeholder",
        max_tokens=settings.get("max_tokens", 2048),
        timeout=settings.get("timeout_seconds", 60),
        max_retries=settings.get("max_retries", 2),
        default_headers=settings.get("headers") or None,
        **common,
    )


def _messages(messages: list[dict[str, str]]):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    output = []
    for message in messages:
        role, content = message.get("role", "user"), message.get("content", "")
        cls = SystemMessage if role == "system" else AIMessage if role == "assistant" else HumanMessage
        output.append(cls(content=content))
    return output


def invoke_chat(settings: dict[str, Any], messages: list[dict[str, str]]) -> str:
    """Invoke a LangChain chat model and normalize its response to text."""

    response = _model(settings).invoke(_messages(messages))
    content = getattr(response, "content", response)
    if isinstance(content, list):
        content = "".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    content = str(content).strip()
    if not content:
        raise ValueError("模型返回空回复")
    return content


def invoke_json(settings: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
    """Invoke a model and parse a JSON object from its response."""

    text = invoke_chat(settings, messages)
    cleaned = text.replace("```json", "").replace("```", "").strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("模型没有返回 JSON 对象")
    return value
