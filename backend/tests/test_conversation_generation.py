import asyncio
import json

import httpx
import pytest

from backend.app.ai.providers import conversation_stream as provider
from backend.app.domains.conversation.generation import GenerationEngine
from backend.app.domains.conversation.schemas import MessageRequest
from backend.app.db.database import now
from backend.tests.test_conversation import chat_client, create, send


def test_persistent_request_id_and_conflict(chat_client):
    client, calls = chat_client
    cid = create(client)
    first = send(client, cid, request_id="same")
    second = send(client, cid, request_id="same")
    assert first["assistant_node_id"] == second["assistant_node_id"]
    assert len(second["messages"]) == 2
    assert len(calls) == 1
    assert client.post(f"/api/v1/conversations/{cid}/messages",
                       json={"message": "different", "request_id": "same"}).status_code == 409
    # Replaying an old request must not move a newer branch.
    newest = send(client, cid, "next", request_id="new")
    replay = send(client, cid, request_id="same")
    assert replay["active_leaf_id"] == newest["active_leaf_id"]
    assert len(calls) == 2


def test_preview_is_model_free_and_accounts_for_output(chat_client):
    client, calls = chat_client
    cid = create(client)
    preview = client.post(f"/api/v1/conversations/{cid}/context-preview", json={"message": "甲乙丙"}).json()
    usage = preview["context_usage"]
    assert usage["context_window"] == 32768
    assert usage["input_tokens"] == sum(usage["components"].values())
    assert usage["available_input"] + usage["max_output"] + usage["safety"] == 32768
    assert calls == []
    assert client.post(f"/api/v1/conversations/{cid}/messages",
                       json={"message": "hello", "profile_id": "missing"}).status_code == 404


def test_roleplay_uses_card_intro_and_user_agency_rules(chat_client):
    client, calls = chat_client
    db = client.app.state.db
    user = client.get("/api/v1/auth/me").json()["user_id"]
    db.execute(
        "INSERT INTO books(book_id,user_id,title,source_type,file_name,source_path,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)", ("book_role", user, "Story", "txt", "a.txt", "a.txt", now(), now()),
    )
    card = client.post("/api/v1/cards", json={
        "book_id": "book_role", "name": "林默", "intro": "谨慎寡言的猎户", "content": "说话简短",
    }).json()
    response = client.post("/api/v1/conversations", json={"card_id": card["id"], "memory_enabled": False})
    response.raise_for_status()
    conversation = response.json()
    assert conversation["mode"] == "roleplay"
    result = send(client, conversation["id"], "你是谁？")
    system = calls[-1][0]["content"]
    assert "姓名：林默" in system and "谨慎寡言的猎户" in system and "说话简短" in system
    assert "角色第一人称" in system and "不要替用户编写台词" in system
    assert "你是小说创作助手" not in system
    assert result["context_usage"]["components"]["knowledge"] <= 2048


def test_preview_and_generation_disable_remote_retrieval(chat_client, monkeypatch):
    from backend.app.domains.conversation import knowledge_search

    client, _ = chat_client
    cid = create(client)
    engine = client.app.state.conversation_engine
    user = client.get("/api/v1/auth/me").json()["user_id"]
    engine.db.execute(
        "INSERT INTO books(book_id,user_id,title,source_type,file_name,source_path,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)", ("book_mock", user, "Story", "txt", "a.txt", "a.txt", now(), now()),
    )
    engine.db.execute("UPDATE conversations SET book_id='book_mock' WHERE id=?", (cid,))
    modes = []

    def retrieve(*args, **kwargs):
        modes.append(kwargs["use_embeddings"])
        return []

    monkeypatch.setattr(knowledge_search, "retrieve", retrieve)
    client.post(f"/api/v1/conversations/{cid}/context-preview", json={"message": "hello"}).raise_for_status()
    assert modes == [False]
    send(client, cid, "hello")
    assert modes == [False, False]


