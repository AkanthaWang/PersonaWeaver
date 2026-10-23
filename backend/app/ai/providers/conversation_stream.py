"""Cancellable, asynchronous conversation transports; extraction stays synchronous."""

import json
import uuid

import httpx

from . import api_types as api
from .schemas import normalize_api_type


def capability(settings):
    protocol = normalize_api_type(settings.get("api_protocol") or settings.get("provider"))
    return {"protocol": protocol, "native_streaming": protocol in {
        "openai-completions", "openai-responses", "ollama",
    }}


def request(settings, messages, json_mode=False):
    protocol = capability(settings)["protocol"]
    model, base = settings["model"], settings["base_url"]
    key = settings.get("api_key") or ""
    headers = api.avatar_headers(key, settings.get("headers"))
    temperature = settings.get("temperature", 0.7)
    maximum = settings.get("max_tokens", 2048)
    sampling = settings.get("sampling_params") or {}
    body = {"model": model, "messages": messages, "temperature": temperature,
            "top_p": settings.get("top_p", 0.9), "max_tokens": maximum}
    url = api.normalize_openai_base_url(base)
    if protocol == "openai-responses":
        url = api.normalize_openai_responses_url(base)
        body = {"model": model, "input": messages, "max_output_tokens": maximum,
                "temperature": temperature, "stream": True}
        if json_mode:
            body["text"] = {"format": {"type": "json_object"}}
    elif protocol == "ollama":
        url = api.join_url(base, "api/chat")
        body = {"model": model, "messages": messages, "stream": True,
                "options": {"temperature": temperature, "top_p": settings.get("top_p", 0.9),
                            "num_predict": maximum, **sampling}}
        if json_mode:
            body["format"] = "json"
    elif protocol == "anthropic-messages":
        url = api.join_url(base, "messages")
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01",
                   "x-api-key": key, **(settings.get("headers") or {})}
        body = {"model": model, "max_tokens": maximum, "temperature": temperature,
                "system": "\n\n".join(m["content"] for m in messages if m["role"] == "system"),
                "messages": [m for m in messages if m["role"] != "system"]}
        if json_mode:
            body["system"] += "\nReturn only a valid JSON object."
    elif protocol == "google-generative-ai":
        url = f"{api.join_url(base, 'models')}/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": key,
                   **(settings.get("headers") or {})}
        body = {"contents": [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages if m["role"] != "system"
        ], "systemInstruction": {"parts": [{"text": "\n\n".join(
            m["content"] for m in messages if m["role"] == "system")}]},
            "generationConfig": {"temperature": temperature, "maxOutputTokens": maximum,
                                 "topP": settings.get("top_p", 0.9), **sampling}}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
    else:
        body["stream"] = protocol != "vivo"
        if protocol == "vivo":
            body["thinking"] = {"type": "disabled"}
        else:
            body["stream_options"] = {"include_usage": True}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
    if protocol not in {"ollama", "google-generative-ai"}:
        body.update(sampling)
    return url, headers, body


async def sse(response):
    data = []
    async for line in response.aiter_lines():
        if line == "":
            if data:
                yield "\n".join(data)
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield "\n".join(data)


async def stream(settings, messages, json_mode=False):
    """Yield text/usage events. EOF without a protocol terminator is a failure."""
    caps = capability(settings)
    protocol = caps["protocol"]
    url, headers, body = request(settings, messages, json_mode)
    timeout = httpx.Timeout(float(settings.get("timeout_seconds") or 60), connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if not caps["native_streaming"]:
            response = await client.post(url, headers=headers, json=body,
                                         params={"request_id": str(uuid.uuid4())} if protocol == "vivo" else None)
            response.raise_for_status()
            result = response.json()
            if protocol == "vivo":
                api.raise_for_vivo_error(result)
            extractor = {"anthropic-messages": api.extract_anthropic_content,
                         "google-generative-ai": api.extract_google_content}.get(protocol, api.extract_openai_content)
            text = extractor(result)
            if not text:
                raise ValueError("模型返回空回复")
            yield {"text": text}
            yield {"usage": result.get("usage") or result.get("usageMetadata") or {}}
            return
        finished = False
        async with client.stream("POST", url, headers=headers, json=body) as response:
            response.raise_for_status()
            if protocol == "ollama":
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get("error"):
                        raise ValueError("模型流返回错误")
                    text = (item.get("message") or {}).get("content") or ""
                    if text:
                        yield {"text": text}
                    if item.get("done"):
                        yield {"usage": {key: item[key] for key in (
                            "prompt_eval_count", "eval_count") if key in item}}
                        finished = True
                        break
            else:
                async for data in sse(response):
                    if data.strip() == "[DONE]":
                        finished = True
                        break
                    item = json.loads(data)
                    if item.get("error") or item.get("type") in {"error", "response.failed", "response.incomplete"}:
                        raise ValueError("模型流未正常完成")
                    if protocol == "openai-responses":
                        if item.get("type") == "response.output_text.delta":
                            yield {"text": item.get("delta", "")}
                        if item.get("type") == "response.completed":
                            yield {"usage": (item.get("response") or {}).get("usage") or {}}
                            finished = True
                            break
                    else:
                        for choice in item.get("choices") or []:
                            if choice.get("index", 0) != 0:
                                continue
                            text = (choice.get("delta") or {}).get("content")
                            if isinstance(text, str) and text:
                                yield {"text": text}
                            if choice.get("finish_reason") is not None:
                                if choice["finish_reason"] not in {"stop"}:
                                    raise ValueError("模型因输出限制或过滤而中断")
                                finished = True
                        if item.get("usage"):
                            yield {"usage": item["usage"]}
            if not finished:
                raise ValueError("上游连接提前断开，回复已中断")


async def complete(settings, messages, json_mode=False):
    text, _ = await complete_result(settings, messages, json_mode)
    return text


async def complete_result(settings, messages, json_mode=False):
    parts, usage = [], {}
    async for event in stream(settings, messages, json_mode):
        parts.append(event.get("text", ""))
        if event.get("usage"):
            usage = event["usage"]
    text = "".join(parts).strip()
    if not text:
        raise ValueError("模型返回空回复")
    return text, usage
