from __future__ import annotations
import json
import sqlite3

from fastapi import HTTPException

from backend.app.db.database import identifier, now

from .repository import CharacterRepository


INTRO_LIMIT = 220
CONTENT_LIMIT = 1000


def clip(text, limit=INTRO_LIMIT):
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def card_intro(entry, limit=INTRO_LIMIT):
    """Pick the shortest complete introduction that can stand alone on a card."""

    for paragraph in entry.get("synthesis") or []:
        text = paragraph.get("text") if isinstance(paragraph, dict) else paragraph
        if str(text or "").strip():
            return clip(text, limit)
    parts = []
    for key in ("summary", "identity"):
        value = entry.get(key)
        if isinstance(value, (list, tuple)):
            value = "；".join(str(item) for item in value if str(item or "").strip())
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    if not parts:
        for key in ("personality", "appearance"):
            value = entry.get(key)
            if isinstance(value, (list, tuple)):
                value = "；".join(str(item) for item in value if str(item or "").strip())
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    return clip(" ".join(parts), limit)


def card_markdown(entry):
    """Keep the persistent persona small; chapter facts belong in retrieval."""
    sections = [f"# {entry['name']}"]
    intro = card_intro(entry)
    if intro:
        sections.append("## 简介\n\n" + intro)
    for label, key in (("身份", "identity"), ("性格", "personality"), ("说话方式", "speech")):
        value = entry.get(key)
        if isinstance(value, list):
            value = "；".join(str(item) for item in value[:3] if isinstance(item, str))
        if isinstance(value, str) and value.strip():
            sections.append(f"## {label}\n\n{clip(value, 160)}")
    return "\n\n".join(sections)


def card_content(entry, limit=CONTENT_LIMIT):
    """Generate a short persona, never a copy of the knowledge archive."""
    content = card_markdown(entry)
    if len(content) > limit:
        content = content[: limit - 1].rstrip() + "…"
    return content


class CharacterService:
    def __init__(self, db):
        self.repo = CharacterRepository(db)

    def list(self, user_id: str, book_id: str | None = None):
        return {"cards": self.repo.list_for_user(user_id, book_id)}

    def owned(self, user_id: str, card_id: str):
        card = self.repo.owned(user_id, card_id)
        if not card:
            raise HTTPException(404, "角色卡不存在")
        return card

    def book_owned(self, user_id: str, book_id: str):
        if not self.repo.one("SELECT book_id FROM books WHERE book_id=? AND user_id=?", (book_id, user_id)):
            raise HTTPException(404, "书籍不存在")

    @staticmethod
    def knowledge_entry(book_db, book_id: str, name: str):
        target = str(name or "").casefold()
        for row in book_db.all(
            "SELECT name,content FROM knowledge_entities WHERE book_id=? AND kind='characters'",
            (book_id,),
        ):
            if row["name"].casefold() != target:
                continue
            try:
                return json.loads(row["content"])
            except (TypeError, ValueError):
                return None
        return None

    def from_character(self, user_id: str, payload):
        """Build a role card from one knowledge character, keeping it idempotent."""

        self.book_owned(user_id, payload.book_id)
        book_db = self.repo.database.book_database(payload.book_id)
        character = book_db.one(
            "SELECT * FROM knowledge_characters WHERE id=? AND book_id=? AND deleted_at IS NULL",
            (payload.character_id, payload.book_id),
        )
        if not character:
            raise HTTPException(404, "人物不存在")
        entry = self.knowledge_entry(book_db, payload.book_id, character["canonical_name"]) or {}
        name = str(entry.get("name") or character["canonical_name"]).strip()
        content, intro = card_content({**entry, "name": name}), card_intro(entry)
        existing = self.repo.one(
            "SELECT c.* FROM cards c WHERE c.book_id=? AND c.name=?", (payload.book_id, name),
        )
        stamp = now()
        if existing:
            if not payload.overwrite:
                return {"card": existing, "created": False, "updated": False}
            self.repo.update(existing["id"], name, intro or existing["intro"], content, stamp)
            return {
                "card": self.repo.one("SELECT * FROM cards WHERE id=?", (existing["id"],)),
                "created": False, "updated": True,
            }
        card_id = identifier("card")
        self.repo.create((card_id, payload.book_id, name, intro, content, stamp, stamp))
        return {
            "card": self.repo.one("SELECT * FROM cards WHERE id=?", (card_id,)),
            "created": True, "updated": False,
        }

    def create(self, user_id: str, payload):
        self.book_owned(user_id, payload.book_id)
        stamp, card_id = now(), identifier("card")
        content = payload.content
        entry = None
        if payload.source_entity_id:
            entity = self.repo.database.book_database(payload.book_id).one(
                "SELECT content FROM knowledge_entities WHERE id=? AND book_id=? AND kind='characters'",
                (payload.source_entity_id, payload.book_id),
            )
            if not entity:
                raise HTTPException(404, "来源人物不存在")
            entry = json.loads(entity["content"])
        if not content:
            summary = self.repo.database.book_database(payload.book_id).one(
                "SELECT content FROM summaries WHERE book_id=? AND type=?",
                (payload.book_id, "characters"),
            )
            matches = [item for item in json.loads(summary["content"]) if item["name"] == payload.name] if summary else []
            if entry is None and len(matches) > 1:
                raise HTTPException(422, "存在同名人物，请指定 source_entity_id")
            entry = entry or next(iter(matches), None)
            content = card_content(entry or {"name": payload.name, "summary": payload.intro})
        intro = payload.intro or card_intro(entry or {})
        try:
            self.repo.create((card_id, payload.book_id, payload.name, intro, content, stamp, stamp))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "该书籍已存在同名角色卡") from exc
        return self.owned(user_id, card_id)

    def update(self, user_id: str, card_id: str, payload):
        self.owned(user_id, card_id)
        try:
            self.repo.update(card_id, payload.name, payload.intro, payload.content, now())
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "该书籍已存在同名角色卡") from exc
        return self.owned(user_id, card_id)

    def delete(self, user_id: str, card_id: str):
        self.owned(user_id, card_id)
        self.repo.delete(card_id)
        return {"ok": True}

    def compact(self, user_id: str, card_id: str):
        card = self.owned(user_id, card_id)
        book_db = self.repo.database.book_database(card["book_id"])
        entry = self.knowledge_entry(book_db, card["book_id"], card["name"])
        if not entry and not card["intro"].strip():
            raise HTTPException(422, "缺少人物档案或简介，请先补充简介")
        entry = {**(entry or {"summary": card["intro"]}), "name": card["name"]}
        if not card_intro(entry):
            entry["summary"] = card["intro"]
        self.repo.update(card_id, card["name"], card_intro(entry), card_content(entry), now())
        return self.owned(user_id, card_id)

    def export(self, user_id: str, card_id: str):
        return self.owned(user_id, card_id)
