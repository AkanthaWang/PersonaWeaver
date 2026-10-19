import json
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.ai.extraction_pipeline import KINDS, combine, request_json, segments, validate_extraction
from backend.app.ai.providers.api_types import ModelResponseError, extract_openai_content
from backend.app.application import create_app
from backend.app.core.config import Config
from backend.app.domains.documents import knowledge
from backend.app.domains.documents.schemas import ExtractRequest
from backend.app.domains.settings import llm
from backend.app.domains.workflow import tasks
from backend.app.domains.workflow.extraction import lookup_segments


def empty():
    return {kind: [] for kind in KINDS}


def model_reply(settings, messages, **kwargs):
    prompt = json.loads(messages[1]["content"])
    if isinstance(prompt, list):
        return json.dumps({"paragraphs": [{"text": "人物事实归纳", "fact_ids": [fact["fact_id"] for fact in prompt]}]})
    result = empty()
    for part in prompt["segments"]:
        if "林川" in part["text"]:
            result["characters"].append({
                "name": "林川", "identity": "医师", "state_changes": ["来到此地"],
                "evidence": [{"segment_id": part["segment_id"], "quote": "林川"}],
            })
    return json.dumps(result)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONAWEAVER_AGENT_DIR", str(tmp_path / "agent"))
    app = create_app(Config(data_dir=tmp_path, database_path=tmp_path / "test.sqlite3"))
    with TestClient(app) as client:
        client.get("/api/v1/auth/me").raise_for_status()
        response = client.post("/api/v1/settings/models", json={
            "name": "提取模型", "model": "extract-test", "provider": "remote_api",
            "base_url": "http://127.0.0.1:9999/v1", "api_key": "secret-key", "activate": False,
        })
        response.raise_for_status()
        profile_id = response.json()["id"]
        monkeypatch.setattr(llm, "chat", lambda *args, **kwargs: "OK")
        client.post(f"/api/v1/settings/models/{profile_id}/test").raise_for_status()
        client.put("/api/v1/settings/selection", json={"extraction_model_id": profile_id}).raise_for_status()
        monkeypatch.setattr(llm, "chat", model_reply)
        yield client


def book(client, text="第一章 起点\n林川走来。\n\n第二章 旅途\n林川来到城中。\n\n第三章 后续\n林川离开。"):
    response = client.post("/api/v1/books", params={"filename": "作品.txt"}, content=text.encode())
    response.raise_for_status()
    book_id = response.json()["book_id"]
    client.post(f"/api/v1/books/{book_id}/parse").raise_for_status()
    return book_id


def extract(client, book_id, **kwargs):
    response = client.post("/api/v1/extract", json={"book_id": book_id, **kwargs})
    response.raise_for_status()
    return client.get("/api/v1/tasks/" + response.json()["task_id"]).json()


def summaries(client, book_id):
    return client.get("/api/v1/summaries", params={"book_id": book_id}).json()


def test_long_chapter_segments_cover_tail_and_bound_overlap():
    chapter = {"id": "c", "book_id": "b", "chapter_no": 1, "title": "章",
               "content": ("段落" * 1700 + "\n") * 5 + "结尾"}
    parts = segments(chapter)
    assert len(parts) > 2
    assert parts[-1]["text"].endswith("结尾")
    assert all(len(p["text"]) <= 6000 for p in parts)
    assert parts[0]["start"] == 0 and parts[-1]["end"] == len(chapter["content"])
    assert all(0 <= a["end"] - b["start"] <= 300 for a, b in zip(parts, parts[1:]))


def test_unicode_occurrences_and_overlap_deduplication():
    chapter = {"id": "c", "book_id": "b", "chapter_no": 1, "title": "章", "content": "甲😀林川，林川"}
    part = segments(chapter)[0]
    result = empty()
    result["characters"] = [{"name": "林川", "evidence": [
        {"segment_id": part["segment_id"], "quote": "林川", "occurrence": 2},
    ]}]
    payload = validate_extraction(result, [part])
    source = payload["characters"][0]["sources"][0]
    assert source["start"] == 5
    assert chapter["content"][source["start"]:source["end"]] == "林川"
    assert len(combine([payload, payload])["characters"]) == 1
    result["characters"][0]["evidence"][0]["quote"] = "虚构"
    with pytest.raises(ValueError):
        validate_extraction(result, [part])


