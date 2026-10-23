import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.application import create_app
from backend.app.core.config import Config
from backend.app.ai.providers import conversation_stream, harness_tools
from backend.app.ai.harness.tools import ToolExecutor
from backend.app.db.database import now


@pytest.fixture
def harness_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONAWEAVER_AGENT_DIR", str(tmp_path / "agent"))
    monkeypatch.setenv("PERSONAWEAVER_SESSION_DIR", str(tmp_path / "sessions"))
    state = {"reviews": [], "drafts": [], "decisions": [], "calls": [], "prompts": [], "fail_review": False}

    async def stream(settings, messages, json_mode=False):
        stage = "review" if json_mode and "审核器" in messages[0]["content"] else "memory" if json_mode else "draft"
        state["calls"].append(stage)
        state["prompts"].append((stage, messages))
        if stage == "review":
            if state["fail_review"]:
                raise ValueError("审核网络失败")
            value = state["reviews"].pop(0) if state["reviews"] else {"passed": True, "conflicts": []}
            yield {"text": json.dumps(value)}
        elif stage == "memory":
            yield {"text": '{"memories":[]}'}
        else:
            yield {"text": state["drafts"].pop(0) if state["drafts"] else "林默在城东等候。"}
        yield {"usage": {"input_tokens": 10, "output_tokens": 5}}

    async def decide(settings, messages, tools, mode=None):
        state["calls"].append("plan")
        decision = state["decisions"].pop(0) if state["decisions"] else {"calls": []}
        if callable(decision):
            decision = decision(messages)
        return decision, "json", {}

    monkeypatch.setattr(conversation_stream, "stream", stream)
    monkeypatch.setattr(harness_tools, "decide", decide)
    app = create_app(Config(data_dir=tmp_path, database_path=tmp_path / "test.sqlite3"))
    with TestClient(app) as client:
        user = client.get("/api/v1/auth/me").json()
        uid = user.get("user_id") or user.get("user", {}).get("user_id")
        if not uid:
            uid = app.state.db.one("SELECT user_id FROM users")["user_id"]
        db = app.state.db
        db.execute("INSERT INTO books(book_id,user_id,title,source_type,file_name,source_path,created_at,updated_at) "
                   "VALUES(?,?,?,?,?,?,?,?)", ("b", uid, "测试", "txt", "test.txt", "test.txt", now(), now()))
        db.book_database("b").execute(
            "INSERT INTO chapters(id,book_id,chapter_no,title,content,word_count) VALUES(?,?,?,?,?,?)",
            ("ch", "b", 1, "城东", "😀林默在城东等候。暗号是青灯。", 20))
        profile = client.post("/api/v1/settings/models", json={
            "name": "stub", "provider": "ollama", "base_url": "http://never-called.invalid",
            "model": "stub", "api_key": "SECRET-MUST-NOT-PERSIST", "context_window": 32768,
            "max_tokens": 512, "activate": True,
        }).json()
        cid = client.post("/api/v1/conversations", json={
            "title": "测试场景", "book_id": "b", "profile_id": profile["id"], "memory_enabled": False,
        }).json()["id"]
        yield client, state, cid, uid


def send(client, cid, rid="r"):
    return client.post(f"/api/v1/conversations/{cid}/messages",
                       json={"message": "林默在哪里？", "request_id": rid})


def test_graph_publishes_only_after_review_and_records_trace(harness_client):
    client, state, cid, _ = harness_client
    result = send(client, cid)
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["status"] == "completed"
    assert result["validation"]["passed"]
    assert state["calls"] == ["plan", "draft", "review"]
    assert len(result["messages"]) == 2
    trace = client.get(f"/api/v1/conversations/{cid}/generations/r/trace").json()["events"]
    phases = [e["payload"]["phase"] for e in trace if e["event"] == "phase"]
    assert phases == ["restore", "context", "knowledge", "plan", "draft", "review", "publish", "memory"]
    assert all(s["kind"] != "chapter" for s in result["sources"])
    assert not result["resumable"]
    assert result["checkpoint_id"]
    run = client.app.state.db.one("SELECT * FROM conversation_runs WHERE request_id='r'")
    assert "SECRET-MUST-NOT-PERSIST" not in json.dumps(run)
    tables = client.app.state.db.all("SELECT checkpoint FROM checkpoints WHERE thread_id=?", (run["thread_id"],))
    assert all(b"SECRET-MUST-NOT-PERSIST" not in bytes(r["checkpoint"]) for r in tables)
    before = list(state["calls"])
    assert send(client, cid).status_code == 200
    assert state["calls"] == before


