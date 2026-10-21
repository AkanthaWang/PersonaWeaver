"""Pi-style append-only JSONL session storage.

PersonaWeaver keeps SQLite as the primary queryable store, but mirrors every
conversation into a Pi-compatible JSONL session file so a session can be read,
diffed and forked like a plain text artefact. Branches, compactions and branch
summaries are recorded by appending new lines; existing history is never
rewritten.

File layout (see Pi ``docs/session-format.md``)::

    db/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl

The first line is a ``session`` header, every following line is one tree entry::

    {"type":"session","version":3,"id":"...","timestamp":"...","cwd":"..."}
    {"type":"message","id":"...","parentId":null,"timestamp":"...","message":{...}}
    {"type":"compaction","id":"...","parentId":"...","summary":"...","tokensBefore":123}
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import re
import tempfile


SESSION_VERSION = 3
_ENCODED_CWD = "personaweaver"

# Pi sanitises the working directory into the folder name. PersonaWeaver is a
# single logical workspace, so it uses one stable segment by default.
_SAFE = re.compile(r"[^0-9A-Za-z._-]+")


def encode_directory(value: str) -> str:
    """Turn an arbitrary path/name into a filesystem-safe session folder."""

    cleaned = _SAFE.sub("-", value.strip().strip("/\\")).strip("-.")
    return cleaned or _ENCODED_CWD


def session_root(base_dir: Path, cwd: str | None = None) -> Path:
    """Resolve the session directory, honouring environment overrides."""

    override = (
        os.getenv("PERSONAWEAVER_SESSION_DIR")
        or os.getenv("PI_CODING_AGENT_SESSION_DIR")
        or ""
    ).strip()
    root = Path(override).expanduser() if override else Path(base_dir) / "agent" / "sessions"
    return root / encode_directory(cwd or _ENCODED_CWD)


class SessionStore:
    """Append-only JSONL writer for one conversation."""

    def __init__(self, base_dir: Path, cwd: str | None = None):
        self.base_dir = Path(base_dir)
        # ``cwd`` is kept for metadata; the folder segment defaults to a stable
        # workspace name so temp/absolute paths do not explode on Windows.
        self.cwd = cwd or _ENCODED_CWD
        self.directory = session_root(self.base_dir, self.cwd)

    def path_for(self, session_id: str, stamp: str) -> Path:
        safe_stamp = stamp.replace(":", "").replace("-", "").replace(".", "").replace("+", "")[:15] or "session"
        return self.directory / f"{safe_stamp}_{session_id}.jsonl"

    def ensure_header(self, path: Path, session_id: str, stamp: str, parent_session: str | None = None):
        """Create the header line once; keep it when the file already exists."""

        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            return
        header = {
            "type": "session",
            "version": SESSION_VERSION,
            "id": session_id,
            "timestamp": stamp,
            "cwd": self.cwd,
        }
        if parent_session:
            header["parentSession"] = parent_session
        self._append_line(path, header)

    def append(self, path: Path, entry: dict):
        """Append a single tree entry, preserving field order for readability."""

        self._append_line(path, entry)

    def append_many(self, path: Path, entries: list[dict]):
        for entry in entries:
            self._append_line(path, entry)

    def read(self, path: Path) -> list[dict]:
        path = Path(path)
        if not path.exists():
            return []
        entries = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
        return entries

    def rebuild(self, path: Path, session_id: str, stamp: str, entries: list[dict]):
        """Atomically replace a derived mirror; a partial append is never canonical."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".session-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                header = {"type": "session", "version": SESSION_VERSION,
                          "id": session_id, "timestamp": stamp, "cwd": self.cwd}
                for entry in [header, *entries]:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def fork(self, source: Path, session_id: str, stamp: str, target_cwd: str | None = None) -> Path:
        """Copy an existing session file into a new session (Pi ``/clone``)."""

        target = self.path_for(session_id, stamp)
        target.parent.mkdir(parents=True, exist_ok=True)
        original = self.read(source)
        with target.open("w", encoding="utf-8") as handle:
            for index, entry in enumerate(original):
                if index == 0 and entry.get("type") == "session":
                    entry = {
                        "type": "session",
                        "version": SESSION_VERSION,
                        "id": session_id,
                        "timestamp": stamp,
                        "cwd": target_cwd or self.cwd,
                        "parentSession": str(source),
                    }
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return target

    @staticmethod
    def _append_line(path: Path, entry: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


__all__ = ["SESSION_VERSION", "SessionStore", "encode_directory", "session_root"]
