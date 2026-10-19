"""Persistence for ``db/agent/models.json`` and ``db/agent/settings.json``.

Pi stores the same files under ``~/.pi/agent`` (see ``settings-manager.ts`` and
``model-config.ts``). This module reproduces the behaviour with plain JSON files:

* ``models.json``  -- provider/model definitions (hand editable, hot reloaded).
* ``settings.json`` -- the user's default ``provider`` / ``model`` / thinking level.

Writes are atomic (temp file + replace) so a crashed process cannot leave a
half-written configuration behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


AGENT_DIR_NAME = "agent"
MODELS_FILE_NAME = "models.json"
SETTINGS_FILE_NAME = "settings.json"


def agent_dir(root: Path | str | None = None) -> Path:
    """Resolve the ``db/agent`` directory.

    ``PERSONAWEAVER_AGENT_DIR`` overrides the location (used by tests and for
    installations that keep data outside the repository).
    """

    override = os.getenv("PERSONAWEAVER_AGENT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if root is not None:
        return Path(root).resolve() / AGENT_DIR_NAME
    # Default: <repo>/db/agent -- providers/ -> ai/ -> app/ -> backend/ -> repo/
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "db" / AGENT_DIR_NAME


def _read_json(path: Path) -> tuple[Any, str | None]:
    """Return ``(parsed, error)``; a missing file is not an error."""

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"Failed to read {path}: {exc}"
    if not raw.strip():
        return None, None
    try:
        return json.loads(_strip_json_comments(raw)), None
    except json.JSONDecodeError as exc:
        return None, f"Failed to parse {path}: {exc}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _strip_json_comments(text: str) -> str:
    """Minimal JSONC support: ``//`` line comments outside strings."""

    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "/":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


class AgentSettingsStore:
    """Filesystem-backed settings store rooted at ``db/agent``."""

    def __init__(self, root: Path | str | None = None):
        self.dir = agent_dir(root)

    @property
    def models_path(self) -> Path:
        return self.dir / MODELS_FILE_NAME

    @property
    def settings_path(self) -> Path:
        return self.dir / SETTINGS_FILE_NAME

    # -- models.json ------------------------------------------------------- #
    def read_models_document(self) -> tuple[dict[str, Any], str | None]:
        payload, error = _read_json(self.models_path)
        if error:
            return {}, error
        if payload is None:
            return {}, None
        if not isinstance(payload, dict):
            return {}, f"Invalid models.json: expected an object, got {type(payload).__name__}"
        return payload, None

    def write_models_document(self, document: dict[str, Any]) -> Path:
        _write_json(self.models_path, document)
        return self.models_path

    def models_mtime(self) -> float | None:
        try:
            return self.models_path.stat().st_mtime
        except OSError:
            return None

    # -- settings.json ----------------------------------------------------- #
    def read_settings(self) -> dict[str, Any]:
        payload, error = _read_json(self.settings_path)
        if error or not isinstance(payload, dict):
            return {}
        return payload

    def get_user_model(self, user_id: str) -> dict[str, Any] | None:
        """Return the persisted active model settings for one local user."""

        users = self.read_settings().get("users")
        if not isinstance(users, dict):
            return None
        settings = users.get(user_id)
        if not isinstance(settings, dict) or not settings.get("model"):
            return None
        return dict(settings)

    def set_user_model(self, user_id: str, settings: dict[str, Any]) -> Path:
        """Persist one user's active model settings in ``settings.json``."""

        document = self.read_settings()
        users = document.get("users")
        if not isinstance(users, dict):
            users = {}
        users[user_id] = dict(settings)
        document["users"] = users
        return self.write_settings(document)

    def write_settings(self, settings: dict[str, Any]) -> Path:
        _write_json(self.settings_path, settings)
        return self.settings_path

    def get_default_provider(self) -> str | None:
        value = self.read_settings().get("defaultProvider")
        return value if isinstance(value, str) and value.strip() else None

    def set_default_provider(self, provider: str | None) -> None:
        settings = self.read_settings()
        if provider:
            settings["defaultProvider"] = provider
        else:
            settings.pop("defaultProvider", None)
        self.write_settings(settings)

    def get_default_model(self) -> str | None:
        value = self.read_settings().get("defaultModel")
        return value if isinstance(value, str) and value.strip() else None

    def set_default_model(self, model: str | None) -> None:
        settings = self.read_settings()
        if model:
            settings["defaultModel"] = model
        else:
            settings.pop("defaultModel", None)
        self.write_settings(settings)

    def get_thinking_level(self) -> str | None:
        value = self.read_settings().get("thinkingLevel")
        return value if isinstance(value, str) and value.strip() else None

    def set_thinking_level(self, level: str | None) -> None:
        settings = self.read_settings()
        if level:
            settings["thinkingLevel"] = level
        else:
            settings.pop("thinkingLevel", None)
        self.write_settings(settings)

    def set_defaults(self, *, provider: str | None = None, model: str | None = None) -> None:
        """Persist provider and model together (single atomic write)."""

        settings = self.read_settings()
        if provider:
            settings["defaultProvider"] = provider
        if model:
            settings["defaultModel"] = model
        self.write_settings(settings)


__all__ = ["AgentSettingsStore", "agent_dir"]