def test_conflict_revision_is_checked_again(harness_client):
    client, state, cid, _ = harness_client
    state["drafts"] = ["冲突草稿", "修订正文"]
    state["reviews"] = [{"passed": False, "conflicts": [{"reason": "与设定冲突", "source_ids": []}]},
                        {"passed": True, "conflicts": []}]
    result = send(client, cid).json()
    assert result["reply"] == "修订正文"
    assert state["calls"].count("review") == 2
    assert "冲突草稿" not in json.dumps(result["messages"], ensure_ascii=False)


def test_repeated_conflict_never_publishes(harness_client):
    client, state, cid, _ = harness_client
    state["reviews"] = [{"passed": False, "conflicts": [{"reason": "违反原著", "source_ids": []}]}] * 2
    assert send(client, cid).status_code == 502
    result = client.get(f"/api/v1/conversations/{cid}/generations/r").json()
    assert result["phase"] == "blocked" and result["reply"] == "" and not result["resumable"]
    assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []
    assert client.app.state.db.all("SELECT * FROM conversation_memory_jobs") == []


def test_failed_review_resumes_saved_draft_without_regenerating(harness_client):
    client, state, cid, _ = harness_client
    state["fail_review"] = True
    assert send(client, cid).status_code == 502
    assert client.get(f"/api/v1/conversations/{cid}/generations/r").json()["resumable"]
    state["fail_review"] = False
    response = client.post(f"/api/v1/conversations/{cid}/generations/r/resume")
    assert response.status_code == 200, response.text
    assert '"status": "completed"' in response.text
    assert state["calls"].count("draft") == 1
    assert len(client.get(f"/api/v1/conversations/{cid}").json()["messages"]) == 2


@pytest.mark.parametrize("change", ["model", "book", "branch", "clear"])
def test_resume_refuses_stale_state(harness_client, change):
    client, state, cid, _ = harness_client
    state["fail_review"] = True
    send(client, cid)
    db = client.app.state.db
    if change == "model":
        db.execute("UPDATE model_profiles SET temperature=1.5")
    elif change == "book":
        db.book_database("b").execute("UPDATE chapters SET content=content || '新资料'")
    elif change == "branch":
        state["fail_review"] = False
        send(client, cid, "another")
    else:
        client.delete(f"/api/v1/conversations/{cid}/messages").raise_for_status()
        assert db.all("SELECT * FROM checkpoints") == []
        assert db.all("SELECT * FROM writes") == []
        assert db.all("SELECT * FROM harness_events") == []
    assert client.post(f"/api/v1/conversations/{cid}/generations/r/resume").status_code == 409


def test_original_tools_require_completed_lookup_and_obey_unicode_bounds(harness_client):
    client, _, cid, uid = harness_client
    db = client.app.state.db
    row = client.app.state.conversation_engine.service.get_owned(uid, cid)
    tools = ToolExecutor(db, uid, row)
    args = {"query": "暗号", "knowledge_call_id": "missing", "missing_question": "暗号是什么？"}
    with pytest.raises(ValueError, match="本轮"):
        tools.execute("search_original", args, [])
    prior = tools.execute("search_knowledge", {"query": "暗号"}, [])
    args["knowledge_call_id"] = prior["id"]
    result = tools.execute("search_original", args, [prior])
    assert result["items"][0]["kind"] == "chapter"
    read = tools.execute("read_original", {
        "knowledge_call_id": prior["id"], "missing_question": "暗号是什么",
        "chapter_id": "ch", "start": 1, "end": 8,
    }, [prior])
    assert read["items"][0]["quote"] == "林默在城东等候"
    assert tools.execute("search_original", args, [prior, result])["cached"]
    with pytest.raises(ValueError):
        tools.execute("read_original", {
            "knowledge_call_id": prior["id"], "missing_question": "x",
            "chapter_id": "ch", "start": 0, "end": 3000,
        }, [prior])
    with pytest.raises(ValueError):
        ToolExecutor(db, "other-user", row).execute("search_knowledge", {"query": "林默"}, [])


