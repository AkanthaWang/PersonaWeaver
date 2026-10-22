import json

import pytest
from fastapi import HTTPException

from backend.app.domains.conversation.knowledge_search import retrieve, rebuild_index
from backend.app.domains.knowledge.service import KnowledgeService
from backend.app.domains.knowledge.schemas import CharacterCreate, FactCreate, FactUpdate, EvidenceCreate
from backend.app.db.database import Database, now


def database_with_book(tmp_path):
    db = Database(tmp_path / "retrieval.sqlite3")
    db.initialize()
    db.execute("INSERT INTO users(user_id,username,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)",
               ("user_1", "tester", "", now(), now()))
    db.execute("INSERT INTO books(book_id,user_id,title,source_type,file_name,source_path,created_at,updated_at) "
               "VALUES(?,?,?,?,?,?,?,?)", ("book_1", "user_1", "测试", "txt", "a.txt", "a.txt", now(), now()))
    db.book_database("book_1").execute(
        "INSERT INTO chapters(id,book_id,chapter_no,title,content,word_count) VALUES(?,?,?,?,?,?)",
        ("chapter_1", "book_1", 1, "第一章", "林默受伤。", 5))
    return db


def test_chinese_recall_alias_expansion_and_unicode_evidence(tmp_path):
    db = database_with_book(tmp_path)
    scoped = db.book_database("book_1")
    scoped.execute("UPDATE chapters SET content=? WHERE id='chapter_1'", ("😀林默受伤。",))
    service = KnowledgeService(db)
    character = service.create_character("user_1", "book_1", CharacterCreate(name="林默", aliases=["小林"]))
    fact = service.create_fact("user_1", "book_1", FactCreate(
        character_id=character["id"], fact_type="status", value="受伤",
        evidence=EvidenceCreate(chapter_id="chapter_1", quote="林默受伤", start_offset=1, end_offset=5)))
    sources = retrieve(db, "user_1", "book_1", "小林怎么样")
    item = next(s for s in sources if s["id"] == "fact:" + fact["id"])
    assert item["start"] == 1 and item["end"] == 5
    assert "😀林默受伤。"[item["start"]:item["end"]] == item["quote"]
    assert all(s["book_id"] == "book_1" for s in sources)
    with pytest.raises(HTTPException) as forbidden:
        retrieve(db, "other", "book_1", "林默")
    assert forbidden.value.status_code == 404


def test_deleted_superseded_pending_and_hypothetical_records_are_excluded(tmp_path):
    db = database_with_book(tmp_path)
    service = KnowledgeService(db)
    c = service.create_character("user_1", "book_1", CharacterCreate(name="林默"))
    old = service.create_fact("user_1", "book_1", FactCreate(character_id=c["id"], fact_type="status", value="受伤"))
    new = service.update_fact("user_1", "book_1", old["id"], FactUpdate(value="痊愈"))
    sources = retrieve(db, "user_1", "book_1", "林默")
    ids = {s["id"] for s in sources}
    assert "fact:" + old["id"] not in ids
    assert "fact:" + new["id"] in ids
    revision = sources[0]["index_revision"]
    scoped = db.book_database("book_1")
    scoped.execute("UPDATE knowledge_facts SET source_type='hypothesis' WHERE id=?", (new["id"],))
    sources = retrieve(db, "user_1", "book_1", "林默")
    assert "fact:" + new["id"] not in {s["id"] for s in sources}
    assert sources[0]["index_revision"] > revision
    scoped.execute("UPDATE knowledge_facts SET source_type='agent' WHERE id=?", (new["id"],))
    scoped.execute("INSERT INTO knowledge_reviews VALUES(?,?,?,?,?,?,?,NULL,?,NULL)",
                   ("review", "book_1", "conflict", "fact", new["id"], "{}", "pending", "now"))
    assert "fact:" + new["id"] not in {s["id"] for s in retrieve(db, "user_1", "book_1", "林默")}
    service.delete_character("user_1", "book_1", c["id"], "test")
    assert not any(s["kind"] in {"character", "fact"} for s in retrieve(db, "user_1", "book_1", "林默"))


def test_bad_offsets_are_not_highlighted_and_index_is_rebuildable(tmp_path):
    db = database_with_book(tmp_path)
    service = KnowledgeService(db)
    c = service.create_character("user_1", "book_1", CharacterCreate(name="林默"))
    fact = service.create_fact("user_1", "book_1", FactCreate(
        character_id=c["id"], fact_type="status", value="受伤",
        evidence=EvidenceCreate(chapter_id="chapter_1", quote="林默受伤", start_offset=9, end_offset=13)))
    sources = retrieve(db, "user_1", "book_1", "林默")
    assert next(s for s in sources if s["id"] == "fact:" + fact["id"])["start"] is None
    scoped = db.book_database("book_1")
    before = scoped.all("SELECT * FROM chapters")
    scoped.execute("DELETE FROM chat_fts")
    assert retrieve(db, "user_1", "book_1", "林默")
    rebuild_index(scoped, "book_1")
    assert before == scoped.all("SELECT * FROM chapters")


