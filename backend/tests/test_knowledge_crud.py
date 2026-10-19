import json

import pytest

from backend.app.db.database import Database, now
from backend.app.domains.knowledge.schemas import (
    CharacterCreate,
    CharacterUpdate,
    EvidenceCreate,
    FactCreate,
    FactUpdate,
)
from backend.app.domains.knowledge.service import KnowledgeService


def database_with_book(tmp_path):
    db = Database(tmp_path / "knowledge.sqlite3")
    db.initialize()
    stamp = now()
    db.execute(
        "INSERT INTO users VALUES(?,?,?,?,?,?,?)",
        ("user_1", "tester", "hash", "", "", "", stamp),
    )
    db.execute(
        "INSERT INTO books VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("book_1", "user_1", "测试", "", "zh-CN", "txt", "a.txt", "a.txt",
         "ready", 0, None, stamp, stamp, 0),
    )
    book_db = db.book_database("book_1")
    book_db.execute(
        "INSERT INTO chapters VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        ("chapter_1", "book_1", 1, "第一章", "林默受伤。", 5, 0, 5, "title", 1, None),
    )
    return db


def test_character_fact_crud_keeps_history_and_supports_restore(tmp_path):
    db = database_with_book(tmp_path)
    service = KnowledgeService(db)
    character = service.create_character("user_1", "book_1", CharacterCreate(name="林默"))
    first = service.create_fact(
        "user_1",
        "book_1",
        FactCreate(
            character_id=character["id"],
            fact_type="status",
            value="受伤",
            evidence=EvidenceCreate(chapter_id="chapter_1", quote="林默受伤"),
        ),
    )

    second = service.update_fact(
        "user_1",
        "book_1",
        first["id"],
        FactUpdate(value="痊愈", reason="后文修订"),
    )
    assert second["supersedes_id"] == first["id"]
    assert [row["value_json"] for row in service.facts("user_1", "book_1", character["id"])] == [
        json.dumps("受伤", ensure_ascii=False),
        json.dumps("痊愈", ensure_ascii=False),
    ]

    service.delete_character("user_1", "book_1", character["id"], "误识别")
    assert service.characters("user_1", "book_1") == []
    restored = service.restore_character("user_1", "book_1", character["id"])
    assert restored["state"] == "active"
    assert db.one("SELECT COUNT(*) AS count FROM knowledge_changes")["count"] >= 2


def test_invalid_evidence_is_rejected_and_books_are_isolated(tmp_path):
    db = database_with_book(tmp_path)
    service = KnowledgeService(db)
    character = service.create_character("user_1", "book_1", CharacterCreate(name="林默"))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        service.create_fact(
            "user_1",
            "book_1",
            FactCreate(
                character_id=character["id"],
                fact_type="identity",
                value="未知",
                evidence=EvidenceCreate(chapter_id="missing", quote="不存在"),
            ),
        )
    assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error:
        service.characters("other", "book_1")
    assert error.value.status_code == 404
