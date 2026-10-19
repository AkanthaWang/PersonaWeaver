"""Shared, provider-neutral extraction and citation validation."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Callable, Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.ai.prompts.extraction import (
    EXTRACTION_LOOKUP_SUFFIX,
    EXTRACTION_REPAIR_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
)

KINDS = ("characters", "items", "storyline_events", "world_locations")
# Changing this version intentionally invalidates old extraction checkpoints.
# The next run must apply normalization and the current key-fact rules.
VERSION = "evidence-v4-normalized-key-facts"
API_ENVELOPE_KEYS = {"choices", "output", "usage", "total_tokens", "error"}


def looks_like_api_envelope(value) -> bool:
    return (
        isinstance(value, dict)
        and bool(API_ENVELOPE_KEYS & value.keys())
        and not any(kind in value for kind in KINDS)
    )


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def model_fingerprint(settings) -> str:
    # Secrets are neither persisted nor included in fingerprints.
    return digest({key: settings.get(key) for key in (
        "provider", "api_protocol", "base_url", "model", "max_tokens", "top_p",
    )} | {"version": VERSION, "temperature": 0.1})


def transient_error(exc):
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return status in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, (requests.Timeout, requests.ConnectionError)) or type(exc).__name__ in {
        "APITimeoutError", "APIConnectionError", "ConnectTimeout", "ReadTimeout",
        "ConnectError", "RemoteProtocolError",
    }


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Quote(StrictModel):
    segment_id: str
    quote: str = Field(min_length=1, max_length=1000)
    occurrence: int = Field(default=1, ge=1)


class Relationship(StrictModel):
    target_name: str = Field(min_length=1)
    relation: str = Field(min_length=1)


class Entry(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str = ""
    description: str = ""
    identity: str = ""
    appearance: str = ""
    personality: str = ""
    aliases: list[str] = Field(default_factory=list)
    behavior: list[str] = Field(default_factory=list)
    speech: list[str] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    key_events: list[str] = Field(default_factory=list)
    state_changes: list[str] = Field(default_factory=list)
    involved_characters: list[str] = Field(default_factory=list)
    related_characters: list[str] = Field(default_factory=list)
    time: str = ""
    owner: str = ""
    significance: str = ""
    type: str = ""
    evidence: list[Quote] = Field(min_length=1)


class Question(StrictModel):
    kind: Literal["identity", "alias", "reference"]
    query: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=200)


class Extraction(StrictModel):
    characters: list[Entry]
    items: list[Entry]
    storyline_events: list[Entry]
    world_locations: list[Entry]
    questions: list[Question] = Field(default_factory=list, max_length=20)


class Paragraph(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    fact_ids: list[str] = Field(min_length=1)


class Synthesis(StrictModel):
    paragraphs: list[Paragraph]


KEY_FIELDS = {
    "characters": ("summary", "description", "identity", "appearance", "personality", "aliases",
                   "behavior", "speech", "relationships", "key_events", "state_changes"),
    "items": ("summary", "description", "owner", "significance", "type",
              "related_characters"),
    "storyline_events": ("summary", "description", "time", "involved_characters",
                         "state_changes", "significance"),
    "world_locations": ("summary", "description", "owner", "significance",
                        "related_characters"),
}


def segments(chapter: dict, limit=6000, overlap=300) -> list[dict]:
    text, start, output = chapter["content"], 0, []
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + limit // 2, end)
            if boundary >= 0:
                end = boundary + 1
        output.append({
            "segment_id": f"{chapter['id']}:{start}:{end}",
            "chapter_id": chapter["id"], "book_id": chapter["book_id"],
            "chapter_no": chapter["chapter_no"], "chapter_title": chapter["title"],
            "start": start, "end": end, "text": text[start:end],
        })
        if end == len(text):
            break
        start = max(start + 1, end - min(overlap, (end - start) // 2))
    return output


def validate_extraction(value, inputs: list[dict]) -> dict:
    parsed = Extraction.model_validate(value).model_dump()
    by_id = {item["segment_id"]: item for item in inputs}
    output = {key: [] for key in KINDS}
    for kind in KINDS:
        for entry in parsed[kind]:
            # Normalize factual fields only; quotation whitespace is significant.
            for key, value in entry.items():
                if isinstance(value, str):
                    entry[key] = value.strip()
                elif isinstance(value, list) and key != "evidence":
                    cleaned = []
                    for item in value:
                        item = (item.strip() if isinstance(item, str)
                                else {k: v.strip() for k, v in item.items()})
                        if item and (not isinstance(item, dict) or all(item.values())) and item not in cleaned:
                            cleaned.append(item)
                    entry[key] = cleaned
            if not entry["name"]:
                raise ValueError("资料名称不能为空")
            citations = []
            for evidence in entry.pop("evidence"):
                source = by_id.get(evidence["segment_id"])
                if not source:
                    raise ValueError("引文引用了未提供的原文片段")
                quote, cursor, found = evidence["quote"], 0, -1
                if not quote.strip():
                    raise ValueError("引文不能仅为空白字符")
                for _ in range(evidence["occurrence"]):
                    found = source["text"].find(quote, cursor)
                    if found < 0:
                        raise ValueError("引文不能精确匹配原文，请逐字引用并检查 occurrence")
                    cursor = found + len(quote)
                citations.append({
                    "book_id": source["book_id"], "chapter_id": source["chapter_id"],
                    "chapter_no": source["chapter_no"], "chapter_title": source["chapter_title"],
                    "start": source["start"] + found, "end": source["start"] + found + len(quote),
                    "quote": quote,
                })
            if not any(entry.get(field) for field in KEY_FIELDS[kind]):
                continue
            entry = {key: value for key, value in entry.items() if value}
            entry["sources"] = sorted({digest(c): c for c in citations}.values(),
                                      key=lambda c: (c["chapter_no"], c["start"], c["end"], c["quote"]))
            entry["fact_id"] = "fact_" + digest([kind, entry])[:32]
            output[kind].append(entry)
    output["questions"] = []
    for question in parsed["questions"]:
        question = {key: value.strip() for key, value in question.items()}
        if not question["query"] or not question["subject"]:
            raise ValueError("待核实问题的查询和对象不能为空")
        if question not in output["questions"]:
            output["questions"].append(question)
    return output


def request_json(settings, messages, validator: Callable, check: Callable = lambda: None,
                 repair_prompt: str = EXTRACTION_REPAIR_PROMPT):
    from backend.app.domains.settings import llm

    messages = list(messages)
    for repair in range(2):
        call_error = None
        for attempt in range(3):
            check()
            try:
                text = llm.chat({**settings, "temperature": 0.1, "max_retries": 0}, messages, json_mode=True)
                check()
                break
            except (ValueError, TypeError) as exc:
                call_error, text = exc, None
                break
            except Exception as exc:
                if attempt == 2 or not transient_error(exc):
                    raise
                time.sleep(0.25 * 2 ** attempt)
        try:
            if call_error:
                raise ValueError(str(call_error))
            if isinstance(text, str):
                cleaned = text.strip()
                if cleaned.startswith("```") and cleaned.endswith("```"):
                    cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
                value = json.loads(cleaned)
            else:
                value = text
            if looks_like_api_envelope(value):
                raise RuntimeError(
                    "模型返回了接口响应元数据（choices/usage）而不是提取 JSON；"
                    "通常是模型输出为空或被 max_tokens 截断。请在模型设置中提高最大输出 token，"
                    "或关闭推理/更换模型后重试。"
                )
            return validator(value)
        except (ValueError, ValidationError, TypeError, KeyError) as exc:
            if repair:
                raise ValueError(f"模型结构或原文依据校验失败：{str(exc)[:400]}") from exc
            messages.append({"role": "user", "content":
                             repair_prompt.format(error=str(exc)[:800])})


def extract_inputs(settings, inputs, check=lambda: None, questions=None):
    prompt = EXTRACTION_SYSTEM_PROMPT
    if questions:
        prompt += EXTRACTION_LOOKUP_SUFFIX
    return request_json(settings, [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps({"segments": inputs, "questions": questions or []}, ensure_ascii=False)},
    ], lambda value: validate_extraction(value, inputs), check)


def combine(payloads):
    result = {key: [] for key in KINDS}
    result["questions"] = []
    seen = set()
    for payload in payloads:
        for question in payload.get("questions", []):
            if question not in result["questions"]:
                result["questions"].append(question)
        for kind in KINDS:
            for entry in payload[kind]:
                signature = digest([kind, {k: v for k, v in entry.items() if k != "fact_id"}])
                if signature not in seen:
                    seen.add(signature)
                    result[kind].append(entry)
    result["_meta"] = {"version": VERSION}
    return result
