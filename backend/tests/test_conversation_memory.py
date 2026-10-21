import asyncio
import json
import time

import pytest
from fastapi import HTTPException

from backend.app.ai.providers import conversation_stream as provider
from backend.app.domains.conversation.memories import ExtractedMemory
from backend.tests.test_conversation import chat_client, create, send


def wait_jobs(client, cid):
    for _ in range(150):
        result = client.get(f"/api/v1/conversations/{cid}/memories").json()
        if all(job["status"] not in {"queued", "running"} for job in result["jobs"]):
            return result
        time.sleep(.01)
    raise AssertionError("memory worker did not finish")


def manual(client, cid, **overrides):
    response = client.post(f"/api/v1/conversations/{cid}/memories",
                           json={"key": "约定", "content": "去城东", **overrides})
    response.raise_for_status()
    return response.json()


def test_manual_memory_versions_are_branch_local_and_undoable(chat_client):
    client, _ = chat_client
    cid = create(client)
    send(client, cid)
    result = manual(client, cid)
    ancestor = result["conversation"]["active_leaf_id"]
    memory = result["items"][0]
    send(client, cid, "分支A")
    edited = client.put(f"/api/v1/conversations/{cid}/memories/{memory['memory_id']}",
                        json={"key": "约定", "content": "去城西", "expected_version": memory["id"]})
    edited.raise_for_status()
    branch_a = edited.json()["conversation"]["active_leaf_id"]
    assert edited.json()["items"][0]["content"] == "去城西"
    client.patch(f"/api/v1/conversations/{cid}/active-node", json={"node_id": ancestor}).raise_for_status()
    assert client.get(f"/api/v1/conversations/{cid}/memories").json()["items"][0]["content"] == "去城东"
    send(client, cid, "分支B")
    deleted = client.delete(f"/api/v1/conversations/{cid}/memories/{memory['memory_id']}").json()
    assert deleted["items"][0]["deleted"]
    undone = client.post(f"/api/v1/conversations/{cid}/memories/{memory['memory_id']}/undo").json()
    assert not undone["items"][0]["deleted"]
    assert undone["items"][0]["content"] == "去城东"
    assert len(undone["versions"]) == 3
    client.patch(f"/api/v1/conversations/{cid}/active-node", json={"node_id": branch_a}).raise_for_status()
    assert client.get(f"/api/v1/conversations/{cid}/memories").json()["items"][0]["content"] == "去城西"
    bad = client.put(f"/api/v1/conversations/{cid}/memories/{memory['memory_id']}",
                     json={"key": "约定", "content": "stale", "expected_version": memory["id"]})
    assert bad.status_code == 409


def test_automatic_memory_cannot_overwrite_locked_or_revive_deleted(chat_client):
    client, _ = chat_client
    cid = create(client)
    run = send(client, cid)
    item = manual(client, cid)["items"][0]
    memory = client.app.state.conversation_engine.memory
    path = memory.service.repo.path(cid, run["assistant_node_id"])
    incoming = [ExtractedMemory(category="experience", key="约定", content="错误覆盖",
                                source_ids=[run["assistant_node_id"]])]
    memory.apply_automatic(cid, run["assistant_node_id"], path, incoming)
    assert len(client.get(f"/api/v1/conversations/{cid}/memories").json()["versions"]) == 1
    client.delete(f"/api/v1/conversations/{cid}/memories/{item['memory_id']}").raise_for_status()
    memory.apply_automatic(cid, run["assistant_node_id"], path, incoming)
    visible = client.get(f"/api/v1/conversations/{cid}/memories").json()
    assert visible["items"][0]["deleted"]
    assert len(visible["versions"]) == 2


def test_memory_sources_and_conversation_ownership_are_validated(chat_client):
    client, _ = chat_client
    cid = create(client)
    response = client.post(f"/api/v1/conversations/{cid}/memories",
                           json={"key": "bad", "content": "bad", "source_ids": ["not-visible"]})
    assert response.status_code == 422
    engine = client.app.state.conversation_engine
    with pytest.raises(HTTPException) as error:
        engine.memory.list("other-user", cid)
    assert error.value.status_code == 404


def test_complete_turn_extracts_once_and_partial_turn_never_extracts(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)
    extraction_calls = []

    async def stream(settings, messages, json_mode=False):
        if json_mode:
            data = json.loads(messages[-1]["content"])
            extraction_calls.append(data)
            yield {"text": json.dumps({"memories": [{"category": "promise", "key": "重逢", "content": "约定明日见",
                                                     "source_ids": [data["messages"][-1]["id"]]}]})}
        else:
            yield {"text": "明日见"}
    monkeypatch.setattr(provider, "stream", stream)
    send(client, cid, "约定", request_id="one")
    first = wait_jobs(client, cid)
    assert first["jobs"][0]["status"] == "completed"
    assert first["items"][0]["category"] == "promise"
    send(client, cid, "约定", request_id="one")
    assert len(extraction_calls) == 1

    async def partial(*args, **kwargs):
        yield {"text": "半段"}
        raise ValueError("断开")
    monkeypatch.setattr(provider, "stream", partial)
    send(client, cid, "partial", request_id="partial")
    assert len(wait_jobs(client, cid)["jobs"]) == 1
    assert len(extraction_calls) == 1