@pytest.mark.parametrize("transport", ["messages", "messages/stream"])
def test_chat_does_not_embed_even_with_a_selected_embedding_model(chat_client, monkeypatch, transport):
    from backend.app.domains.conversation import semantic_search
    from backend.app.domains.retrieval import vector

    client, calls = chat_client
    db = client.app.state.db
    user = client.get("/api/v1/auth/me").json()["user_id"]
    db.execute(
        "INSERT INTO books(book_id,user_id,title,source_type,file_name,source_path,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)", ("book_local", user, "Story", "txt", "a.txt", "a.txt", now(), now()),
    )
    book_db = db.book_database("book_local")
    book_db.execute(
        "INSERT INTO chapters(id,book_id,chapter_no,title,content,word_count) VALUES(?,?,?,?,?,?)",
        ("chapter_local", "book_local", 1, "城东", "林默在城东等候。", 8),
    )
    db.execute(
        "INSERT INTO model_profiles(id,user_id,name,provider,base_url,model,model_type,test_status,"
        "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("embed_disabled", user, "Embedding", "remote_api", "http://never-called.invalid",
         "embedding", "embedding", "passed", now(), now()),
    )
    db.execute(
        "INSERT INTO model_selections(user_id,embedding_model_id) VALUES(?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET embedding_model_id=excluded.embedding_model_id",
        (user, "embed_disabled"),
    )
    embedding_calls = []

    def forbidden(*args, **kwargs):
        embedding_calls.append(True)
        raise AssertionError("Chat must not invoke semantic recall or Embedding")

    monkeypatch.setattr(semantic_search, "recall", forbidden)
    monkeypatch.setattr(vector, "embed", forbidden)
    response = client.post("/api/v1/conversations", json={"book_id": "book_local", "memory_enabled": False})
    response.raise_for_status()
    cid = response.json()["id"]
    client.post(f"/api/v1/conversations/{cid}/context-preview", json={"message": "林默"}).raise_for_status()
    assert calls == [] and embedding_calls == []
    client.post(f"/api/v1/conversations/{cid}/{transport}", json={"message": "林默"}).raise_for_status()
    assert len(calls) == 1 and embedding_calls == []
    # Original text is only supplied after a model-requested, ordered fallback.
    assert "林默在城东等候" not in json.dumps(calls[0], ensure_ascii=False)
    assert book_db.one("SELECT COUNT(*) AS count FROM chapter_vectors")["count"] == 0


def test_knowledge_budget_keeps_whole_records_and_reserves_conversation_room(chat_client):
    from backend.app.domains.conversation import budget

    client, _ = chat_client
    cid = create(client)
    engine = client.app.state.conversation_engine
    user = client.get("/api/v1/auth/me").json()["user_id"]
    records = [{"id": f"source_{i}", "content": str(i) + "甲" * 400} for i in range(20)]
    prepared = budget.prepare(
        engine.service, user, engine.service.get_owned(user, cid),
        MessageRequest(message="hello"), None, optional={"knowledge": records},
    )
    usage = prepared["context_usage"]
    assert 0 < usage["components"]["knowledge"] <= min(2048, usage["available_input"] * .2)
    assert 0 < len(prepared["sources"]) < len(records)
    for source in prepared["sources"]:
        assert source["content"] in prepared["messages"][0]["content"]
    assert usage["fits"]


def test_stream_events_and_partial_failure(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)

    async def partial(*args, **kwargs):
        yield {"text": "半段😀"}
        raise httpx.ReadError("test connection failed")

    monkeypatch.setattr(provider, "stream", partial)
    response = client.post(f"/api/v1/conversations/{cid}/messages/stream",
                           json={"message": "continue", "request_id": "partial"})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[0]["request_id"] == "partial"
    assert events[-1]["status"] == "failed"
    assert events[-1]["reply"] == ""
    assert events[-1]["messages"] == []
    assert not events[-1]["assistant_node_id"]
    names = [line for line in response.text.splitlines() if line.startswith("event:")]
    assert names[0] == "event: start" and names[-1] == "event: terminal"
    assert "event: phase" in names and "event: delta" not in names


