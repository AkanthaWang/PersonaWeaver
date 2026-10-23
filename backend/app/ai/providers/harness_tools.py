"""Native function-call planning with explicit, narrowly scoped JSON fallback."""

import json

import httpx

from . import conversation_stream as transport
from .api_types import parse_json_payload
from backend.app.ai.harness.tools import Decision
from backend.app.ai.harness.storage import encode


def native_protocol(settings):
    protocol = transport.capability(settings)["protocol"]
    return protocol if protocol in {"openai-completions", "openai-responses", "ollama"} else None


async def decide(settings, messages, tools, mode=None, *, probe=False):
    protocol = native_protocol(settings)
    if probe and not protocol:
        raise ValueError("当前协议没有经过支持的原生工具路径，继续使用严格 JSON")
    if protocol and mode != "json" and (probe or settings.get("tool_support") == "native"):
        url, headers, body = transport.request(settings, messages)
        body.pop("stream_options", None)
        body.pop("text", None)
        body["stream"] = False
        body["tools"] = ([{"type": "function", **t["function"]} for t in tools]
                         if protocol == "openai-responses" else tools)
        if protocol != "ollama":
            body["tool_choice"] = "auto"
        timeout = httpx.Timeout(float(settings.get("timeout_seconds") or 60), connect=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
            # Only an explicit unsupported-tools response permits a second call.
            error = response.text.lower()
            unsupported = (
                response.status_code in {400, 422}
                and any(term in error for term in ("tool", "function"))
                and any(term in error for term in (
                    "not supported", "does not support", "unsupported", "not available", "unknown parameter"))
            )
            if unsupported and probe:
                raise ValueError("模型明确不支持原生工具调用，继续使用严格 JSON")
            if not unsupported:
                response.raise_for_status()
                result = response.json()
                calls = []
                if protocol == "openai-responses":
                    if result.get("status") not in {None, "completed"} or result.get("error"):
                        raise ValueError("工具规划响应未完整结束")
                    for item in result.get("output") or []:
                        if item.get("type") == "function_call":
                            calls.append({"name": item["name"], "arguments": json.loads(item["arguments"])})
                else:
                    if protocol == "ollama":
                        if not result.get("done") or result.get("error"):
                            raise ValueError("工具规划响应未完整结束")
                        message = result.get("message")
                    else:
                        choices = result.get("choices") or []
                        if not choices or choices[0].get("finish_reason") not in {"stop", "tool_calls"}:
                            raise ValueError("工具规划响应被截断")
                        message = choices[0].get("message")
                    if not isinstance(message, dict):
                        raise ValueError("工具规划响应无效")
                    for call in message.get("tool_calls") or []:
                        fn = call.get("function") or {}
                        arguments = fn.get("arguments")
                        calls.append({"name": fn.get("name"), "arguments":
                                      json.loads(arguments) if isinstance(arguments, str) else arguments})
                decision = Decision.model_validate({"calls": calls})
                return decision.model_dump(), "native", result.get("usage") or {
                    k: result[k] for k in ("prompt_eval_count", "eval_count") if k in result}
    prompt = [*messages, {"role": "system", "content": "仅返回 JSON 动作。\n工具定义：" + encode(tools)}]
    parts, usage = [], {}
    async for event in transport.stream(settings, prompt, json_mode=True):
        if event.get("text"):
            parts.append(event["text"])
        if event.get("usage"):
            usage = event["usage"]
    return Decision.model_validate(parse_json_payload("".join(parts))).model_dump(), "json", usage
