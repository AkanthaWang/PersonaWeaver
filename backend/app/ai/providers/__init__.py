"""Model provider adapters.

The package mirrors Pi's provider architecture in three layers:

1. :mod:`schemas` -- Pydantic definitions for ``db/agent/models.json``.
2. :mod:`registry` -- :class:`ModelRegistry`, the config driven loader that
   merges built-in defaults, ``models.json`` and runtime profiles.
3. :mod:`api_types` -- one HTTP transport per API type
   (``openai-completions``, ``openai-responses``, ``anthropic-messages``,
   ``google-generative-ai``, ``ollama``, ``vivo``).

:mod:`settings_store` persists the default provider/model into
``db/agent/settings.json``.
"""

from .base import ChatProvider, ChatSettings
from .registry import ModelRegistry, get_registry, reset_registry, resolve_api_key_config
from .schemas import (
    BUILTIN_PROVIDERS,
    KNOWN_API_TYPES,
    ModelsConfig,
    ModelDefinition,
    ProviderConfig,
    ResolvedModel,
    normalize_api_type,
)
from .settings_store import AgentSettingsStore, agent_dir

__all__ = [
    "ChatProvider",
    "ChatSettings",
    "ModelRegistry",
    "get_registry",
    "reset_registry",
    "resolve_api_key_config",
    "AgentSettingsStore",
    "agent_dir",
    "ModelsConfig",
    "ModelDefinition",
    "ProviderConfig",
    "ResolvedModel",
    "BUILTIN_PROVIDERS",
    "KNOWN_API_TYPES",
    "normalize_api_type",
]