def test_zero_text_failure_does_not_save_empty_messages(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)

    async def failure(*args):
        raise ValueError("empty")
        yield

    monkeypatch.setattr(provider, "stream", failure)
    response = client.post(f"/api/v1/conversations/{cid}/messages", json={"message": "retry", "request_id": "zero"})
    assert response.status_code == 502
    assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []
    assert client.get(f"/api/v1/conversations/{cid}/generations/zero").json()["status"] == "failed"


@pytest.mark.parametrize("partial", [False, True])
def test_stop_closes_upstream_and_releases_conversation(chat_client, monkeypatch, partial):
    client, _ = chat_client
    cid = create(client)
    user = client.get("/api/v1/auth/me").json()["user_id"]
    closed = []

    async def scenario():
        entered = asyncio.Event()

        async def waiting(*args):
            try:
                if partial:
                    yield {"text": "已保存"}
                entered.set()
                await asyncio.sleep(100)
            finally:
                closed.append(True)
        monkeypatch.setattr(provider, "stream", waiting)
        engine = GenerationEngine(client.app.state.db)
        live = await engine.start(user, cid, MessageRequest(message="hi", request_id="stop"))
        await entered.wait()
        same = await engine.start(user, cid, MessageRequest(message="hi", request_id="stop"))
        assert same is live
        with pytest.raises(Exception) as busy:
            await engine.start(user, cid, MessageRequest(message="other", request_id="other"))
        assert busy.value.status_code == 409
        result = await engine.cancel(user, cid, live.request_id)
        assert result["status"] == "cancelled"
        assert result["messages"] == []
        assert closed
        # Branch changes work again after cancellation.
        client.patch(f"/api/v1/conversations/{cid}/active-node", json={"node_id": None}).raise_for_status()
    asyncio.run(scenario())


def test_restart_recovers_partial_without_model_call(chat_client):
    client, calls = chat_client
    cid = create(client)
    db = client.app.state.db
    db.execute("INSERT INTO conversation_runs(conversation_id,request_id,fingerprint,status,message,reply,created_at,updated_at) "
               "VALUES(?,?,?,?,?,?,?,?)", (cid, "crash", "hash", "running", "hello", "checkpoint", now(), now()))
    engine = GenerationEngine(db)
    engine.recover()
    engine.recover()
    result = client.get(f"/api/v1/conversations/{cid}").json()
    assert len(result["messages"]) == 2
    assert result["messages"][-1]["metadata"]["status"] == "interrupted"
    assert calls == []


def test_failed_final_transaction_is_recoverable(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)
    engine = client.app.state.conversation_engine
    original = engine.service.repo.append_exchange
    monkeypatch.setattr(engine.service.repo, "append_exchange", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    response = client.post(f"/api/v1/conversations/{cid}/messages/stream",
                           json={"message": "hi", "request_id": "disk"})
    assert '"status": "failed"' in response.text
    assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []
    monkeypatch.setattr(engine.service.repo, "append_exchange", original)
    resumed = client.post(f"/api/v1/conversations/{cid}/generations/disk/resume")
    assert resumed.status_code == 200, resumed.text
    assert len(client.get(f"/api/v1/conversations/{cid}").json()["messages"]) == 2


@pytest.mark.parametrize("protocol,payload,expected", [
    ("openai-completions", 'data: {"choices":[{"delta":{"content":"甲😀"}}]}\n\n'
     'data: {"choices":[{"finish_reason":"stop"}],"usage":{"total_tokens":4}}\n\ndata: [DONE]\n\n', "甲😀"),
    ("openai-responses", 'data: {"type":"response.output_text.delta","delta":"乙"}\n\n'
     'data: {"type":"response.completed","response":{"usage":{"input_tokens":2}}}\n\n', "乙"),
    ("ollama", '{"message":{"content":"丙"},"done":false}\n{"done":true,"eval_count":1}\n', "丙"),
    ("anthropic-messages", '{"content":[{"type":"text","text":"丁"}]}', "丁"),
    ("google-generative-ai", '{"candidates":[{"content":{"parts":[{"text":"戊"}]}}]}', "戊"),
    ("vivo", '{"choices":[{"message":{"content":"己"}}]}', "己"),
])
def test_async_protocols_use_mock_transport(monkeypatch, protocol, payload, expected):
    settings = {"provider": protocol, "api_key": "test", "base_url": "https://model.test/v1",
                "model": "test", "max_tokens": 128, "context_window": 32768}
    real_client = httpx.AsyncClient
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=payload.encode())
    monkeypatch.setattr(provider.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))

    async def check():
        output = [e async for e in provider.stream(settings, [{"role": "user", "content": "hi"}])]
        assert "".join(e.get("text", "") for e in output) == expected
    asyncio.run(check())
    assert provider.capability(settings)["native_streaming"] == (protocol in {
        "openai-completions", "openai-responses", "ollama"})
    assert len(captured) == 1