def test_writing_mode_cast_and_fork(harness_client):
    client, _, cid, _ = harness_client
    changed = client.patch(f"/api/v1/conversations/{cid}", json={
        "mode": "writing", "writing_format": "screenplay", "character_ids": []})
    assert changed.status_code == 200
    result = send(client, cid).json()
    assert result["mode"] == "writing" and result["writing_format"] == "screenplay"
    assert result["character_ids"] == []
    copied = client.post(f"/api/v1/conversations/{cid}/fork").json()
    assert copied["writing_format"] == "screenplay"
    assert client.app.state.db.all("SELECT * FROM conversation_runs WHERE conversation_id=?", (copied["id"],)) == []


def test_sse_draft_is_not_exposed_before_review(harness_client):
    client, state, cid, _ = harness_client
    state["reviews"] = [{"passed": False, "conflicts": [{"reason": "冲突", "source_ids": []}]}] * 2
    response = client.post(f"/api/v1/conversations/{cid}/messages/stream",
                           json={"message": "继续", "request_id": "stream"})
    assert "event: phase" in response.text and "event: terminal" in response.text
    assert "event: delta" not in response.text


@pytest.mark.parametrize("burst,expected_plans,expected_tools", [(False, 4, 5), (True, 1, 8)])
def test_tool_limits_and_duplicate_cache(harness_client, monkeypatch, burst, expected_plans, expected_tools):
    from backend.app.domains.conversation import knowledge_search
    client, state, cid, _ = harness_client
    retrieved = []
    original = knowledge_search.retrieve

    def retrieve(*args, **kwargs):
        retrieved.append(args[3])
        return original(*args, **kwargs)

    monkeypatch.setattr(knowledge_search, "retrieve", retrieve)
    call = {"name": "search_knowledge", "arguments": {"query": "不存在的问题"}}
    state["decisions"] = [{"calls": [call] * (8 if burst else 1)}] * 5
    assert send(client, cid).status_code == 200
    assert state["calls"].count("plan") == expected_plans
    trace = client.get(f"/api/v1/conversations/{cid}/generations/r/trace").json()["events"]
    tools = [e["payload"] for e in trace if e["event"] == "tool"]
    assert len(tools) == expected_tools
    assert len(retrieved) == 2
    assert any(o.get("cached") for o in tools)


def test_invalid_tool_arguments_are_observations_not_raw_access(harness_client):
    client, state, cid, _ = harness_client
    state["decisions"] = [{"calls": [
        {"name": "search_original", "arguments": {
            "query": "城东", "knowledge_call_id": "invented", "missing_question": "地点"}},
        {"name": "search_knowledge", "arguments": {"query": "林默", "book_id": "other"}},
        {"name": "search_knowledge", "arguments": {"query": "   "}},
    ]}]
    assert send(client, cid).status_code == 200
    trace = client.get(f"/api/v1/conversations/{cid}/generations/r/trace").json()["events"]
    invalid = [e for e in trace if e["event"] == "tool" and e["payload"].get("error")]
    assert len(invalid) == 3


def test_recovery_after_restart_never_calls_model_automatically(harness_client):
    from backend.app.domains.conversation.generation import GenerationEngine
    client, state, cid, _ = harness_client
    state["fail_review"] = True
    send(client, cid)
    db = client.app.state.db
    db.execute("UPDATE conversation_runs SET status='running',checkpoint_id=NULL WHERE request_id='r'")
    before = list(state["calls"])
    fresh = GenerationEngine(db)
    fresh.recover()
    client.app.state.conversation_engine = fresh
    assert state["calls"] == before
    run = client.get(f"/api/v1/conversations/{cid}/generations").json()["runs"][0]
    assert run["status"] == "interrupted" and run["resumable"] and run["message"]
    state["fail_review"] = False
    assert client.post(f"/api/v1/conversations/{cid}/generations/r/resume").status_code == 200
    assert state["calls"].count("draft") == 1
    assert len(client.get(f"/api/v1/conversations/{cid}").json()["messages"]) == 2


