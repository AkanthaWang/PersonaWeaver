"""Protocol contracts use HTTP substitutes, never external models."""

import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from backend.app.ai.harness.tools import definitions
from backend.app.ai.providers import harness_tools


def settings(protocol):
    return {"api_protocol": protocol, "provider": "openai", "model": "stub",
            "base_url": "http://model.invalid/v1", "api_key": "not-persisted", "max_tokens": 128,
            "tool_support": "native"}


def http_stub(monkeypatch, response):
    requests = []
    original = httpx.AsyncClient

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(response[0], json=response[1], request=request)

    monkeypatch.setattr(harness_tools.httpx, "AsyncClient",
                        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    return requests


@pytest.mark.parametrize("protocol", ["openai-completions", "openai-responses", "ollama"])
def test_native_function_calls_share_validated_schema(monkeypatch, protocol):
    fn = {"name": "search_knowledge", "arguments": '{"query":"林默"}'}
    body = {
        "openai-completions": {"choices": [{"finish_reason": "tool_calls", "message": {
            "tool_calls": [{"type": "function", "function": fn}]}}]},
        "openai-responses": {"status": "completed", "output": [{"type": "function_call", **fn}]},
        "ollama": {"done": True, "message": {"tool_calls": [{
            "function": {**fn, "arguments": {"query": "林默"}}}]}},
    }[protocol]
    requests = http_stub(monkeypatch, (200, body))
    decision, mode, _ = asyncio.run(harness_tools.decide(
        settings(protocol), [{"role": "user", "content": "查询"}], definitions()))
    assert mode == "native"
    assert decision == {"calls": [{"name": "search_knowledge", "arguments": {"query": "林默"}}]}
    assert requests[0]["stream"] is False
    assert len(requests[0]["tools"]) == 3
    if protocol == "openai-responses":
        assert requests[0]["tools"][0]["name"] == "search_knowledge"
    else:
        assert requests[0]["tools"][0]["function"]["name"] == "search_knowledge"


def test_only_explicit_unsupported_tools_response_permits_json_fallback(monkeypatch):
    requests = http_stub(monkeypatch, (400, {"error": "This model does not support tools"}))
    calls = []

    async def stream(config, messages, json_mode=False):
        calls.append((messages, json_mode))
        yield {"text": '{"calls":[{"name":"search_knowledge","arguments":{"query":"林默"}}]}'}

    monkeypatch.setattr(harness_tools.transport, "stream", stream)
    result = asyncio.run(harness_tools.decide(settings("ollama"), [], definitions()))
    assert result[1] == "json" and calls[0][1] is True
    asyncio.run(harness_tools.decide(settings("ollama"), [], definitions(), mode="json"))
    assert len(requests) == 1 and len(calls) == 2


@pytest.mark.parametrize("status,error", [
    (401, "unsupported tools"), (503, "tools unavailable"),
    (400, "invalid tool schema"), (422, "model not supported"),
])
def test_auth_transient_and_schema_errors_do_not_retry(monkeypatch, status, error):
    http_stub(monkeypatch, (status, {"error": error}))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(harness_tools.decide(settings("ollama"), [], definitions()))


@pytest.mark.parametrize("content", [
    '{"calls":[{"name":"delete_book","arguments":{}}]}',
    '{"calls":[],"extra":"ignored"}', '{"calls":"bad"}', 'not json',
])
def test_json_fallback_is_strict(monkeypatch, content):
    async def stream(*args, **kwargs):
        yield {"text": content}
    monkeypatch.setattr(harness_tools.transport, "stream", stream)
    with pytest.raises((ValueError, ValidationError)):
        asyncio.run(harness_tools.decide(settings("ollama"), [], definitions(), mode="json"))


@pytest.mark.parametrize("protocol,body", [
    ("ollama", {"done": False, "message": {"tool_calls": []}}),
    ("openai-completions", {"choices": [{"finish_reason": "length", "message": {}}]}),
    ("openai-responses", {"status": "incomplete", "output": []}),
])
def test_incomplete_native_plans_fail_closed(monkeypatch, protocol, body):
    http_stub(monkeypatch, (200, body))
    with pytest.raises(ValueError):
        asyncio.run(harness_tools.decide(settings(protocol), [], definitions()))


def test_unverified_models_never_attempt_native_calls(monkeypatch):
    requests = http_stub(monkeypatch, (500, {"error": "must not be contacted"}))

    async def stream(*args, **kwargs):
        yield {"text": '{"calls":[]}'}

    monkeypatch.setattr(harness_tools.transport, "stream", stream)
    config = {**settings("ollama"), "tool_support": "unverified"}
    assert asyncio.run(harness_tools.decide(config, [], definitions()))[1] == "json"
    assert requests == []


def test_explicit_probe_does_not_pay_for_json_retry(monkeypatch):
    requests = http_stub(monkeypatch, (400, {"error": "tools are not supported"}))
    with pytest.raises(ValueError, match="不支持"):
        asyncio.run(harness_tools.decide(settings("ollama"), [], definitions(), probe=True))
    assert len(requests) == 1
