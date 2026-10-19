from unittest.mock import Mock

import pytest

from backend.app.ai.providers import retrieval


SETTINGS = {"provider": "remote_api", "base_url": "http://localhost:9999/v1",
            "model": "test", "api_key": "secret", "timeout_seconds": 30,
            "headers": {"X-Provider": "test"}}


def response(monkeypatch, payload):
    mock = Mock()
    mock.json.return_value = payload
    post = Mock(return_value=mock)
    monkeypatch.setattr(retrieval.requests, "post", post)
    return post


def test_openai_embeddings_order_and_request_headers(monkeypatch):
    post = response(monkeypatch, {"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]})
    assert retrieval.embed(SETTINGS, ["one", "two"]) == [[1, 0], [0, 1]]
    assert post.call_args.args == ("http://localhost:9999/v1/embeddings",)
    assert post.call_args.kwargs["headers"] == {"X-Provider": "test", "Authorization": "Bearer secret"}
    assert post.call_args.kwargs["json"] == {"model": "test", "input": ["one", "two"]}


def test_ollama_embeddings_use_native_endpoint(monkeypatch):
    post = response(monkeypatch, {"embeddings": [[1.0, 0.5]]})
    assert retrieval.embed({**SETTINGS, "provider": "ollama", "base_url": "http://localhost:11434"}, ["one"]) == [[1.0, 0.5]]
    assert post.call_args.args[0] == "http://localhost:11434/api/embed"


@pytest.mark.parametrize("data", [
    None, [], [{"index": 0, "embedding": []}], [{"index": 0, "embedding": [0, 0]}],
    [{"index": 0, "embedding": [float("nan"), 1]}], [{"index": 0, "embedding": ["bad", 1]}],
    [{"index": 1, "embedding": [1, 1]}],
])
def test_invalid_embeddings_are_rejected(monkeypatch, data):
    response(monkeypatch, {"data": data})
    with pytest.raises(ValueError):
        retrieval.embed(SETTINGS, ["one"])


def test_reranking_validates_and_sorts_results(monkeypatch):
    post = response(monkeypatch, {"results": [{"index": 0, "relevance_score": 0.3}, {"index": 1, "relevance_score": 0.9}]})
    assert retrieval.rerank(SETTINGS, "query", ["a", "b"], 1) == [{"index": 1, "score": 0.9}]
    assert post.call_args.args[0] == "http://localhost:9999/v1/rerank"
    assert post.call_args.kwargs["json"]["top_n"] == 1


@pytest.mark.parametrize("rows", [
    [], [{"index": -1, "relevance_score": 0.8}], [{"index": 0, "relevance_score": float("nan")}],
    [{"index": 0, "relevance_score": 0.8}, {"index": 0, "relevance_score": 0.5}],
])
def test_invalid_rerank_results_are_rejected(monkeypatch, rows):
    response(monkeypatch, {"results": rows})
    with pytest.raises(ValueError):
        retrieval.rerank(SETTINGS, "query", ["one"], 1)
