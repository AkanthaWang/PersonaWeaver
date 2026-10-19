from __future__ import annotations
import json
import sqlite3

from fastapi import HTTPException

from backend.app.db.database import identifier, now

from .repository import CharacterRepository


def card_markdown(entry):
    def text(value):
        if isinstance(value, list):
            return "\n".join(f"- {text(item)}" for item in value)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value or "")

    sections = [f"# {entry['name']}"]
    if entry.get("synthesis"):
        sections.append("## 综合档案（模型归纳）\n\n" + "\n\n".join(
            paragraph["text"] + "\n\n事实依据：" + "、".join(paragraph["fact_ids"])
            for paragraph in entry["synthesis"]
        ))
    for label, key in (("简介", "summary"), ("身份", "identity"), ("外貌", "appearance"),
                       ("性格", "personality"), ("台词", "speech"), ("关键经历", "key_events"),
                       ("关系", "relationships")):
        if entry.get(key):
            sections.append(f"## {label}\n\n{text(entry[key])}")
    if entry.get("evidence"):
        sections.append("## 章节依据\n\n" + "\n\n".join(
            f"### {item['chapter']}\n\n{text({k: v for k, v in item.items() if k not in {'chapter', 'name'}})}"
            for item in entry["evidence"]
        ))
    return "\n\n".join(sections)


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

    def create(self, user_id: str, payload):
        if not self.repo.one("SELECT book_id FROM books WHERE book_id=? AND user_id=?", (payload.book_id, user_id)):
            raise HTTPException(404, "书籍不存在")
        stamp, card_id = now(), identifier("card")
        content = payload.content
        entry = None
        if payload.source_entity_id:
            entity = self.repo.one(
                "SELECT content FROM knowledge_entities WHERE id=? AND book_id=? AND kind='characters'",
                (payload.source_entity_id, payload.book_id),
            )
            if not entity:
                raise HTTPException(404, "来源人物不存在")
            entry = json.loads(entity["content"])
        if not content:
            summary = self.repo.summary(payload.book_id, "characters")
            matches = [item for item in json.loads(summary["content"]) if item["name"] == payload.name] if summary else []
            if entry is None and len(matches) > 1:
                raise HTTPException(422, "存在同名人物，请指定 source_entity_id")
            entry = entry or next(iter(matches), None)
            content = card_markdown(entry or {"name": payload.name, "summary": payload.intro})
        try:
            self.repo.create((card_id, payload.book_id, payload.name, payload.intro, content, stamp, stamp))
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

    def export(self, user_id: str, card_id: str):
        return self.owned(user_id, card_id)
