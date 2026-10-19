"""Pydantic mirror of Pi's ``models.json`` schema.

Pi defines these structures with TypeBox in
``packages/coding-agent/src/core/model-config.ts``. This module keeps the same
field names (``baseUrl``, ``apiKey``, ``contextWindow`` ...) so an existing
``models.json`` file can be reused verbatim, while adding snake_case aliases for
the Python side of the code base.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ApiType = Literal[
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
    "google-generative-ai",
    "ollama",
    "vivo",
]

KNOWN_API_TYPES: tuple[str, ...] = (
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
    "google-generative-ai",
    "ollama",
    "vivo",
)


class _Base(BaseModel):
    """Accept both camelCase (Pi) and snake_case (project) keys."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        protected_namespaces=(),
    )


class ModelCost(_Base):
    input: float = 0.0
    output: float = 0.0
    cache_read: float = Field(default=0.0, alias="cacheRead")
    cache_write: float = Field(default=0.0, alias="cacheWrite")


class ThinkingLevelMap(_Base):
    off: str | None = None
    minimal: str | None = None
    low: str | None = None
    medium: str | None = None
    high: str | None = None
    xhigh: str | None = None
    max: str | None = None


class ModelDefinition(_Base):
    """One entry inside a provider's ``models`` array."""

    id: str = Field(min_length=1)
    name: str | None = None
    api: str | None = None
    base_url: str | None = Field(default=None, alias="baseUrl")
    reasoning: bool = False
    thinking_level_map: ThinkingLevelMap | None = Field(default=None, alias="thinkingLevelMap")
    input: list[Literal["text", "image"]] = Field(default_factory=lambda: ["text"])
    cost: ModelCost = Field(default_factory=ModelCost)
    context_window: int = Field(default=128_000, alias="contextWindow")
    max_tokens: int = Field(default=16_384, alias="maxTokens")
    sampling_params: dict[str, Any] | None = Field(default=None, alias="samplingParams")
    headers: dict[str, str] = Field(default_factory=dict)
    compat: dict[str, Any] = Field(default_factory=dict)


class ProviderConfig(_Base):
    """One provider entry in ``models.json``."""

    name: str | None = None
    base_url: str | None = Field(default=None, alias="baseUrl")
    api_key: str | None = Field(default=None, alias="apiKey")
    api: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    auth_header: bool | None = Field(default=None, alias="authHeader")
    compat: dict[str, Any] = Field(default_factory=dict)
    models: list[ModelDefinition] = Field(default_factory=list)


class ModelsConfig(_Base):
    """Top level ``models.json`` document: ``{"providers": {...}}``."""

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


class ResolvedModel(_Base):
    """Flattened runtime view of one model (registry output)."""

    provider: str
    provider_name: str
    id: str
    name: str
    api: str
    base_url: str
    api_key: str | None = None
    auth_header: bool = False
    headers: dict[str, str] = Field(default_factory=dict)
    reasoning: bool = False
    input: list[str] = Field(default_factory=lambda: ["text"])
    cost: ModelCost = Field(default_factory=ModelCost)
    context_window: int = 128_000
    max_tokens: int = 16_384
    sampling_params: dict[str, Any] = Field(default_factory=dict)
    compat: dict[str, Any] = Field(default_factory=dict)


# Built-in provider defaults. Custom entries for the same id inherit these,
# matching Pi's "override built-in provider" behaviour.
BUILTIN_PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "name": "Ollama",
        "api": "ollama",
        "baseUrl": "http://127.0.0.1:11434",
    },
    "openai": {
        "name": "OpenAI",
        "api": "openai-completions",
        "baseUrl": "https://api.openai.com/v1",
    },
    "openai-responses": {
        "name": "OpenAI Responses",
        "api": "openai-responses",
        "baseUrl": "https://api.openai.com/v1",
    },
    "anthropic": {
        "name": "Anthropic",
        "api": "anthropic-messages",
        "baseUrl": "https://api.anthropic.com/v1",
    },
    "google": {
        "name": "Google Generative AI",
        "api": "google-generative-ai",
        "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
    },
    "vivo": {
        "name": "vivo AIGC",
        "api": "vivo",
        "baseUrl": "https://api-ai.vivo.com.cn/v1",
    },
    "ecnu": {
        "name": "ECNU",
        "api": "openai-completions",
        "baseUrl": "https://chat.ecnu.edu.cn/open/api/v1",
    },
}

# Maps the legacy ``provider`` column values onto the new API-type vocabulary.
LEGACY_PROVIDER_ALIASES: dict[str, str] = {
    "ollama": "ollama",
    "remote_api": "openai-completions",
    "openai": "openai-completions",
    "openai_compatible": "openai-completions",
    "openai-completions": "openai-completions",
    "openai_responses": "openai-responses",
    "openai-responses": "openai-responses",
    "ecnu": "openai-completions",
    "glm": "openai-completions",
    "bigmodel": "openai-completions",
    "anthropic": "anthropic-messages",
    "anthropic-messages": "anthropic-messages",
    "google": "google-generative-ai",
    "google-generative-ai": "google-generative-ai",
    "gemini": "google-generative-ai",
    "vivo": "vivo",
    "vivo_aigc": "vivo",
}


def normalize_api_type(value: str | None) -> str | None:
    """Resolve a user supplied provider/api string to a known API type."""

    if not value:
        return None
    key = value.strip().lower()
    return LEGACY_PROVIDER_ALIASES.get(key, key)


__all__ = [
    "ApiType",
    "KNOWN_API_TYPES",
    "LEGACY_PROVIDER_ALIASES",
    "BUILTIN_PROVIDERS",
    "ModelCost",
    "ThinkingLevelMap",
    "ModelDefinition",
    "ProviderConfig",
    "ModelsConfig",
    "ResolvedModel",
    "normalize_api_type",
]
