import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.app.ai.providers import retrieval
from backend.app.application import create_app
from backend.app.core.config import Config
from backend.app.domains.retrieval import service as retrieval_service
from backend.app.domains.retrieval import vector
from backend.app.domains.settings import llm
from backend.app.domains.settings.selection import load_function_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONAWEAVER_AGENT_DIR", str(tmp_path / "agent"))
    app = create_app(Config(data_dir=tmp_path, database_path=tmp_path / "test.sqlite3"))
    with TestClient(app) as test_client:
        test_client.get("/api/v1/auth/me").raise_for_status()
        yield test_client


def profile(client, model_type="llm", **overrides):
    response = client.post("/api/v1/settings/models", json={
        "name": f"test-{model_type}", "model": f"test-{model_type}", "model_type": model_type,
        "provider": "remote_api", "provider_name": "Test Provider",
        "base_url": "http://127.0.0.1:9999/v1", "activate": False, **overrides,
    })
    assert response.status_code == 201, response.text
    return response.json()


def verified_profile(client, monkeypatch, model_type="llm", **overrides):
    monkeypatch.setattr(llm, "chat", lambda *args, **kwargs: "OK")
    monkeypatch.setattr(retrieval, "embed", lambda *args: [[1.0, 0.0]])
    monkeypatch.setattr(retrieval, "rerank", lambda *args: [{"index": 0, "score": 1.0}])
    item = profile(client, model_type, **overrides)
    assert client.post(f"/api/v1/settings/models/{item['id']}/test").status_code == 200
    return item


def select(client, **values):
    return client.put("/api/v1/settings/selection", json=values)


def book_with_chapters(client):
    response = client.post("/api/v1/books", params={"filename": "story.txt"},
                           content="第一章 开始\n故事一\n\n第二章 继续\n故事二".encode())
    response.raise_for_status()
    book_id = response.json()["book_id"]
    result = client.post(f"/api/v1/books/{book_id}/parse")
    assert result.status_code == 202
    task = client.get(f"/api/v1/tasks/{result.json()['task_id']}").json()
    assert task["status"] == "completed", task
    return book_id


def test_empty_selection_has_explicit_statuses(client):
    values = client.get("/api/v1/settings/selection").json()
    assert values["reranker_top_k"] == 5
    assert values["statuses"]["extraction"]["status"] == "unconfigured"
    assert values["statuses"]["embedding"]["status"] == "unconfigured"
    assert values["statuses"]["reranker"]["status"] == "disabled"


def test_only_tested_models_of_matching_type_can_be_selected(client, monkeypatch):
    item = profile(client, "embedding")
    assert select(client, embedding_model_id=item["id"]).status_code == 422
    monkeypatch.setattr(retrieval, "embed", lambda *args: [[1.0, 0.0]])
    assert client.post(f"/api/v1/settings/models/{item['id']}/test").status_code == 200
    assert select(client, extraction_model_id=item["id"]).status_code == 422
    assert select(client, embedding_model_id=item["id"]).status_code == 200
    assert select(client, embedding_model_id="deleted-id").status_code == 422
    assert client.get("/api/v1/settings/selection").json()["embedding_model_id"] == item["id"]


def test_selection_persists_and_test_statuses_do_not_include_secrets(client, monkeypatch):
    extract = verified_profile(client, monkeypatch, api_key="private-key")
    embedding = verified_profile(client, monkeypatch, "embedding")
    reranker = verified_profile(client, monkeypatch, "reranker")
    result = select(client, extraction_model_id=extract["id"], embedding_model_id=embedding["id"],
                    reranker_model_id=reranker["id"], reranker_top_k=7)
    assert result.status_code == 200
    values = result.json()
    assert all(item["status"] == "healthy" for item in values["statuses"].values())
    assert "private-key" not in result.text
    assert "api_key" not in json.dumps(values["statuses"])
    client.app.state.db.initialize()
    assert client.get("/api/v1/settings/selection").json() == values
    models = client.get("/api/v1/settings/models").json()["models"]
    assert all(item["test_status"] == "passed" and item["tested_at"] for item in models)
    assert "private-key" not in json.dumps(models)


