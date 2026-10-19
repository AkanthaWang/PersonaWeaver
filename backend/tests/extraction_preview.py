"""Isolated browser fixture. Never imported by the production application."""

import json
import os
import time
from pathlib import Path

from backend.app.application import create_app
from backend.app.ai.providers.api_types import ModelResponseError
from backend.app.core.config import Config
from backend.app.domains.settings import llm

directory = os.environ.get("PERSONAWEAVER_DATA_DIR", "")
if not directory or Path(directory).resolve() == Path("db").resolve():
    raise RuntimeError("Browser fixture requires an explicitly isolated data directory")

failed_once = False
partial_failed_once = False


def fixture_chat(settings, messages, **kwargs):
    global failed_once, partial_failed_once
    try:
        prompt = json.loads(messages[1]["content"])
    except (ValueError, IndexError, TypeError):
        return "OK"
    time.sleep(0.15)
    if isinstance(prompt, dict) and "available_tools" in prompt:
        return json.dumps({"tool": "skip"})
    if isinstance(prompt, list):
        kind = prompt[0].get("kind", "characters") if prompt else "characters"
        text = {
            "characters": "林川以医师身份行医，各章经历与关系按原文保留。",
            "items": "药箱随林川来到青石镇，第二章交给阿遥，第三章由林川收起。",
            "world_locations": "青石镇是林川与阿遥停留行医的地点。",
        }.get(kind, "资料按章节整合。")
        return json.dumps({"paragraphs": [{
            "text": text,
            "fact_ids": [fact["fact_id"] for fact in prompt],
        }]}, ensure_ascii=False)
    output = {key: [] for key in ("characters", "items", "storyline_events", "world_locations")}
    for part in prompt["segments"]:
        if "局部失败" in part["text"] and not partial_failed_once:
            partial_failed_once = True
            raise ModelResponseError("浏览器验收：当前分段输出为空")
        if "失败一次" in part["text"] and not failed_once:
            failed_once = True
            raise RuntimeError("浏览器验收：模拟临时失败，检查点已保留")
        quote = next((line for line in part["text"].splitlines() if "林川" in line), None)
        if quote:
            evidence = [{"segment_id": part["segment_id"], "quote": quote}]
            output["characters"].append({
                "name": "林川", "identity": "医师", "description": quote,
                "relationships": [{"target_name": "阿遥", "relation": "同行者"}],
                "state_changes": [quote], "evidence": evidence,
            })
            output["storyline_events"].append({
                "name": f"第{part['chapter_no']}章行程", "description": quote,
                "involved_characters": ["林川"], "evidence": evidence,
            })
            output["items"].append({
                "name": "药箱", "owner": "阿遥" if part["chapter_no"] == 2 else "林川",
                "description": "随身药箱", "evidence": evidence,
            })
            output["world_locations"].append({
                "name": "青石镇", "type": "地点", "description": "行医地点", "evidence": evidence,
            })
    return json.dumps(output, ensure_ascii=False)


llm.chat = fixture_chat
app = create_app(Config(data_dir=Path(directory), database_path=Path(directory) / "preview.sqlite3"))
