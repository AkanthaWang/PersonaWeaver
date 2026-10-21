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
    assert events[-1]["status"] == "interrupted"
    assert events[-1]["reply"] == "半段😀"
    assert events[-1]["messages"][-1]["metadata"]["status"] == "interrupted"
    assert events[-1]["assistant_node_id"]
    assert [line for line in response.text.splitlines() if line.startswith("event:")] == [
        "event: start", "event: context", "event: sources", "event: delta", "event: terminal"]


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
        assert len(result["messages"]) == (2 if partial else 0)
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
    assert '"storage_error": true' in response.text
    assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []
    monkeypatch.setattr(engine.service.repo, "append_exchange", original)
    engine.recover()
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
            if event.startswith("event: delta"):
                break
        await events.aclose()
        result = engine.result(user, cid, "disconnect")
        assert result["status"] == "interrupted"
        assert result["reply"] == "断连前文本"
        assert len(result["messages"]) == 2
        await engine.shutdown()
    asyncio.run(scenario())


def test_context_window_is_persisted_and_auto_compaction_keeps_recent_turns(chat_client):
    client, calls = chat_client
    model = client.post("/api/v1/settings/models", json={
        "name": "small", "context_window": 2048, "max_tokens": 128, "activate": True,
    }).json()
    assert model["context_window"] == 2048
    assert client.get("/api/v1/settings/model").json()["context_window"] == 2048
    cid = create(client)
    for i in range(6):
        result = send(client, cid, f"第{i}轮" + "甲" * 160)
    assert any(e["entry_type"] == "compaction" for e in result["context"])
    assert result["context_usage"]["input_tokens"] <= result["context_usage"]["available_input"]
    assert any("第4轮" in m["content"] for m in calls[-1])
    refused = client.post(f"/api/v1/conversations/{cid}/messages", json={"message": "甲" * 1200})
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