def test_empty_is_valid_but_missing_and_wrong_types_fail():
    assert validate_extraction(empty(), [])["characters"] == []
    with pytest.raises(ValidationError):
        validate_extraction({}, [])
    with pytest.raises(ValidationError):
        validate_extraction({**empty(), "items": "错误"}, [])


def test_repair_once_including_parser_errors(monkeypatch):
    invoke = Mock(side_effect=[ValueError("bad JSON"), json.dumps(empty())])
    monkeypatch.setattr(llm, "chat", invoke)
    assert request_json({}, [], lambda value: validate_extraction(value, []))["items"] == []
    assert invoke.call_count == 2
    invoke.side_effect = ["wrong", "still wrong"]
    with pytest.raises(ValueError):
        request_json({}, [], lambda value: value)
    assert invoke.call_count == 4


def test_transient_retries_and_auth_failure(monkeypatch):
    monkeypatch.setattr("backend.app.ai.extraction_pipeline.time.sleep", lambda _: None)
    invoke = Mock(side_effect=[requests.Timeout(), requests.Timeout(), "{}"])
    monkeypatch.setattr(llm, "chat", invoke)
    assert request_json({}, [], lambda value: value) == {}
    assert invoke.call_count == 3
    response = requests.Response()
    response.status_code = 401
    invoke.reset_mock(side_effect=True)
    invoke.side_effect = requests.HTTPError(response=response)
    with pytest.raises(requests.HTTPError):
        request_json({}, [], lambda value: value)
    assert invoke.call_count == 1


def test_incremental_range_preserves_other_chapters_and_reuses(client, monkeypatch):
    book_id = book(client)
    first = extract(client, book_id, max_chapters=1)
    assert first["status"] == "completed", first
    assert summaries(client, book_id)["coverage"] == [1]
    second = extract(client, book_id, chapter_start=2, chapter_end=3)
    assert second["status"] == "completed", second
    data = summaries(client, book_id)
    assert data["coverage"] == [1, 2, 3] and data["revision"] == 2
    person = next(row for row in data["summaries"] if row["type"] == "characters")["content"][0]
    assert len(person["evidence"]) == 3 and person["synthesis_status"] == "ready"
    assert person["evidence"][0]["sources"][0]["book_id"] == book_id
    monkeypatch.setattr(llm, "chat", Mock(side_effect=AssertionError("cache should be reused")))
    third = extract(client, book_id)
    assert third["status"] == "completed", third
    assert third["reused_units"] >= 3
    units = client.get(f"/api/v1/tasks/{third['id']}/units").json()
    assert all("payload" not in row for row in units["units"])
    assert "secret-key" not in json.dumps(third)


@pytest.mark.parametrize("params", [
    {"chapter_start": 2}, {"chapter_start": 3, "chapter_end": 2},
    {"max_chapters": 2, "chapter_start": 1, "chapter_end": 2},
    {"chapter_start": 1, "chapter_end": 99}, {"max_chapters": 99},
])
def test_invalid_range_is_rejected_before_task_creation(client, params):
    book_id = book(client)
    before = len(client.get("/api/v1/tasks").json()["tasks"])
    assert client.post("/api/v1/extract", json={"book_id": book_id, **params}).status_code == 422
    assert len(client.get("/api/v1/tasks").json()["tasks"]) == before


def test_failure_keeps_published_data_and_retry_uses_checkpoints(client, monkeypatch):
    book_id = book(client)
    extract(client, book_id, max_chapters=1)
    previous = summaries(client, book_id)
    calls = []

    def failing(settings, messages, **kwargs):
        data = json.loads(messages[1]["content"])
        if isinstance(data, dict):
            chapter_no = data["segments"][0]["chapter_no"]
            calls.append(chapter_no)
            if chapter_no == 3:
                raise RuntimeError("模拟失败")
        return model_reply(settings, messages)

    monkeypatch.setattr(llm, "chat", failing)
    failed = extract(client, book_id)
    assert failed["status"] == "failed"
    assert summaries(client, book_id) == previous
    assert calls == [2, 3]
    monkeypatch.setattr(llm, "chat", model_reply)
    retry = client.post(f"/api/v1/tasks/{failed['id']}/retry")
    assert retry.status_code == 202, retry.text
    task = client.get("/api/v1/tasks/" + retry.json()["task_id"]).json()
    assert task["status"] == "completed", task
    assert task["reused_units"] >= 2 and task["parent_task_id"] == failed["id"]


