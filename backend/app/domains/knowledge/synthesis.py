"""On-demand character synthesis used by the 人物档案 panel and role-play."""

from __future__ import annotations

import json

from fastapi import HTTPException

from backend.app.ai.extraction_pipeline import Synthesis, digest, request_json
from backend.app.ai.prompts.extraction import KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT
from backend.app.db.database import now
from backend.app.domains.settings import llm

BATCH_BYTES = 12000


def character_facts(book_db, book_id: str, character_id: str) -> list[dict]:
    """Return the active facts of one character, oldest chapter first."""

    rows = book_db.all(
        "SELECT f.id,f.fact_type,f.value_json,c.chapter_no "
        "FROM knowledge_facts f "
        "LEFT JOIN knowledge_evidence e ON e.id=f.evidence_id "
        "LEFT JOIN chapters c ON c.id=e.chapter_id "
        "WHERE f.book_id=? AND f.entity_type='character' AND f.entity_id=? "
        "AND f.state='active' AND f.deleted_at IS NULL "
        "ORDER BY COALESCE(c.chapter_no, 1 << 30), f.version, f.created_at",
        (book_id, character_id),
    )
    facts = []
    for row in rows:
        try:
            value = json.loads(row["value_json"])
        except (TypeError, ValueError):
            value = row["value_json"]
        if isinstance(value, str) and not value.strip():
            continue
        facts.append({
            "fact_id": row["id"],
            "fact_type": row["fact_type"],
            "chapter_no": row["chapter_no"],
            "value": value,
        })
    return facts


def _batches(facts: list[dict], limit: int = BATCH_BYTES) -> list[list[dict]]:
    batches, batch = [], []
    for fact in facts:
        candidate = batch + [fact]
        if batch and len(json.dumps(candidate, ensure_ascii=False)) > limit:
            batches.append(batch)
            batch = [fact]
        else:
            batch = candidate
    if batch:
        batches.append(batch)
    return batches


def _validate(allowed: set[str]):
    def validate(value):
        parsed = Synthesis.model_validate(value).model_dump()
        if not parsed["paragraphs"]:
            raise ValueError("综合档案不能为空")
        if any(not set(paragraph["fact_ids"]) <= allowed for paragraph in parsed["paragraphs"]):
            raise ValueError("综合档案必须引用已有事实ID")
        return parsed

    return validate


def _synthesize(settings, facts: list[dict]) -> list[dict]:
    batches = _batches(facts)
    paragraphs = []
    for batch in batches:
        allowed = {fact["fact_id"] for fact in batch}
        parsed = request_json(
            settings,
            [
                {"role": "system", "content": KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
            ],
            _validate(allowed),
        )
        paragraphs.extend(parsed["paragraphs"])
    if len(batches) > 1:
        compact = [{"fact_id": paragraph["fact_ids"][0], "fact_ids": paragraph["fact_ids"],
                    "summary": paragraph["text"]} for paragraph in paragraphs]
        parsed = request_json(
            settings,
            [
                {"role": "system", "content": KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
            ],
            _validate({fact["fact_id"] for fact in facts}),
        )
        paragraphs = parsed["paragraphs"]
    return paragraphs


def synthesize_character(db, user_id: str, book_id: str, character_id: str, profile_id: str | None = None):
    """Regenerate one character's summary and persist it with its source facts."""

    book_db = db.book_database(book_id)
    character = book_db.one(
        "SELECT * FROM knowledge_characters WHERE id=? AND book_id=? AND deleted_at IS NULL",
        (character_id, book_id),
    )
    if not character:
        raise HTTPException(404, "人物不存在")
    facts = character_facts(book_db, book_id, character_id)
    if not facts:
        raise HTTPException(422, "该人物暂无可用事实，无法生成角色总结")

    settings = llm.load_settings_for_profile(db, user_id, profile_id)
    try:
        paragraphs = _synthesize(settings, facts)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, llm.error_message(exc)) from exc

    stamp = now()
    entity = book_db.one(
        "SELECT id,content FROM knowledge_entities WHERE book_id=? AND kind='characters' AND name=?",
        (book_id, character["canonical_name"]),
    )
    if entity:
        content = json.loads(entity["content"])
        content.update(
            synthesis=paragraphs,
            synthesis_status="ready",
            synthesis_model=settings.get("model"),
            synthesis_version=digest(KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT),
        )
        book_db.execute(
            "UPDATE knowledge_entities SET content=? WHERE id=?",
            (json.dumps(content, ensure_ascii=False), entity["id"]),
        )
    book_db.execute(
        "UPDATE knowledge_characters SET updated_at=? WHERE id=?", (stamp, character_id),
    )
    return {
        "character_id": character_id,
        "synthesis": paragraphs,
        "synthesis_status": "ready",
        "synthesis_model": settings.get("model"),
    }


__all__ = ["character_facts", "synthesize_character"]
