import json

import pytest
from fastapi import HTTPException

from backend.app.db.database import Database, now
from backend.app.domains.characters.schemas import CardFromCharacter
from backend.app.domains.characters.service import CharacterService, card_intro
from backend.app.domains.conversation.schemas import ConversationCreate
from backend.app.domains.conversation.service import ConversationService


def book_with_character(tmp_path, synthesis=True):
    db = Database(tmp_path / "cards.sqlite3")
    db.initialize()
    stamp = now()
    db.execute(
        "INSERT INTO users(user_id,username,password_hash,email,avatar,prompt,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        ("user_1", "tester", "hash", "", "", "", stamp, stamp),
    )
    db.execute(
        "INSERT INTO books(book_id,user_id,title,author,language,source_type,file_name,source_path,"
        "status,progress,err_message,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("book_1", "user_1", "测试", "", "zh-CN", "txt", "a.txt", "a.txt",
         "ready", 0, None, stamp, stamp),
    )
    book_db = db.book_database("book_1")
    book_db.execute(
        "INSERT INTO knowledge_characters VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("character_1", "book_1", "林默", json.dumps(["阿默"], ensure_ascii=False), 12, "active",
         None, None, stamp, stamp),
    )
    entry = {
        "entity_id": "entity_1", "name": "林默", "kind": "characters",
        "summary": "青石镇的猎户少年，因伤入城。", "identity": "猎户",
        "personality": ["谨慎", "重情"], "behavior": ["避开人群"],
        "synthesis": ([{"text": "林默是青石镇的猎户少年，受伤后被迫进城求医。", "fact_ids": ["fact_1"]}]
                      if synthesis else []),
        "synthesis_status": "ready" if synthesis else "pending",
    }
    book_db.execute(
        "INSERT INTO knowledge_entities VALUES(?,?,?,?,?,?)",
        ("entity_1", "book_1", "characters", "林默", json.dumps(["fact_1"]),
         json.dumps(entry, ensure_ascii=False)),
    )
    return db, book_db


def test_card_intro_prefers_synthesis_then_falls_back_to_fields():
    assert card_intro({"synthesis": [{"text": "综合段落", "fact_ids": []}], "summary": "摘要"}) == "综合段落"
    assert card_intro({"summary": "摘要", "identity": "身份"}) == "摘要 身份"
    assert card_intro({"personality": ["谨慎"]}) == "谨慎"
    long_text = card_intro({"summary": "甲" * 400})
    assert len(long_text) == 220 and long_text.endswith("…")


def test_card_from_character_is_idempotent_and_can_be_overwritten(tmp_path):
    db, _ = book_with_character(tmp_path)
    service = CharacterService(db)
    first = service.from_character(
        "user_1", CardFromCharacter(book_id="book_1", character_id="character_1"),
    )
    assert first["created"] is True
    assert first["card"]["name"] == "林默"
    assert first["card"]["intro"] == "林默是青石镇的猎户少年，受伤后被迫进城求医。"
    assert "# 林默" in first["card"]["content"]
    assert "## 性格" in first["card"]["content"]

    again = service.from_character(
        "user_1", CardFromCharacter(book_id="book_1", character_id="character_1"),
    )
    assert again["created"] is False and again["updated"] is False
    assert again["card"]["id"] == first["card"]["id"]

    overwrite = service.from_character(
        "user_1", CardFromCharacter(book_id="book_1", character_id="character_1", overwrite=True),
    )
    assert overwrite["updated"] is True
    assert db.one("SELECT COUNT(*) AS count FROM cards")["count"] == 1


def test_card_from_character_without_synthesis_uses_summary(tmp_path):
    db, _ = book_with_character(tmp_path, synthesis=False)
    result = CharacterService(db).from_character(
        "user_1", CardFromCharacter(book_id="book_1", character_id="character_1"),
    )
    assert result["card"]["intro"] == "青石镇的猎户少年，因伤入城。 猎户"


def test_long_character_keeps_card_within_editable_limit(tmp_path):
    db, book_db = book_with_character(tmp_path)
    entry = json.loads(book_db.one("SELECT content FROM knowledge_entities")["content"])
    entry["synthesis"] = [{"text": "综合" * 20000, "fact_ids": ["fact_1"]}]
    entry["evidence"] = [{"chapter": "第 1 章", "summary": "依据" * 4000}]
    book_db.execute(
        "UPDATE knowledge_entities SET content=?", (json.dumps(entry, ensure_ascii=False),),
    )
    card = CharacterService(db).from_character(
        "user_1", CardFromCharacter(book_id="book_1", character_id="character_1"),
    )["card"]
    assert len(card["content"]) <= 1000
    assert "## 章节依据" not in card["content"]
    assert len(card["intro"]) <= 220


def test_card_keeps_persona_not_history_or_references(tmp_path):
    db, book_db = book_with_character(tmp_path)
    entry = json.loads(book_db.one("SELECT content FROM knowledge_entities")["content"])
    entry.update(
        speech=["惜字如金", "习惯反问"],
        key_events=["十年前的战役"],
        relationships=["与城主结盟"],
        field_history={"identity": [{"chapter_no": 2, "chapter": "第二章", "value": "隐秘身份"}]},
        evidence=[{"chapter": "第三章", "quote": "完整引文"}],
    )
    book_db.execute("UPDATE knowledge_entities SET content=?", (json.dumps(entry, ensure_ascii=False),))
    card = CharacterService(db).from_character(
        "user_1", CardFromCharacter(book_id="book_1", character_id="character_1"),
    )["card"]
    assert "惜字如金" in card["content"] and "## 简介" in card["content"]
    for excluded in ("fact_1", "完整引文", "十年前的战役", "与城主结盟", "隐秘身份", "按章变化"):
        assert excluded not in card["content"]
    assert "完整引文" in book_db.one("SELECT content FROM knowledge_entities")["content"]


def test_compact_is_explicit_and_preserves_card_and_conversation_links(tmp_path):
    db, _ = book_with_character(tmp_path)
    service = CharacterService(db)
    card = service.from_character(
        "user_1", CardFromCharacter(book_id="book_1", character_id="character_1"),
    )["card"]
    conversation = ConversationService(db).create(
        "user_1", ConversationCreate(card_id=card["id"]),
    )
    db.execute("UPDATE cards SET content=? WHERE id=?", ("手工内容" * 1000, card["id"]))
    assert service.owned("user_1", card["id"])["content"] == "手工内容" * 1000
    with pytest.raises(HTTPException) as forbidden:
        service.compact("other", card["id"])
    assert forbidden.value.status_code == 404
    compacted = service.compact("user_1", card["id"])
    assert compacted["id"] == card["id"] and compacted["book_id"] == "book_1"
    assert len(compacted["content"]) <= 1000
    assert db.one("SELECT card_id FROM conversations WHERE id=?", (conversation["id"],))["card_id"] == card["id"]


def test_compact_preserves_intro_when_knowledge_projection_is_empty(tmp_path):
    db, book_db = book_with_character(tmp_path)
    card = CharacterService(db).from_character(
        "user_1", CardFromCharacter(book_id="book_1", character_id="character_1"),
    )["card"]
    book_db.execute("UPDATE knowledge_entities SET content=?", (json.dumps({"name": "林默"}),))
    compacted = CharacterService(db).compact("user_1", card["id"])
    assert compacted["intro"] == card["intro"]
    assert card["intro"] in compacted["content"]
