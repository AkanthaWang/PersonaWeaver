"""ModelRegistry -- Pi-style config driven provider/model management.

Responsibilities (mirrors ``pi-coding-agent/src/core/model-config.ts`` +
``model-registry.ts``):

* load ``db/agent/models.json`` and validate it against the schema;
* merge built-in provider defaults, custom providers and runtime profiles;
* resolve API keys (``$ENV`` / literal) and headers;
* lazily create one transport per request so a missing optional dependency in
  one provider never breaks the others;
* hot reload when ``models.json`` changes on disk.

Errors never crash the process: a broken config is surfaced through
``registry.load_error`` and the registry keeps serving whatever it could load.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import api_types
from .schemas import (
    BUILTIN_PROVIDERS,
    KNOWN_API_TYPES,
    ModelCost,
    ModelDefinition,
    ModelsConfig,
    ProviderConfig,
    ResolvedModel,
    normalize_api_type,
)
from .settings_store import AgentSettingsStore


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def resolve_api_key_config(key_config: str | None) -> str | None:
    """Resolve an API key config value the way Pi does.

    * ``None`` / ``""``            -> ``None``
    * ``$MY_KEY`` / ``${MY_KEY}``  -> the environment variable (missing -> unresolved)
    * plain uppercase name         -> environment variable if set, else literal
    * anything else                -> literal
    """

    if key_config is None:
        return None
    value = str(key_config).strip()
    if not value:
        return None
    if value.startswith("$$"):
        return value[1:]
    interpolated, unresolved = _interpolate_env(value)
    if unresolved:
        return None
    if interpolated is not None:
        return interpolated or None
    env_value = os.environ.get(value)
    if env_value:
        return env_value
    return value


def _interpolate_env(value: str) -> tuple[str | None, bool]:
    """Expand ``$VAR`` / ``${VAR}``. Returns ``(None, False)`` when absent."""

    if "$" not in value:
        return None, False
    unresolved = False

    def replace(match: re.Match[str]) -> str:
        nonlocal unresolved
        name = match.group(1) or match.group(2)
        resolved = os.environ.get(name)
        if resolved is None:
            unresolved = True
            return ""
        return resolved

    result = _ENV_PATTERN.sub(replace, value)
    return result, unresolved


def _resolve_value_config(value: str | None) -> str | None:
    """Resolve headers as well; only ``$ENV`` forms are expanded, literals kept."""

    if value is None:
        return None
    text = str(value)
    if text.startswith("$$"):
        return text[1:]
    interpolated, unresolved = _interpolate_env(text)
    if unresolved and interpolated is not None and "$" in text:
        return None
    return interpolated if interpolated is not None else text


def _merged_compat(provider_compat: dict[str, Any], model_compat: dict[str, Any]) -> dict[str, Any]:
    merged = dict(provider_compat or {})
    merged.update(model_compat or {})
    return merged


class ModelRegistry:
    """Loads, validates and merges provider/model configuration."""

    def __init__(self, store: AgentSettingsStore | None = None, models_json_path: Path | str | None = None):
        self.store = store or AgentSettingsStore()
        if models_json_path is not None:
            self.store.dir = Path(models_json_path).resolve().parent
        self._config = ModelsConfig()
        self._models: list[ResolvedModel] = []
        self._runtime_overrides: dict[str, ProviderConfig] = {}
        self.load_error: str | None = None
        self._loaded_mtime: float | None = None
        self.reload()

    # ------------------------------------------------------------------ #
    # loading
    # ------------------------------------------------------------------ #
    def reload(self, force: bool = False) -> None:
        """Load ``models.json`` when it changed (or when forced)."""

        mtime = self.store.models_mtime()
        if not force and mtime is not None and mtime == self._loaded_mtime and self._models:
            return
        self._loaded_mtime = mtime
        self._config, self.load_error = self.load_custom_models()
        self._models = self.parse_models(self._config)

    def load_custom_models(self) -> tuple[ModelsConfig, str | None]:
        """Read + validate ``db/agent/models.json``.

        A missing file yields an empty config. Malformed JSON or a schema
        violation is reported through the returned error string instead of
        raising, so a bad edit cannot take down the application.
        """

        document, error = self.store.read_models_document()
        if error:
            return ModelsConfig(), error
        if not document:
            return ModelsConfig(), None
        try:
            config = ModelsConfig.model_validate(document)
        except ValidationError as exc:
            details = "\n".join(
                f"  - {'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            )
            return ModelsConfig(), f"Invalid models.json schema:\n{details}\n\nFile: {self.store.models_path}"
        validation_error = self.validate_config(config)
        if validation_error:
            return ModelsConfig(), validation_error
        return config, None

    @staticmethod
    def validate_config(config: ModelsConfig) -> str | None:
        """Custom providers need a base URL and an API type.

        Built-in providers may omit both and inherit their defaults.
        """

        problems: list[str] = []
        for provider_id, provider in config.providers.items():
            builtin = BUILTIN_PROVIDERS.get(provider_id, {})
            api = normalize_api_type(provider.api) or normalize_api_type(builtin.get("api"))
            if not api:
                problems.append(f"providers.{provider_id}.api: required for custom providers")
            elif api not in KNOWN_API_TYPES:
                problems.append(
                    f"providers.{provider_id}.api: unknown API '{api}' (expected one of {', '.join(KNOWN_API_TYPES)})"
                )
            if not (provider.base_url or builtin.get("baseUrl")):
                problems.append(f"providers.{provider_id}.baseUrl: required for custom providers")
            for index, model in enumerate(provider.models):
                model_api = normalize_api_type(model.api) or api
                if model_api and model_api not in KNOWN_API_TYPES:
                    problems.append(
                        f"providers.{provider_id}.models[{index}].api: unknown API '{model_api}'"
                    )
                if not model.id.strip():
                    problems.append(f"providers.{provider_id}.models[{index}].id: must not be empty")
        if not problems:
            return None
        details = "\n".join(f"  - {problem}" for problem in problems)
        return f"Invalid models.json configuration:\n{details}\n\nFile: {config_path_hint()}"

    def parse_models(self, config: ModelsConfig) -> list[ResolvedModel]:
        """Flatten provider/model pairs using Pi's inheritance chain:

        ``model.api ?? provider.api ?? builtin.api``.
        """

        resolved: list[ResolvedModel] = []
        for provider_id, provider in config.providers.items():
            builtin = dict(BUILTIN_PROVIDERS.get(provider_id, {}))
            provider_api = (
                normalize_api_type(provider.api)
                or normalize_api_type(builtin.get("api"))
                or "openai-completions"
            )
            provider_base = provider.base_url or builtin.get("baseUrl") or ""
            provider_headers = self._resolve_headers(provider.headers)
            provider_key = resolve_api_key_config(provider.api_key)
            auth_header = provider.auth_header if provider.auth_header is not None else bool(provider.api_key)
            for definition in provider.models:
                resolved.append(
                    self._resolve_model(
                        provider_id=provider_id,
                        provider_name=provider.name or builtin.get("name") or provider_id,
                        definition=definition,
                        provider_api=provider_api,
                        provider_base=provider_base,
                        provider_key=provider_key,
                        provider_headers=provider_headers,
                        provider_compat=provider.compat,
                        auth_header=auth_header,
                    )
                )
        return resolved

    def _resolve_model(
        self,
        *,
        provider_id: str,
        provider_name: str,
        definition: ModelDefinition,
        provider_api: str,
        provider_base: str,
        provider_key: str | None,
        provider_headers: dict[str, str],
        provider_compat: dict[str, Any],
        auth_header: bool,
    ) -> ResolvedModel:
        api = normalize_api_type(definition.api) or provider_api
        headers = dict(provider_headers)
        headers.update(self._resolve_headers(definition.headers))
        return ResolvedModel(
            provider=provider_id,
            provider_name=provider_name,
            id=definition.id,
            name=definition.name or definition.id,
            api=api,
            base_url=definition.base_url or provider_base,
            api_key=provider_key,
            auth_header=auth_header,
            headers=headers,
            reasoning=definition.reasoning,
            input=list(definition.input),
            cost=definition.cost or ModelCost(),
            context_window=definition.context_window,
            max_tokens=definition.max_tokens,
            sampling_params=dict(definition.sampling_params or {}),
            compat=_merged_compat(provider_compat, definition.compat),
        )

    @staticmethod
    def _resolve_headers(headers: dict[str, str] | None) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for key, value in (headers or {}).items():
            resolved_value = _resolve_value_config(value)
            if resolved_value is None:
                continue
            resolved[str(key)] = resolved_value
        return resolved

    # ------------------------------------------------------------------ #
    # runtime registration / overrides
    # ------------------------------------------------------------------ #
    def register_provider(self, provider_id: str, config: ProviderConfig | dict[str, Any]) -> ResolvedModel:
        """Upsert a provider and its models (extension style registration).

        Merge semantics match Pi's ``upsertRegisteredProvider``: supplying only
        ``baseUrl`` keeps previously registered model definitions.
        """

        parsed = config if isinstance(config, ProviderConfig) else ProviderConfig.model_validate(config)
        existing = self._runtime_overrides.get(provider_id)
        if existing is not None:
            merged = ProviderConfig.model_validate(
                {
                    **existing.model_dump(by_alias=True),
                    **parsed.model_dump(by_alias=True, exclude_unset=True),
                    "models": parsed.models or existing.models,
                }
            )
        else:
            merged = parsed
        self._runtime_overrides[provider_id] = merged
        self._config = ModelsConfig(
            providers={**self._config.providers, provider_id: merged}
        )
        self._models = self.parse_models(self._config)
        return next(model for model in self._models if model.provider == provider_id)

    def unregister_provider(self, provider_id: str) -> None:
        self._runtime_overrides.pop(provider_id, None)
        providers = dict(self._config.providers)
        providers.pop(provider_id, None)
        self._config = ModelsConfig(providers=providers)
        self._models = self.parse_models(self._config)

    def register_runtime_profile(self, profile: dict[str, Any]) -> None:
        """Expose a SQLite ``model_profiles`` row as a runtime provider/model.

        The profile's ``provider_name`` groups models in the UI, so it becomes
        the provider id when present.
        """

        provider_id = (profile.get("provider_name") or profile.get("provider") or "default").strip() or "default"
        api = normalize_api_type(profile.get("provider")) or "openai-completions"
        if (profile.get("api_protocol") or "").strip():
            api = normalize_api_type(profile["api_protocol"]) or api
        definition = ModelDefinition.model_validate(
            {
                "id": profile.get("model") or profile.get("name") or "default",
                "name": profile.get("name") or profile.get("model"),
                "reasoning": bool(profile.get("reasoning", False)),
                "contextWindow": int(profile.get("context_window") or 128_000),
                "maxTokens": int(profile.get("max_tokens") or 16_384),
                "samplingParams": {
                    key: profile[key]
                    for key in ("temperature", "top_p")
                    if profile.get(key) is not None
                },
            }
        )
        self.register_provider(
            provider_id,
            ProviderConfig.model_validate(
                {
                    "name": profile.get("provider_name") or provider_id,
                    "baseUrl": profile.get("base_url"),
                    "apiKey": profile.get("api_key") or None,
                    "api": api,
                    "headers": profile.get("headers") or {},
                    "models": [definition.model_dump(by_alias=True)],
                }
            ),
        )

    # ------------------------------------------------------------------ #
    # lookups
    # ------------------------------------------------------------------ #
    def get_by_api(self, api: str) -> list[ResolvedModel]:
        target = normalize_api_type(api)
        return [model for model in self._models if model.api == target]

    def find(self, model_id: str, provider: str | None = None) -> ResolvedModel | None:
        for model in self._models:
            if model.id != model_id:
                continue
            if provider is None or model.provider == provider or model.provider_name == provider:
                return model
        return None

    def get(self, model_id: str) -> ResolvedModel | None:
        return self.find(model_id)

    def get_provider(self, provider_id: str) -> ResolvedModel | None:
        return next(
            (
                model
                for model in self._models
                if model.provider == provider_id or model.provider_name == provider_id
            ),
            None,
        )

    def models(self) -> list[ResolvedModel]:
        self.reload()
        return list(self._models)

    def providers(self) -> list[str]:
        return sorted({model.provider for model in self._models})

    def save_models_document(self, document: dict[str, Any]) -> Path:
        """Validate then persist ``models.json``; raises ``ValueError`` on error."""

        config = ModelsConfig.model_validate(document)
        error = self.validate_config(config)
        if error:
            raise ValueError(error)
        path = self.store.write_models_document(config.model_dump(by_alias=True, exclude_none=True))
        self.reload(force=True)
        return path

    # ------------------------------------------------------------------ #
    # invocation
    # ------------------------------------------------------------------ #
    def invoke(self, settings: dict[str, Any], messages: list[dict[str, str]]) -> str:
        """Resolve settings into a model and call the right transport.

        ``settings`` accepts either registry-native keys (``api``) or the
        project's legacy keys (``provider`` + ``api_protocol``).
        """

        model = self.resolve_settings(settings)
        transport = api_types.get_transport(model.api)
        params = dict(model.sampling_params)
        for key in ("temperature", "top_p"):
            if settings.get(key) is not None:
                params[key] = settings[key]
        temperature = float(params.pop("temperature", settings.get("temperature", 0.7)))
        top_p = params.pop("top_p", None)
        if top_p is not None:
            params.setdefault("top_p", top_p)
        return transport(
            messages=messages,
            model=model.id,
            base_url=model.base_url,
            api_key=model.api_key,
            temperature=temperature,
            max_tokens=int(settings.get("max_tokens") or model.max_tokens or 2048),
            timeout_seconds=int(settings.get("timeout_seconds") or 60),
            headers=model.headers,
            json_mode=bool(settings.get("json_mode")),
            sampling_params=params,
            request_id=settings.get("request_id"),
        )

    def resolve_settings(self, settings: dict[str, Any]) -> ResolvedModel:
        """Build a ``ResolvedModel`` from flat settings without persistence.

        Used by the settings screen, which edits a transient form before saving.
        """

        api = normalize_api_type(settings.get("api") or settings.get("api_protocol"))
        if not api:
            api = normalize_api_type(settings.get("provider")) or "openai-completions"
        provider_id = str(settings.get("provider_name") or settings.get("provider") or "default")
        base_url = str(settings.get("base_url") or "")
        if not base_url:
            builtin = BUILTIN_PROVIDERS.get(str(settings.get("provider") or "").lower(), {})
            base_url = builtin.get("baseUrl", "")
        return ResolvedModel(
            provider=provider_id,
            provider_name=provider_id,
            id=str(settings.get("model") or "default"),
            name=str(settings.get("name") or settings.get("model") or "default"),
            api=api,
            base_url=base_url,
            api_key=resolve_api_key_config(settings.get("api_key")) if settings.get("api_key") else None,
            auth_header=bool(settings.get("auth_header", bool(settings.get("api_key")))),
            headers=self._resolve_headers(settings.get("headers")),
            reasoning=bool(settings.get("reasoning", False)),
            context_window=int(settings.get("context_window") or 128_000),
            max_tokens=int(settings.get("max_tokens") or 16_384),
            sampling_params={
                key: settings[key]
                for key in ("temperature", "top_p")
                if settings.get(key) is not None
            },
        )


def config_path_hint() -> str:
    return str(AgentSettingsStore().models_path)


_default_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """Process-wide registry singleton (hot reloads on access)."""

    global _default_registry
    if _default_registry is None:
        _default_registry = ModelRegistry()
    _default_registry.reload()
    return _default_registry


def reset_registry() -> None:
    """Drop the singleton (tests / explicit config reloads)."""

    global _default_registry
    _default_registry = None


__all__ = [
    "ModelRegistry",
    "get_registry",
    "reset_registry",
    "resolve_api_key_config",
    "config_path_hint",
]