def test_connection_edit_invalidates_test_but_rename_does_not(client, monkeypatch):
    item = verified_profile(client, monkeypatch, "embedding")
    select(client, embedding_model_id=item["id"]).raise_for_status()
    payload = {**item, "name": "renamed"}
    renamed = client.put(f"/api/v1/settings/models/{item['id']}", json=payload).json()
    assert renamed["test_status"] == "passed"
    changed = client.put(f"/api/v1/settings/models/{item['id']}",
                         json={**payload, "model": "changed-model"}).json()
    assert changed["test_status"] == "untested"
    values = client.get("/api/v1/settings/selection").json()
    assert values["embedding_model_id"] == item["id"]
    assert values["statuses"]["embedding"]["status"] == "untested"


def test_failed_retest_removes_model_availability(client, monkeypatch):
    item = verified_profile(client, monkeypatch, "embedding")
    select(client, embedding_model_id=item["id"]).raise_for_status()
    monkeypatch.setattr(retrieval, "embed", Mock(side_effect=ValueError("invalid embeddings")))
    assert client.post(f"/api/v1/settings/models/{item['id']}/test").status_code == 502
    values = client.get("/api/v1/settings/selection").json()
    assert values["statuses"]["embedding"]["status"] == "failed"
    assert select(client, embedding_model_id=item["id"]).status_code == 422


def test_concurrent_configuration_edit_cannot_mark_new_settings_as_tested(client, monkeypatch):
    item = profile(client)
    def change_during_test(*args, **kwargs):
        client.app.state.db.execute("UPDATE model_profiles SET updated_at='changed' WHERE id=?", (item["id"],))
        return "OK"
    monkeypatch.setattr(llm, "chat", change_during_test)
    assert client.post(f"/api/v1/settings/models/{item['id']}/test").status_code == 409
    assert client.get("/api/v1/settings/models").json()["models"][0]["test_status"] == "untested"


def test_deleted_bindings_remain_visible_and_runtime_reports_rebinding(client, monkeypatch, caplog):
    item = verified_profile(client, monkeypatch)
    select(client, extraction_model_id=item["id"]).raise_for_status()
    assert client.delete(f"/api/v1/settings/models/{item['id']}").status_code == 200
    values = client.get("/api/v1/settings/selection").json()
    assert values["extraction_model_id"] == item["id"]
    assert values["statuses"]["extraction"]["status"] == "missing"
    book_id = book_with_chapters(client)
    result = client.post("/api/v1/extract", json={"book_id": book_id})
    assert result.status_code == 422
    assert "模型选用" in result.json()["detail"]
    assert "重新绑定" in caplog.text


def test_extraction_uses_its_binding_not_active_chat_model(client, monkeypatch):
    active = profile(client, name="chat", model="chat", activate=True)
    extract = verified_profile(client, monkeypatch, name="extract", model="extract")
    select(client, extraction_model_id=extract["id"]).raise_for_status()
    user_id = client.get("/api/v1/auth/me").json()["user_id"]
    assert load_function_settings(client.app.state.db, user_id, "extraction")["model"] == "extract"
    assert client.get("/api/v1/settings/model").json()["model"] == active["model"]


def test_embedding_and_reranker_never_activate_for_chat(client):
    active = profile(client, activate=True)
    embedding = profile(client, "embedding", activate=True)
    reranker = profile(client, "reranker", activate=True)
    assert not embedding["active"] and not reranker["active"]
    assert client.get("/api/v1/settings/model").json()["model"] == active["model"]
    assert client.post(f"/api/v1/settings/models/{embedding['id']}/activate").status_code == 422
    result = client.post("/api/v1/conversations", json={"title": "test", "profile_id": reranker["id"]})
    assert result.status_code == 422


@pytest.mark.parametrize("top_k", [0, 101, -1, 1.5, None])
def test_invalid_top_k_is_rejected(client, top_k):
    assert select(client, reranker_top_k=top_k).status_code == 422