def test_cancel_before_publish_keeps_previous_results(client, monkeypatch):
    book_id = book(client)
    extract(client, book_id, max_chapters=1)
    previous = summaries(client, book_id)
    from backend.app.domains.workflow.extraction import ExtractionWorker
    original = ExtractionWorker.step

    def step(worker, stage, label, percent):
        original(worker, stage, label, percent)
        if stage == "publish":
            client.post(f"/api/v1/tasks/{worker.task_id}/cancel").raise_for_status()

    monkeypatch.setattr(ExtractionWorker, "step", step)
    cancelled = extract(client, book_id)
    assert cancelled["status"] == "cancelled", cancelled
    assert summaries(client, book_id) == previous
    assert client.post(f"/api/v1/tasks/{cancelled['id']}/cancel").status_code == 409


def test_lookup_is_bounded_to_selected_chapters():
    chapters = [{"id": f"c{i}", "book_id": "b", "chapter_no": i, "title": str(i),
                 "content": "林川" * 4000} for i in range(1, 5)]
    inputs = lookup_segments(chapters[1:3], chapters[1], [{"query": "林川", "subject": "林川"}], set())
    assert all(part["chapter_no"] in {2, 3} for part in inputs)
    assert len(inputs) <= 3 and sum(len(part["text"]) for part in inputs) <= 6000


def test_retry_refuses_model_or_input_changes(client, monkeypatch):
    book_id = book(client)
    monkeypatch.setattr(llm, "chat", Mock(side_effect=RuntimeError("stop")))
    failed = extract(client, book_id)
    client.app.state.db.execute("UPDATE chapters SET content=content || '修改' WHERE book_id=?", (book_id,))
    assert client.post(f"/api/v1/tasks/{failed['id']}/retry").status_code == 409
    client.app.state.db.execute("UPDATE model_profiles SET model='other'")
    assert client.post(f"/api/v1/tasks/{failed['id']}/retry").status_code == 409


def test_manual_split_merge_revision_and_cards_are_independent(client):
    book_id = book(client)
    extract(client, book_id)
    data = summaries(client, book_id)
    people = next(row["content"] for row in data["summaries"] if row["type"] == "characters")
    person = people[0]
    card = client.post("/api/v1/cards", json={"book_id": book_id, "name": "林川", "source_entity_id": person["entity_id"]})
    assert card.status_code == 201, card.text
    old_card = card.json()
    body = {"revision": data["revision"], "action": "split", "source_ids": person["source_ids"][:1]}
    response = client.post(f"/api/v1/books/{book_id}/entity-resolutions", json=body)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert client.post(f"/api/v1/books/{book_id}/entity-resolutions", json=body).status_code == 409
    people = next(row["content"] for row in updated["summaries"] if row["type"] == "characters")
    assert len(people) == 2
    assert all(not p["synthesis"] for p in people)
    assert client.post("/api/v1/cards", json={"book_id": book_id, "name": "林川"}).status_code == 422
    extract(client, book_id)
    updated = summaries(client, book_id)
    people = next(row["content"] for row in updated["summaries"] if row["type"] == "characters")
    assert len(people) == 2
    response = client.post(f"/api/v1/books/{book_id}/entity-resolutions", json={
        "revision": updated["revision"], "action": "merge", "source_ids": people[0]["source_ids"],
        "other_source_ids": people[1]["source_ids"],
    })
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/cards").json()["cards"][0]["content"] == old_card["content"]


def test_active_task_blocks_mutation_and_duplicate_task(client):
    book_id = book(client)
    task_id = tasks.create_task(client.app.state.db, book_id, "extract")
    assert client.post("/api/v1/extract", json={"book_id": book_id}).status_code == 409
    assert client.post(f"/api/v1/books/{book_id}/entity-resolutions", json={
        "revision": 0, "action": "merge", "source_ids": ["missing"],
    }).status_code == 409
    client.app.state.db.initialize()
    assert client.get(f"/api/v1/tasks/{task_id}").json()["status"] == "failed"