def test_two_owned_books_never_share_search_material(tmp_path):
    db = database_with_book(tmp_path)
    db.execute("INSERT INTO books(book_id,user_id,title,source_type,file_name,source_path,created_at,updated_at) "
               "VALUES(?,?,?,?,?,?,?,?)", ("book_2", "user_1", "另一作品", "txt", "b.txt", "b.txt", now(), now()))
    db.book_database("book_2").execute(
        "INSERT INTO chapters(id,book_id,chapter_no,title,content,word_count) VALUES(?,?,?,?,?,?)",
        ("chapter_2", "book_2", 1, "第二作品", "林默在月球旅行。", 8))
    sources = retrieve(db, "user_1", "book_1", "林默月球旅行")
    assert all(item["book_id"] == "book_1" for item in sources)
    assert not any("月球" in item["content"] for item in sources)


def bind_embedding(db):
    db.execute(
        "INSERT INTO model_profiles(id,user_id,name,provider,base_url,model,model_type,test_status,"
        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("embed_1", "user_1", "Semantic", "remote_api", "http://never-called.invalid",
         "embedding", "embedding", "passed", now(), now()),
    )
    db.execute("INSERT INTO model_selections(user_id,embedding_model_id) VALUES(?,?)",
               ("user_1", "embed_1"))


def test_semantic_recall_without_keyword_overlap_and_cache_invalidation(tmp_path, monkeypatch):
    from backend.app.domains.retrieval import vector

    db = database_with_book(tmp_path)
    bind_embedding(db)
    calls = []

    def embed(settings, texts):
        calls.extend(texts)
        return [[1, 0] if text == "创伤" or "受伤" in text else [0, 1] for text in texts]

    monkeypatch.setattr(vector, "embed", embed)
    assert retrieve(db, "user_1", "book_1", "创伤", use_embeddings=False) == []
    assert calls == []
    sources = retrieve(db, "user_1", "book_1", "创伤")
    assert sources[0]["chapter_id"] == "chapter_1"
    assert sources[0]["retrieval"] == "hybrid"
    assert calls == ["创伤", "第一章\n林默受伤。"]
    retrieve(db, "user_1", "book_1", "创伤")
    assert calls[-1] == "创伤" and len(calls) == 3
    db.book_database("book_1").execute("UPDATE chapters SET content='林默已经康复。'")
    assert retrieve(db, "user_1", "book_1", "创伤") == []
    assert calls[-1] == "第一章\n林默已经康复。"


def test_semantic_failures_fall_back_without_logging_credentials(tmp_path, monkeypatch, caplog):
    from backend.app.domains.retrieval import vector

    db = database_with_book(tmp_path)
    bind_embedding(db)

    def failed(*args):
        raise RuntimeError("request failed with api_key=private-secret")

    monkeypatch.setattr(vector, "embed", failed)
    sources = retrieve(db, "user_1", "book_1", "林默")
    assert sources and sources[0]["retrieval"] == "keyword"
    assert "using keyword recall" in caplog.text and "private-secret" not in caplog.text


def test_semantic_recall_excludes_deleted_facts_and_other_books(tmp_path, monkeypatch):
    from backend.app.domains.retrieval import vector

    db = database_with_book(tmp_path)
    bind_embedding(db)
    seen = []

    def embed(settings, texts):
        seen.extend(texts)
        return [[1, 0] for _ in texts]

    monkeypatch.setattr(vector, "embed", embed)
    service = KnowledgeService(db)
    character = service.create_character("user_1", "book_1", CharacterCreate(name="林默"))
    fact = service.create_fact("user_1", "book_1", FactCreate(
        character_id=character["id"], fact_type="status", value="受伤"))
    fact_id = "fact:" + fact["id"]
    assert fact_id in {s["id"] for s in retrieve(db, "user_1", "book_1", "近况")}
    db.book_database("book_1").execute(
        "UPDATE knowledge_facts SET deleted_at=? WHERE id=?", (now(), fact["id"]),
    )
    assert fact_id not in {s["id"] for s in retrieve(db, "user_1", "book_1", "近况")}
    db.execute(
        "INSERT INTO books(book_id,user_id,title,source_type,file_name,source_path,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)", ("book_2", "user_1", "Other", "txt", "b.txt", "b.txt", now(), now()),
    )
    db.book_database("book_2").execute(
        "INSERT INTO chapters(id,book_id,chapter_no,title,content,word_count) VALUES(?,?,?,?,?,?)",
        ("chapter_2", "book_2", 1, "Other", "DO_NOT_SEND_OTHER_BOOK", 8),
    )
    seen.clear()
    sources = retrieve(db, "user_1", "book_1", "近况")
    assert all(s["book_id"] == "book_1" for s in sources)
    assert not any("DO_NOT_SEND_OTHER_BOOK" in text for text in seen)
    with pytest.raises(HTTPException):
        retrieve(db, "other", "book_1", "近况")