def test_delete_erases_run_checkpoints(harness_client):
    client, state, cid, _ = harness_client
    state["fail_review"] = True
    send(client, cid)
    assert client.delete(f"/api/v1/conversations/{cid}").status_code == 200
    for table in ("checkpoints", "writes", "harness_events", "conversation_runs"):
        assert client.app.state.db.all(f"SELECT * FROM {table}") == []


def test_selected_character_core_facts_are_always_supplied(harness_client):
    from backend.app.domains.knowledge.service import KnowledgeService
    from backend.app.domains.knowledge.schemas import CharacterCreate, FactCreate
    client, state, cid, uid = harness_client
    service = KnowledgeService(client.app.state.db)
    character = service.create_character(uid, "b", CharacterCreate(name="林默"))
    fact = service.create_fact(uid, "b", FactCreate(
        character_id=character["id"], fact_type="personality", value="绝不伤及无辜"))
    card = client.post("/api/v1/cards", json={
        "name": "林默", "book_id": "b", "intro": "寡言", "content": "说话简短"}).json()
    changed = client.patch(f"/api/v1/conversations/{cid}", json={
        "mode": "writing", "character_ids": [card["id"]]})
    assert changed.json()["character_ids"] == [card["id"]]
    response = client.post(f"/api/v1/conversations/{cid}/messages", json={
        "message": "描述不相关的天气。", "request_id": "weather"})
    assert response.status_code == 200, response.text
    source = next(s for s in response.json()["sources"] if s["id"] == f"fact:{fact['id']}")
    assert source["core"] and source["fact_version"] == 1
    draft_prompt = next(messages for stage, messages in state["prompts"] if stage == "draft")
    assert "绝不伤及无辜" in json.dumps(draft_prompt, ensure_ascii=False)


def test_failed_ancestor_memory_blocks_until_user_disables_or_retries(harness_client):
    import time
    client, state, cid, _ = harness_client
    client.patch(f"/api/v1/conversations/{cid}", json={"memory_enabled": True}).raise_for_status()
    first = send(client, cid).json()
    for _ in range(200):
        job = client.app.state.db.one("SELECT * FROM conversation_memory_jobs WHERE id=?",
                                     (first["assistant_node_id"],))
        if job and job["status"] == "completed":
            break
        time.sleep(.01)
    assert job["status"] == "completed"
    client.app.state.db.execute("UPDATE conversation_memory_jobs SET status='failed',error='test'")
    before = state["calls"].count("draft")
    assert send(client, cid, "blocked-memory").status_code == 502
    assert state["calls"].count("draft") == before
    client.patch(f"/api/v1/conversations/{cid}", json={"memory_enabled": False}).raise_for_status()
    assert send(client, cid, "disabled").status_code == 200


def test_locked_fact_survives_incremental_compaction(harness_client):
    client, state, cid, _ = harness_client
    client.app.state.db.execute("UPDATE model_profiles SET context_window=8192,max_tokens=128")
    first = send(client, cid).json()
    client.post(f"/api/v1/conversations/{cid}/memories", json={
        "key": "底线", "content": "LOCKED-绝不离开城东", "locked": True,
        "source_ids": [first["assistant_node_id"]]}).raise_for_status()
    for i in range(10):
        response = client.post(f"/api/v1/conversations/{cid}/messages", json={
            "message": f"第{i}轮" + "雨" * 550, "request_id": f"turn-{i}"})
        assert response.status_code == 200, response.text
    result = response.json()
    assert len([n for n in result["context"] if n["entry_type"] == "compaction"]) >= 2
    assert len(result["messages"]) == 22
    draft_prompts = [messages for stage, messages in state["prompts"][2:]
                     if stage == "draft" and messages[0]["role"] == "system"]
    assert len(draft_prompts) == 10
    assert all("LOCKED-绝不离开城东" in json.dumps(messages, ensure_ascii=False)
               for messages in draft_prompts)