def test_other_user_cannot_access_tasks_knowledge_or_cards(client):
    book_id = book(client)
    task = extract(client, book_id)
    db = client.app.state.db
    owner = db.one("SELECT * FROM users LIMIT 1")
    db.execute("INSERT INTO users(user_id,username,password_hash,created_at,updated_at) VALUES(?,?,?,?,?)",
               ("other", "other", "", owner["created_at"], owner["updated_at"]))
    db.execute("UPDATE books SET user_id='other' WHERE book_id=?", (book_id,))
    assert client.get(f"/api/v1/tasks/{task['id']}/units").status_code == 404
    assert client.post(f"/api/v1/tasks/{task['id']}/cancel").status_code == 404
    assert client.get("/api/v1/summaries", params={"book_id": book_id}).status_code == 404
    assert client.post("/api/v1/cards", json={"book_id": book_id, "name": "越权"}).status_code == 404


def test_explicit_alias_and_same_name_conflict_remain_separate():
    chapters = [{"id": f"c{i}", "book_id": "b", "chapter_no": i, "title": str(i),
                 "content": "林川又名小川，是医师。"} for i in range(1, 4)]
    payloads = []
    for chapter, name, identity, aliases in zip(chapters, ["林川", "小川", "林川"], ["医师", "医师", "守卫"], [["小川"], [], []]):
        part = segments(chapter)[0]
        raw = {**empty(), "characters": [{"name": name, "identity": identity, "aliases": aliases, "evidence": [
            {"segment_id": part["segment_id"], "quote": chapter["content"]},
        ]}]}
        payloads.append((chapter, validate_extraction(raw, [part])))
    projected, _ = knowledge.project(payloads, [], [])
    assert len(projected["characters"]) == 2
    assert all(person["needs_review"] for person in projected["characters"])
    assert sorted(len(person["source_ids"]) for person in projected["characters"]) == [1, 2]


def test_force_recomputes_selected_only_and_model_change_invalidates_cache(client, monkeypatch):
    book_id = book(client)
    extract(client, book_id)
    invoke = Mock(side_effect=model_reply)
    monkeypatch.setattr(llm, "chat", invoke)
    task = extract(client, book_id, chapter_start=2, chapter_end=2, force=True)
    assert task["status"] == "completed", task
    extraction_calls = [call for call in invoke.call_args_list if isinstance(json.loads(call.args[1][1]["content"]), dict)]
    assert len(extraction_calls) == 1
    assert summaries(client, book_id)["coverage"] == [1, 2, 3]
    invoke.reset_mock()
    client.app.state.db.execute("UPDATE model_profiles SET model='changed-model'")
    task = extract(client, book_id)
    assert task["status"] == "completed", task
    assert task["reused_units"] == 0 and invoke.call_count >= 4


def test_empty_results_are_successful_and_legacy_results_survive(client, monkeypatch):
    book_id = book(client)
    db = client.app.state.db
    first = db.one("SELECT id FROM chapters WHERE book_id=? ORDER BY chapter_no", (book_id,))
    db.execute("INSERT INTO extractions VALUES(?,?,?,?,?,?)", (
        "legacy", book_id, first["id"], json.dumps({**empty(), "items": [{"name": "旧物品", "summary": "旧资料"}]}),
        "old", "now",
    ))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps(empty()))
    task = extract(client, book_id, chapter_start=2, chapter_end=3)
    assert task["status"] == "completed", task
    data = summaries(client, book_id)
    assert data["coverage"] == [1, 2, 3]
    assert next(row["content"] for row in data["summaries"] if row["type"] == "items")[0]["name"] == "旧物品"


def test_invalidated_human_decision_becomes_pending(client, monkeypatch):
    book_id = book(client)
    extract(client, book_id)
    data = summaries(client, book_id)
    person = next(row["content"][0] for row in data["summaries"] if row["type"] == "characters")
    client.post(f"/api/v1/books/{book_id}/entity-resolutions", json={
        "revision": data["revision"], "action": "split", "source_ids": person["source_ids"][:1],
    }).raise_for_status()

    def changed(settings, messages, **kwargs):
        value = json.loads(model_reply(settings, messages))
        for entry in value.get("characters", []):
            entry["description"] = "不同的事实字段"
        return json.dumps(value)

    monkeypatch.setattr(llm, "chat", changed)
    assert extract(client, book_id, force=True)["status"] == "completed"
    data = summaries(client, book_id)
    assert len(data["pending_resolutions"]) == 1
    decision_id = data["pending_resolutions"][0]["id"]
    response = client.delete(f"/api/v1/books/{book_id}/entity-resolutions/{decision_id}", params={"revision": data["revision"]})
    assert response.status_code == 200
    assert not summaries(client, book_id)["pending_resolutions"]


