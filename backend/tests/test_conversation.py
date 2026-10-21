import json

import pytest
from fastapi.testclient import TestClient

from backend.app.application import create_app
from backend.app.core.config import Config
from backend.app.domains.conversation.memory_context import build_context
from backend.app.domains.conversation.service import _conversation_lock
from backend.app.domains.conversation.session_store import SessionStore
from backend.app.domains.settings import llm


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONAWEAVER_AGENT_DIR", str(tmp_path / "agent"))
    monkeypatch.setenv("PERSONAWEAVER_SESSION_DIR", str(tmp_path / "sessions"))
    calls = []

    def reply(settings, messages, **kwargs):
        calls.append(messages)
        return "摘要" if len(messages) == 1 else "回答：" + messages[-1]["content"][:10]

    monkeypatch.setattr(llm, "chat", reply)
    from backend.app.ai.providers import conversation_stream

    async def stream(settings, messages, json_mode=False):
        yield {"text": '{"memories":[]}' if json_mode else reply(settings, messages)}

    monkeypatch.setattr(conversation_stream, "stream", stream)
    app = create_app(Config(data_dir=tmp_path, database_path=tmp_path / "test.sqlite3"))
    with TestClient(app) as client:
        client.get("/api/v1/auth/me").raise_for_status()
        yield client, calls


def create(client):
    response = client.post("/api/v1/conversations", json={})
    response.raise_for_status()
    return response.json()["id"]


def send(client, cid, text="你好", **kwargs):
    response = client.post(f"/api/v1/conversations/{cid}/messages", json={"message": text, **kwargs})
    response.raise_for_status()
    return response.json()


def test_compaction_restores_recent_messages_and_is_incremental(chat_client):
    client, calls = chat_client
    cid = create(client)
    for i in range(6):
        send(client, cid, f"第{i}轮" + "甲" * 250)
    first = client.post(f"/api/v1/conversations/{cid}/compact", json={"keep_recent_tokens": 700})
    assert first.status_code == 200, first.text
    first_summary_prompt = calls[-1][0]["content"]
    assert "第0轮" in first_summary_prompt
    send(client, cid, "继续")
    context = calls[-1]
    assert any("第5轮" in item["content"] for item in context)
    assert not any("第0轮" in item["content"] for item in context)
    for i in range(6, 10):
        send(client, cid, f"第{i}轮" + "乙" * 250)
    second = client.post(f"/api/v1/conversations/{cid}/compact", json={"keep_recent_tokens": 700})
    assert second.status_code == 200, second.text
    assert "第0轮" not in calls[-1][0]["content"]
    assert "摘要" in calls[-1][0]["content"]


def test_legacy_retained_tail_without_source_id():
    path = [{"id": "c", "entry_type": "compaction", "summary": "old",
             "metadata": json.dumps({"retainedTail": [
                 {"role": "user", "content": "keep"}, {"role": "assistant", "content": "yes"}]})}]
    assert [item["content"] for item in build_context("sys", "next", path)][-3:] == ["keep", "yes", "next"]


def test_branch_summary_becomes_active_and_is_not_implicit(chat_client):
    client, calls = chat_client
    cid = create(client)
    first = send(client, cid, "共同祖先")
    ancestor = first["active_leaf_id"]
    send(client, cid, "旧分支")
    count = len(calls)
    switched = client.patch(f"/api/v1/conversations/{cid}/active-node", json={"node_id": ancestor})
    assert switched.status_code == 200
    assert len(calls) == count
    send(client, cid, "新分支")
    switched = client.patch(f"/api/v1/conversations/{cid}/active-node",
                           json={"node_id": ancestor, "summary": True})
    assert switched.status_code == 200, switched.text
    result = switched.json()
    assert result["active_leaf_id"] == result["branch_summary"]["id"]
    assert result["context"][-1]["entry_type"] == "branch_summary"
    send(client, cid, "带摘要继续")
    assert any("已放弃分支摘要" in item["content"] for item in calls[-1])


def test_mirror_failure_does_not_rollback_reply_and_can_recover(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)
    original = SessionStore.rebuild
    monkeypatch.setattr(SessionStore, "rebuild", lambda *args: (_ for _ in ()).throw(OSError("disk")))
    result = send(client, cid)
    assert len(result["messages"]) == 2
    assert client.app.state.db.one("SELECT * FROM conversation_mirrors WHERE conversation_id=?", (cid,))
    monkeypatch.setattr(SessionStore, "rebuild", original)
    from backend.app.domains.conversation.mirror import sync_mirror
    assert sync_mirror(client.app.state.db, cid) is None
    assert sync_mirror(client.app.state.db, cid) is None
    row = client.get(f"/api/v1/conversations/{cid}").json()
    entries = SessionStore(client.app.state.db.path.parent).read(row["session_file"])
    assert len(entries) == 3
    assert len({entry["id"] for entry in entries}) == 3
    client.delete(f"/api/v1/conversations/{cid}/messages").raise_for_status()
    assert len(SessionStore(client.app.state.db.path.parent).read(row["session_file"])) == 1


def test_busy_conversation_rejects_branch_mutations(chat_client):
    client, _ = chat_client
    cid = create(client)
    with _conversation_lock(cid):
        assert client.patch(f"/api/v1/conversations/{cid}/active-node", json={"node_id": None}).status_code == 409
        assert client.delete(f"/api/v1/conversations/{cid}/messages").status_code == 409
        assert client.post(f"/api/v1/conversations/{cid}/messages", json={"message": "busy"}).status_code == 409


def test_corrupt_mirror_is_rebuilt_without_repeating_model_calls(chat_client):
    from pathlib import Path
    from backend.app.domains.conversation.mirror import recover_mirrors
    client, calls = chat_client
    cid = create(client)
    result = send(client, cid)
    Path(result["session_file"]).write_text("{broken", encoding="utf-8")
    recover_mirrors(client.app.state.db)
    entries = SessionStore(client.app.state.db.path.parent).read(result["session_file"])
    assert len(entries) == 3
    assert len(calls) == 1


def test_mirror_ack_does_not_erase_newer_outbox_work(chat_client, monkeypatch):
    from backend.app.db.database import identifier, now
    from backend.app.domains.conversation.mirror import sync_mirror
    from backend.app.domains.conversation.repository import ConversationRepository
    client, _ = chat_client
    cid = create(client)
    result = send(client, cid)
    db = client.app.state.db
    repo = ConversationRepository(db)
    repo.set_label(cid, result["active_leaf_id"], "before")
    original = SessionStore.rebuild

    def changed(*args, **kwargs):
        original(*args, **kwargs)
        repo.set_label(cid, result["active_leaf_id"], "newer")

    monkeypatch.setattr(SessionStore, "rebuild", changed)
    sync_mirror(db, cid)
    assert db.one("SELECT * FROM conversation_mirrors WHERE conversation_id=?", (cid,))
    monkeypatch.setattr(SessionStore, "rebuild", original)
    sync_mirror(db, cid)
    assert not db.one("SELECT * FROM conversation_mirrors WHERE conversation_id=?", (cid,))