def test_bad_source_is_warning_and_can_retry(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)
    valid = False

    async def stream(settings, messages, json_mode=False):
        if not json_mode:
            yield {"text": "reply"}
            return
        data = json.loads(messages[-1]["content"])
        source = data["messages"][-1]["id"] if valid else "invented"
        yield {"text": json.dumps({"memories": [{"category": "scene", "key": "地点", "content": "城东",
                                                 "source_ids": [source]}]})}
    monkeypatch.setattr(provider, "stream", stream)
    result = send(client, cid, request_id="retry")
    failed = wait_jobs(client, cid)
    assert failed["jobs"][0]["status"] == "failed"
    assert result["status"] == "completed"
    valid = True
    client.post(f"/api/v1/conversations/{cid}/memory-jobs/{result['assistant_node_id']}/retry").raise_for_status()
    success = wait_jobs(client, cid)
    assert success["jobs"][0]["status"] == "completed"
    assert len(success["items"]) == 1


def test_fork_copies_checkpoints_and_memory_with_remapped_nodes(chat_client):
    client, _ = chat_client
    cid = create(client)
    send(client, cid)
    manual(client, cid)
    original = client.get(f"/api/v1/conversations/{cid}").json()
    clone = client.post(f"/api/v1/conversations/{cid}/fork")
    clone.raise_for_status()
    new_id = clone.json()["id"]
    copied = client.get(f"/api/v1/conversations/{new_id}").json()
    assert [v["entry_type"] for v in copied["context"]] == [v["entry_type"] for v in original["context"]]
    assert not {v["id"] for v in copied["context"]} & {v["id"] for v in original["context"]}
    memories = client.get(f"/api/v1/conversations/{new_id}/memories").json()
    assert memories["items"][0]["content"] == "去城东"
    assert memories["jobs"] == []
    client.delete(f"/api/v1/conversations/{new_id}/messages").raise_for_status()
    assert client.get(f"/api/v1/conversations/{new_id}/memories").json()["items"] == []


def test_late_automatic_job_stays_on_its_source_branch(chat_client):
    client, _ = chat_client
    cid = create(client)
    common = send(client, cid, "共同起点")["active_leaf_id"]
    branch_a = send(client, cid, "剧情A")["assistant_node_id"]
    client.patch(f"/api/v1/conversations/{cid}/active-node", json={"node_id": common}).raise_for_status()
    send(client, cid, "剧情B")
    memory = client.app.state.conversation_engine.memory
    path = memory.service.repo.path(cid, branch_a)
    memory.apply_automatic(cid, branch_a, path, [
        ExtractedMemory(category="experience", key="A分支事件", content="只在A分支发生", source_ids=[branch_a])])
    assert client.get(f"/api/v1/conversations/{cid}/memories").json()["items"] == []
    client.patch(f"/api/v1/conversations/{cid}/active-node", json={"node_id": branch_a}).raise_for_status()
    assert client.get(f"/api/v1/conversations/{cid}/memories").json()["items"][0]["content"] == "只在A分支发生"


def test_memory_jobs_are_ordered_and_restart_requires_manual_retry(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)
    order = []
    concurrent = 0

    async def stream(settings, messages, json_mode=False):
        nonlocal concurrent
        if json_mode:
            concurrent += 1
            assert concurrent == 1
            order.append(json.loads(messages[-1]["content"])["messages"][0]["content"])
            await asyncio.sleep(.06)
            concurrent -= 1
            yield {"text": '{"memories":[]}'}
        else:
            yield {"text": "reply"}
    monkeypatch.setattr(provider, "stream", stream)
    send(client, cid, "第一轮", request_id="first")
    second = send(client, cid, "第二轮", request_id="second")
    assert len(wait_jobs(client, cid)["jobs"]) == 2
    assert order == ["第一轮", "第二轮"]
    client.app.state.db.execute("UPDATE conversation_memory_jobs SET status='running' WHERE id=?", (second["assistant_node_id"],))
    client.app.state.conversation_engine.memory.recover()
    result = wait_jobs(client, cid)
    assert result["jobs"][-1]["status"] == "failed"
    assert order == ["第一轮", "第二轮"]


def test_clear_cancels_background_memory_and_cannot_resurrect_it(chat_client, monkeypatch):
    client, _ = chat_client
    cid = create(client)
    entered, closed = [], []

    async def stream(settings, messages, json_mode=False):
        if json_mode:
            entered.append(True)
            try:
                await asyncio.sleep(100)
            finally:
                closed.append(True)
            yield {"text": '{"memories":[]}'}
        else:
            yield {"text": "reply"}
    monkeypatch.setattr(provider, "stream", stream)
    send(client, cid, "待提炼")
    for _ in range(100):
        if entered:
            break
        time.sleep(.01)
    assert entered
    client.delete(f"/api/v1/conversations/{cid}/messages").raise_for_status()
    assert closed
    assert client.get(f"/api/v1/conversations/{cid}/memories").json() == {
        "items": [], "versions": [], "jobs": []}
    assert not client.app.state.conversation_engine.memory.settings_cache