def test_supplement_cache_is_range_sensitive_and_no_embedding_required(client, monkeypatch):
    book_id = book(client)
    lookups = []

    def questioning(settings, messages, **kwargs):
        prompt = json.loads(messages[1]["content"])
        value = json.loads(model_reply(settings, messages))
        if isinstance(prompt, dict):
            if prompt.get("questions"):
                lookups.append({part["chapter_no"] for part in prompt["segments"]})
            elif prompt["segments"][0]["chapter_no"] == 1:
                value["questions"] = [{"kind": "identity", "query": "林川", "subject": "林川"}]
        return json.dumps(value)

    monkeypatch.setattr(llm, "chat", questioning)
    first = extract(client, book_id, max_chapters=1)
    assert first["status"] == "completed", first
    assert all(numbers <= {1} for numbers in lookups)
    lookups.clear()
    second = extract(client, book_id, max_chapters=2)
    assert second["status"] == "completed", second
    assert lookups and any(2 in numbers for numbers in lookups)


def test_restart_retains_completed_checkpoints_for_manual_resume(client, monkeypatch):
    book_id = book(client)
    from backend.app.domains.workflow.extraction import ExtractionWorker
    from backend.app.domains.documents.service import DocumentService
    from backend.app.domains.workflow.extraction import Cancelled
    db = client.app.state.db
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    record, task_id, settings = DocumentService(db).start_extract(user_id, book_id)
    original = ExtractionWorker.step

    def restart(worker, stage, label, percent):
        if stage == "merge":
            db.initialize()
        original(worker, stage, label, percent)

    monkeypatch.setattr(ExtractionWorker, "step", restart)
    worker = ExtractionWorker(db, record, task_id, settings)
    with pytest.raises(Cancelled):
        worker.run(db.all("SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_no", (book_id,)))
    assert db.one("SELECT status FROM tasks WHERE id=?", (task_id,))["status"] == "failed"
    assert len(db.all("SELECT id FROM extraction_units WHERE task_id=? AND status='completed'", (task_id,))) == 3
    monkeypatch.setattr(ExtractionWorker, "step", original)
    response = client.post(f"/api/v1/tasks/{task_id}/retry")
    assert response.status_code == 202, response.text
    task = client.get(f"/api/v1/tasks/{response.json()['task_id']}").json()
    assert task["status"] == "completed", task
    assert task["reused_units"] == 3


def test_frontend_bundle_is_served_from_repo_not_backend_directory(tmp_path, monkeypatch):
    from backend.app import application
    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>workspace</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ready');", encoding="utf-8")
    monkeypatch.setattr(application, "ROOT", tmp_path / "backend")
    app = create_app(Config(data_dir=tmp_path / "data", database_path=tmp_path / "data" / "test.sqlite3"))
    with TestClient(app) as client:
        assert client.get("/summary").text == "<html>workspace</html>"
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/v1/not-found").status_code == 404


def test_manual_merge_with_third_entity_preserves_previous_split(client):
    book_id = book(client)
    extract(client, book_id)
    data = summaries(client, book_id)
    person = next(row["content"][0] for row in data["summaries"] if row["type"] == "characters")
    ids = person["source_ids"]
    for selected in (ids[:1], ids[1:2]):
        client.post(f"/api/v1/books/{book_id}/entity-resolutions", json={
            "revision": data["revision"], "action": "split", "source_ids": selected,
        }).raise_for_status()
        data = summaries(client, book_id)
    people = next(row["content"] for row in data["summaries"] if row["type"] == "characters")
    assert len(people) == 3
    response = client.post(f"/api/v1/books/{book_id}/entity-resolutions", json={
        "revision": data["revision"], "action": "merge", "source_ids": ids[:1], "other_source_ids": ids[1:2],
    })
    assert response.status_code == 200, response.text
    people = next(row["content"] for row in response.json()["summaries"] if row["type"] == "characters")
    assert sorted(len(p["source_ids"]) for p in people) == [1, 2]
    assert not any(p["needs_review"] for p in people)


