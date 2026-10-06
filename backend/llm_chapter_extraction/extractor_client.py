import json
import re
from typing import Any

from backend.llm_dispatch.llm_client import call_llm_json


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


def call_ollama_json(
    text_or_documents: str,
    prompt_description: str,
    model: str,
    base_url: str,
    temperature: float = 0.1,
    timeout_seconds: int = 60,
    provider: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
) -> dict:
    chosen_model = model_name or model
    return call_llm_json(
        text_or_documents=text_or_documents,
        prompt_description=prompt_description,
        model=chosen_model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        provider=provider,
        api_key=api_key,
    )