def test_original_gap_is_supplied_without_writing_confirmed_knowledge(harness_client):
    client, state, cid, _ = harness_client

    def fill_gap(messages):
        observation = json.loads(messages[-1]["content"].split("：", 1)[1])[0]
        return {"calls": [{"name": "search_original", "arguments": {
            "query": "暗号", "knowledge_call_id": observation["id"], "missing_question": "暗号是什么？"}}]}

    state["decisions"] = [fill_gap]
    db = client.app.state.db.book_database("b")
    before = db.all("SELECT * FROM knowledge_facts")
    response = send(client, cid)
    assert response.status_code == 200, response.text
    assert any(s["kind"] == "chapter" and "青灯" in s["quote"] for s in response.json()["sources"])
    assert db.all("SELECT * FROM knowledge_facts") == before
    # A sibling run starts with its own fresh tool context, never the previous evidence.
    client.patch(f"/api/v1/conversations/{cid}/active-node", json={"node_id": None}).raise_for_status()
    sibling = send(client, cid, "sibling").json()
    assert all(s["kind"] != "chapter" for s in sibling["sources"])
    assert sibling["messages"][0]["parent_id"] is None


def test_world_projection_is_searchable_with_verified_offsets(harness_client):
    client, _, cid, uid = harness_client
    db = client.app.state.db.book_database("b")
    content = {"name": "青灯结界", "description": "城东的青灯结界",
               "source_ids": ["projected-fact"], "evidence": [{"sources": [
                   {"chapter_id": "ch", "quote": "林默在城东等候", "start": 1, "end": 8}]}]}
    db.execute("INSERT INTO knowledge_entities VALUES(?,?,?,?,?,?)",
               ("world", "b", "world_locations", "青灯结界", '["projected-fact"]',
                json.dumps(content, ensure_ascii=False)))
    row = client.app.state.conversation_engine.service.get_owned(uid, cid)
    observation = ToolExecutor(client.app.state.db, uid, row).execute(
        "search_knowledge", {"query": "青灯结界"}, [])
    source = next(s for s in observation["items"] if s["kind"] == "world_locations")
    assert source["start"] == 1 and source["end"] == 8
    assert source["source_ids"] == ["projected-fact"]


def test_live_model_change_prevents_publication(harness_client, monkeypatch):
    client, _, cid, _ = harness_client
    original = conversation_stream.stream

    async def stream(settings, messages, json_mode=False):
        async for event in original(settings, messages, json_mode):
            yield event
        if not json_mode:
            client.app.state.db.execute("UPDATE model_profiles SET temperature=1.7")

    monkeypatch.setattr(conversation_stream, "stream", stream)
    assert send(client, cid).status_code == 502
    result = client.get(f"/api/v1/conversations/{cid}/generations/r").json()
    assert result["reply"] == "" and result["usage"]["draft_0"]["actual"]
    assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []
    assert client.post(f"/api/v1/conversations/{cid}/generations/r/resume").status_code == 409


def test_explicit_tool_verification_and_config_invalidation(harness_client, monkeypatch):
    client, _, _, _ = harness_client
    profile = client.get("/api/v1/settings/models").json()["models"][0]
    assert profile["tool_support"] == "unverified"
    probes = []

    async def decide(settings, messages, tools, mode=None, *, probe=False):
        probes.append(probe)
        return {"calls": [{"name": "search_knowledge", "arguments": {"query": "capability-check"}}]}, "native", {}

    monkeypatch.setattr(harness_tools, "decide", decide)
    response = client.post(f"/api/v1/settings/models/{profile['id']}/test-tools")
    assert response.status_code == 200 and response.json()["tool_support"] == "native"
    assert probes == [True]
    client.put(f"/api/v1/settings/models/{profile['id']}", json={
        "name": profile["name"], "model": "different", "provider": profile["provider"],
        "base_url": profile["base_url"],
    }).raise_for_status()
    changed = client.get("/api/v1/settings/models").json()["models"][0]
    assert changed["tool_support"] == "unverified"
