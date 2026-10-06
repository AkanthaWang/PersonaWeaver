from backend.llm_dispatch.llm_client import call_llm_json, call_llm_text


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_call_llm_json_remote_api_builds_openai_request(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"name":"石野"}'
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("backend.llm_dispatch.llm_client.requests.post", fake_post)

    result = call_llm_json(
        text_or_documents="章节正文",
        prompt_description="提取角色信息",
        model="ecnu-max",
        base_url="https://chat.ecnu.edu.cn/open/api/v1/chat/completions",
        temperature=0.2,
        timeout_seconds=30,
        provider="remote_api",
        api_key="test-token",
    )

    assert result == {"name": "石野"}
    assert captured["url"] == "https://chat.ecnu.edu.cn/open/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["json"]["model"] == "ecnu-max"
    assert captured["json"]["stream"] is False
    assert captured["json"]["temperature"] == 0.2
    assert captured["timeout"] == 30


def test_call_llm_text_remote_api_builds_openai_request(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "# 石野\n\n## 简介\n主角"
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("backend.llm_dispatch.llm_client.requests.post", fake_post)

    result = call_llm_text(
        text_or_documents="章节正文",
        prompt_description="生成 Markdown 角色卡",
        model="ecnu-max",
        base_url="https://chat.ecnu.edu.cn/open/api/v1/chat/completions",
        temperature=0.2,
        timeout_seconds=30,
        provider="remote_api",
        api_key="test-token",
    )

    assert result.startswith("# 石野")
    assert captured["url"] == "https://chat.ecnu.edu.cn/open/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-token"
    assert captured["json"]["model"] == "ecnu-max"
    assert captured["json"]["stream"] is False
    assert captured["json"]["temperature"] == 0.2
    assert captured["timeout"] == 30


def test_call_llm_json_vivo_builds_request_with_request_id(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"characters":[{"name":"林澈"}]}'
                        }
                    }
                ],
                "usage": {"total_tokens": 12},
            }
        )

    monkeypatch.setattr("backend.llm_dispatch.llm_client.requests.post", fake_post)

    result = call_llm_json(
        text_or_documents="林澈发现手札。",
        prompt_description="提取角色信息",
        model="Volc-DeepSeek-V3.2",
        base_url="https://api-ai.vivo.com.cn/v1/chat/completions",
        temperature=0.1,
        timeout_seconds=30,
        provider="vivo",
        api_key="vivo-token",
        request_id="rid-test",
    )

    assert result == {"characters": [{"name": "林澈"}]}
    assert captured["url"] == "https://api-ai.vivo.com.cn/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer vivo-token"
    assert captured["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert captured["params"] == {"request_id": "rid-test"}
    assert captured["json"]["model"] == "Volc-DeepSeek-V3.2"
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["json"]["stream"] is False


def test_call_llm_text_vivo_raises_for_usage_limit(monkeypatch):
    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        return _FakeResponse({"code": 2003, "msg": "today usage limit", "data": None})

    monkeypatch.setattr("backend.llm_dispatch.llm_client.requests.post", fake_post)

    try:
        call_llm_text(
            text_or_documents="章节正文",
            prompt_description="生成摘要",
            model="Volc-DeepSeek-V3.2",
            base_url="https://api-ai.vivo.com.cn/v1/chat/completions",
            provider="vivo",
            api_key="vivo-token",
        )
    except RuntimeError as exc:
        assert "today usage limit" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
