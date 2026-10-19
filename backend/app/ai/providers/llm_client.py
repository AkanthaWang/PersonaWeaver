"""Legacy LLM client facade.

The actual provider logic now lives in the Pi-style registry
(:mod:`backend.app.ai.providers.registry` + :mod:`api_types`). This module keeps
the historical function signatures working so existing callers and tests do not
have to change.

The public helpers ``call_llm_json`` / ``call_llm_text`` accept the same keyword
arguments as before; ``provider`` values are mapped onto API types, so for
example ``provider="remote_api"`` still produces an OpenAI Chat Completions
request.
"""

from __future__ import annotations

from typing import Any

from . import api_types
from .api_types import (  # re-exported for backwards compatibility
    extract_openai_content as _extract_json_content,
    normalize_openai_base_url as _normalize_openai_base_url,
    normalize_openai_responses_url as _normalize_openai_responses_url,
    parse_json_payload as _parse_json_payload,
    raise_for_vivo_error as _raise_for_vivo_error,
)
from .registry import get_registry
from .schemas import normalize_api_type
from ..prompts.extraction import (
    LEGACY_EXAMPLE,
    LEGACY_EXTRACTION_SYSTEM_PROMPT,
    LEGACY_TEXT_SYSTEM_PROMPT,
    LEGACY_USER_PROMPT_TEMPLATE,
)

DEFAULT_EXAMPLE = LEGACY_EXAMPLE


def _extract_text_content(result_json: Any) -> str:
    return _extract_json_content(result_json).strip()


def _build_messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _vivo_params(request_id: str | None = None) -> dict[str, str]:
    import uuid

    return {"request_id": request_id or str(uuid.uuid4())}


def _resolve_api(provider: str | None, base_url: str, api_key: str | None) -> str:
    resolved = normalize_api_type(provider)
    if resolved:
        return resolved
    if api_key or "chat/completions" in base_url or "/open/api/v1" in base_url:
        return "openai-completions"
    return "ollama"


def _call_llm(
    *,
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    temperature: float,
    timeout_seconds: int,
    provider: str | None,
    api_key: str | None,
    request_id: str | None,
    json_mode: bool,
) -> str:
    import json

    system_prompt = (
        LEGACY_EXTRACTION_SYSTEM_PROMPT.format(example=json.dumps(DEFAULT_EXAMPLE, ensure_ascii=False))
        if json_mode
        else LEGACY_TEXT_SYSTEM_PROMPT
    )
    user_prompt = LEGACY_USER_PROMPT_TEMPLATE.format(
        description=prompt_description, documents=text_or_documents,
    )
    messages = _build_messages(system_prompt, user_prompt)
    api = _resolve_api(provider, base_url, api_key)
    transport = api_types.get_transport(api)
    if not api_key and api in {"openai-responses", "anthropic-messages", "google-generative-ai", "vivo"}:
        raise ValueError(f"{api} provider requires api_key")
    if not api_key and api == "openai-completions" and provider:
        raise ValueError("Remote LLM provider requires api_key")
    kwargs: dict[str, Any] = {
        "messages": messages,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "temperature": temperature,
        "max_tokens": 2048,
        "timeout_seconds": timeout_seconds,
        "json_mode": json_mode,
    }
    if api == "vivo":
        kwargs["request_id"] = request_id
    return transport(**kwargs)


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
    content = _call_llm(
        text_or_documents=text_or_documents,
        prompt_description=prompt_description,
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        provider=provider,
        api_key=api_key,
        request_id=request_id,
        json_mode=True,
    )
    return _parse_json_payload(content)


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
    return _call_llm(
        text_or_documents=text_or_documents,
        prompt_description=prompt_description,
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        provider=provider,
        api_key=api_key,
        request_id=request_id,
        json_mode=False,
    )


def call_openai_responses_text(*, messages, model, base_url, api_key, temperature=0.7, max_tokens=2048, timeout_seconds=60):
    return api_types.call_openai_responses(
        messages=messages, model=model, base_url=base_url, api_key=api_key,
        temperature=temperature, max_tokens=max_tokens, timeout_seconds=timeout_seconds,
    )


def call_openai_responses_json(*, messages, model, base_url, api_key, temperature=0.1, max_tokens=2048, timeout_seconds=60):
    content = api_types.call_openai_responses(
        messages=messages, model=model, base_url=base_url, api_key=api_key,
        temperature=temperature, max_tokens=max_tokens, timeout_seconds=timeout_seconds,
        json_mode=True,
    )
    return _parse_json_payload(content)


__all__ = [
    "call_llm_json",
    "call_llm_text",
    "call_openai_responses_json",
    "call_openai_responses_text",
    "get_registry",
    "DEFAULT_EXAMPLE",
]