def test_top_k_is_retained_when_reranker_disabled(client, monkeypatch):
    reranker = verified_profile(client, monkeypatch, "reranker")
    assert select(client, reranker_model_id=reranker["id"], reranker_top_k=8).status_code == 200
    assert select(client, reranker_model_id=None, reranker_top_k=8).json()["reranker_top_k"] == 8


def test_source_profile_inherits_only_owned_matching_provider_key(client):
    source = profile(client, api_key="provider-secret")
    child = profile(client, "embedding", source_profile_id=source["id"])
    assert child["has_api_key"]
    stored = client.app.state.db.one("SELECT api_key FROM model_profiles WHERE id=?", (child["id"],))
    assert stored["api_key"] == "provider-secret"
    result = client.post("/api/v1/settings/models", json={
        "name": "unsafe", "model": "unsafe", "provider": "remote_api",
        "source_profile_id": source["id"], "base_url": "https://other.example/v1",
    })
    assert result.status_code == 422


def test_vector_retrieval_skips_optional_rerank_and_reuses_cache(client, monkeypatch):
    embedding = verified_profile(client, monkeypatch, "embedding")
    select(client, embedding_model_id=embedding["id"]).raise_for_status()
    book_id = book_with_chapters(client)
    embed_mock = Mock(side_effect=lambda settings, texts: [[1.0, 0.5] for _ in texts])
    rerank_mock = Mock(side_effect=AssertionError("rerank must be disabled"))
    monkeypatch.setattr(vector, "embed", embed_mock)
    monkeypatch.setattr(retrieval_service, "rerank", rerank_mock)
    query = {"query": "故事", "book_id": book_id, "limit": 10}
    result = client.post("/api/v1/search", json=query)
    assert result.status_code == 200, result.text
    assert len(result.json()["items"]) == 2
    assert embed_mock.call_count == 3
    assert client.post("/api/v1/search", json=query).status_code == 200
    assert embed_mock.call_count == 4
    rerank_mock.assert_not_called()


def test_reranker_uses_independent_top_k_and_deleted_embedding_fails(client, monkeypatch):
    embedding = verified_profile(client, monkeypatch, "embedding")
    reranker = verified_profile(client, monkeypatch, "reranker")
    select(client, embedding_model_id=embedding["id"], reranker_model_id=reranker["id"],
           reranker_top_k=1).raise_for_status()
    book_id = book_with_chapters(client)
    monkeypatch.setattr(vector, "embed", lambda settings, texts: [[1.0, 0.5] for _ in texts])
    rerank_mock = Mock(return_value=[{"index": 1, "score": 0.95}])
    monkeypatch.setattr(retrieval_service, "rerank", rerank_mock)
    query = {"query": "故事", "book_id": book_id, "limit": 10}
    result = client.post("/api/v1/search", json=query)
    assert result.status_code == 200, result.text
    assert len(result.json()["items"]) == 1
    assert result.json()["items"][0]["score"] == 0.95
    assert rerank_mock.call_args.args[-1] == 1
    assert client.delete(f"/api/v1/settings/models/{embedding['id']}").status_code == 200
    result = client.post("/api/v1/search", json=query)
    assert result.status_code == 422
    assert "模型选用" in result.json()["detail"]


def test_switching_embeddings_keeps_indexes_separate(client, monkeypatch):
    first = verified_profile(client, monkeypatch, "embedding")
    second = verified_profile(client, monkeypatch, "embedding", name="second", model="second")
    book_id = book_with_chapters(client)
    monkeypatch.setattr(vector, "embed",
                        lambda settings, texts: [[1.0] * (2 if settings["model"] == first["model"] else 3) for _ in texts])
    for item in (first, second):
        select(client, embedding_model_id=item["id"]).raise_for_status()
        result = client.post("/api/v1/search", json={"query": "test", "book_id": book_id})
        assert result.status_code == 200, result.text
    cached = client.app.state.db.all("SELECT model_key,vector_json FROM chapter_vectors")
    assert len({item["model_key"] for item in cached}) == 2
    assert {len(json.loads(item["vector_json"])) for item in cached} == {2, 3}