def test_both_extraction_facades_use_same_citation_rules(monkeypatch):
    from backend.app.ai import extraction_graph
    chapter = {"id": "c", "book_id": "b", "chapter_no": 1, "title": "章", "content": "林川"}
    monkeypatch.setattr(llm, "chat", model_reply)
    monkeypatch.setattr(extraction_graph, "build_extraction_graph", Mock(side_effect=ImportError()))
    assert llm.extract({}, chapter) == llm._legacy_extract({}, chapter)
    assert llm.extract({}, chapter)["characters"][0]["sources"][0]["chapter_id"] == "c"


def test_explicit_protocol_selects_transport_even_for_ollama_profile(monkeypatch):
    from backend.app.ai.providers import api_types
    transport = Mock(return_value=json.dumps(empty()))
    get_transport = Mock(return_value=transport)
    monkeypatch.setattr(api_types, "get_transport", get_transport)
    settings = {"provider": "ollama", "api_protocol": "openai-responses", "model": "test",
                "base_url": "http://example.invalid/v1", "api_key": "private-key", "headers": {"X-Test": "yes"}}
    assert json.loads(llm.chat(settings, [], json_mode=True)) == empty()
    get_transport.assert_called_once_with("openai-responses")
    assert transport.call_args.kwargs["headers"] == {"X-Test": "yes"}


def test_sdk_rate_limits_share_the_same_retry_budget(monkeypatch):
    class RateLimitError(Exception):
        status_code = 429
    invoke = Mock(side_effect=[RateLimitError(), RateLimitError(), "{}"])
    monkeypatch.setattr(llm, "chat", invoke)
    monkeypatch.setattr("backend.app.ai.extraction_pipeline.time.sleep", lambda _: None)
    assert request_json({}, [], lambda value: value) == {}
    assert invoke.call_count == 3


def test_openai_empty_or_truncated_completion_is_not_treated_as_model_json():
    envelope = {
        "choices": [{
            "index": 0, "finish_reason": "length",
            "message": {"role": "assistant", "content": ""},
        }],
        "usage": {"prompt_tokens": 1091, "completion_tokens": 2048, "total_tokens": 3139},
    }
    with pytest.raises(ModelResponseError) as error:
        extract_openai_content(envelope)
    message = str(error.value)
    assert "finish_reason=length" in message
    assert "usage=" in message
    assert "最大输出 token" in message


def test_openai_content_reads_supported_text_shapes_only():
    assert extract_openai_content({"choices": [{"message": {"content": "{\"characters\": []}"}}]}) == '{"characters": []}'
    assert extract_openai_content({"message": {"content": "OK"}}) == "OK"
    assert extract_openai_content({"output": [{"content": [{"text": "A"}, {"text": "B"}]}]}) == "AB"


def test_api_envelope_is_rejected_without_repair(monkeypatch):
    invoke = Mock(return_value=json.dumps({
        "choices": [{"index": 0, "finish_reason": "length", "message": {"content": ""}}],
        "usage": {"total_tokens": 3139},
    }))
    monkeypatch.setattr(llm, "chat", invoke)
    with pytest.raises(RuntimeError) as error:
        request_json({}, [], lambda value: validate_extraction(value, []))
    assert "接口响应元数据" in str(error.value)
    assert invoke.call_count == 1
    assert invoke.call_args.args[0]["max_retries"] == 0


def test_legacy_summary_evidence_can_open_unambiguous_chapter_without_invented_quote(client):
    book_id = book(client)
    db = client.app.state.db
    chapter = db.one("SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_no", (book_id,))
    db.execute("INSERT INTO extractions VALUES(?,?,?,?,?,?)",
               ("old-extraction", book_id, chapter["id"], json.dumps(empty()), "old", "now"))
    content = [{"name": "林川", "evidence": [{"name": "林川", "chapter": chapter["title"], "identity": "医师"}]}]
    db.execute("INSERT INTO summaries VALUES(?,?,?,?,?,?)",
               ("old-summary", book_id, "characters", json.dumps(content), "now", "now"))
    evidence = summaries(client, book_id)["summaries"][0]["content"][0]["evidence"][0]
    assert evidence["chapter_id"] == chapter["id"]
    assert not evidence.get("sources")