def test_native_eof_without_terminator_is_failure(monkeypatch):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _: httpx.Response(
        200, content=b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'))
    monkeypatch.setattr(provider.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))

    async def check():
        events = []
        with pytest.raises(ValueError, match="断开"):
            async for event in provider.stream({"provider": "remote_api", "model": "test", "base_url": "http://mock"}, []):
                events.append(event)
        assert events == [{"text": "partial"}]
    asyncio.run(check())


def test_stream_disconnect_saves_partial_reply(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)
    user = client.get("/api/v1/auth/me").json()["user_id"]

    async def partial(*args, **kwargs):
        yield {"text": "断连前文本"}
        await asyncio.sleep(100)

    monkeypatch.setattr(provider, "stream", partial)

    async def scenario():
        engine = GenerationEngine(client.app.state.db)
        live = await engine.start(user, cid, MessageRequest(message="hi", request_id="disconnect"))
        events = engine.events(live)
        async for event in events:
            if event.startswith("event: phase") and '"draft"' in event:
                await asyncio.sleep(.05)
                break
        await events.aclose()
        result = engine.result(user, cid, "disconnect")
        assert result["status"] == "interrupted"
        assert result["reply"] == ""
        assert result["messages"] == []
        await engine.shutdown()
    asyncio.run(scenario())


def test_context_window_is_persisted_and_auto_compaction_keeps_recent_turns(chat_client):
    client, calls = chat_client
    model = client.post("/api/v1/settings/models", json={
        "name": "small", "context_window": 4096, "max_tokens": 128, "activate": True,
    }).json()
    assert model["context_window"] == 4096
    assert client.get("/api/v1/settings/model").json()["context_window"] == 4096
    cid = create(client)
    for i in range(6):
        result = send(client, cid, f"第{i}轮" + "甲" * 400)
    assert any(e["entry_type"] == "compaction" for e in result["context"])
    assert result["context_usage"]["input_tokens"] <= result["context_usage"]["available_input"]
    assert any("第4轮" in m["content"] for m in calls[-1])
    refused = client.post(f"/api/v1/conversations/{cid}/messages", json={"message": "甲" * 5000})
    assert refused.status_code == 422


def test_clear_keeps_request_tombstone_without_retaining_text(chat_client):
    client, calls = chat_client
    cid = create(client)
    send(client, cid, "需要清空的内容", request_id="before-clear")
    client.delete(f"/api/v1/conversations/{cid}/messages").raise_for_status()
    response = client.post(f"/api/v1/conversations/{cid}/messages",
                           json={"message": "需要清空的内容", "request_id": "before-clear"})
    assert response.status_code == 409
    assert len(calls) == 1
    assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []
    row = client.app.state.db.one("SELECT * FROM conversation_runs WHERE conversation_id=?", (cid,))
    assert row["message"] == row["reply"] == ""
    assert row["cleared"] == 1
