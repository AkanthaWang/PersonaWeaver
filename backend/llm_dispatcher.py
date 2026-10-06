from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from backend.llm_chapter_extraction.extractor_client import call_ollama_json
from backend.llm_dispatch.llm_client import call_llm_text
from backend.source_preprocess import process_source_file


ROOT_DIR = Path(__file__).resolve().parents[1]
ProgressCallback = Callable[[dict[str, Any]], None]


def _load_dotenv_simple(env_path: Path | None = None) -> None:
    """加载 .env 文件到 os.environ，不依赖 python-dotenv。"""
    target = env_path or ROOT_DIR / ".env"
    if not target.exists():
        return
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in os.environ:
            os.environ[key] = value


# 模块加载时自动导入 .env，确保 CLI 独立运行时也能读取环境变量
_load_dotenv_simple()


def _emit_progress(progress_callback: ProgressCallback | None, payload: dict[str, Any]) -> None:
    if progress_callback is None:
        return
    progress_callback(payload)


def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parent / "config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _safe_folder_name(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name.strip())
    return safe or "source_local"


def _resolve_prompt_group(config: dict, prompt_group: str) -> dict[str, str]:
    prompts = config.get(prompt_group)
    if isinstance(prompts, dict):
        return prompts

    if prompt_group == "chapter_prompts":
        legacy = config.get("prompts")
        if isinstance(legacy, dict):
            return legacy

    return {}


def _env_or_config(cfg: dict[str, Any], env_key_field: str, value_field: str, default: str = "") -> str:
    """Resolve config value with an optional environment-variable indirection."""
    env_name = str(cfg.get(env_key_field) or "").strip()
    if env_name:
        env_value = os.getenv(env_name)
        if env_value:
            return env_value
    value = cfg.get(value_field, default)
    return str(value or default)



def _resolve_llm_config(
    config: dict,
    *,
    provider: str | None = None,
    model: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    llm_cfg = dict(config.get("llm", {}))
    resolved_provider = provider or llm_cfg.get("provider", "ollama")

    local_cfg = llm_cfg.get("ollama", {}) if isinstance(llm_cfg.get("ollama"), dict) else {}
    remote_cfg = llm_cfg.get("remote_api", {}) if isinstance(llm_cfg.get("remote_api"), dict) else {}
    vivo_cfg = llm_cfg.get("vivo", {}) if isinstance(llm_cfg.get("vivo"), dict) else {}
    glm_cfg = llm_cfg.get("glm", {}) if isinstance(llm_cfg.get("glm"), dict) else {}

    if resolved_provider in {"vivo", "vivo_aigc"}:
        merged_cfg = {
            "base_url": _env_or_config(vivo_cfg, "base_url_env", "base_url", "https://api-ai.vivo.com.cn/v1/chat/completions"),
            "api_key": _env_or_config(vivo_cfg, "api_key_env", "api_key", llm_cfg.get("api_key", "")),
            "app_id": _env_or_config(vivo_cfg, "app_id_env", "app_id", ""),
            "model": _env_or_config(vivo_cfg, "model_name_env", "model_name", vivo_cfg.get("model", llm_cfg.get("model_name", llm_cfg.get("model", "Volc-DeepSeek-V3.2")))),
            "temperature": vivo_cfg.get("temperature", llm_cfg.get("temperature", 0.1)),
            "timeout_seconds": vivo_cfg.get("timeout_seconds", llm_cfg.get("timeout_seconds", 300)),
            "fallback_providers": vivo_cfg.get("fallback_providers", []),
        }
    elif resolved_provider in {"remote_api", "ecnu"}:
        merged_cfg = {
            "base_url": _env_or_config(remote_cfg, "base_url_env", "base_url", llm_cfg.get("base_url", "https://chat.ecnu.edu.cn/open/api/v1/chat/completions")),
            "api_key": _env_or_config(remote_cfg, "api_key_env", "api_key", llm_cfg.get("api_key", "")),
            "model": _env_or_config(remote_cfg, "model_name_env", "model_name", remote_cfg.get("model", llm_cfg.get("model_name", llm_cfg.get("model", "ecnu-max")))),
            "temperature": remote_cfg.get("temperature", llm_cfg.get("temperature", 0.1)),
            "timeout_seconds": remote_cfg.get("timeout_seconds", llm_cfg.get("timeout_seconds", 60)),
        }
    elif resolved_provider in {"glm", "bigmodel"}:
        glm_api_key = _env_or_config(glm_cfg, "api_key_env", "api_key", os.getenv("BIGMODEL_API_KEY", ""))
        merged_cfg = {
            "base_url": _env_or_config(glm_cfg, "base_url_env", "base_url", "https://open.bigmodel.cn/api/paas/v4"),
            "api_key": glm_api_key or llm_cfg.get("api_key", ""),
            "model": _env_or_config(glm_cfg, "model_name_env", "model_name", glm_cfg.get("model", llm_cfg.get("model_name", llm_cfg.get("model", "glm-4.5-air")))),
            "temperature": glm_cfg.get("temperature", llm_cfg.get("temperature", 0.1)),
            "timeout_seconds": glm_cfg.get("timeout_seconds", llm_cfg.get("timeout_seconds", 60)),
        }
    else:
        merged_cfg = {
            "base_url": local_cfg.get("base_url", llm_cfg.get("base_url", "http://localhost:11434")),
            "api_key": local_cfg.get("api_key", llm_cfg.get("api_key", "")),
            "model": local_cfg.get("model", llm_cfg.get("model", "qwen2.5:0.5b")),
            "temperature": local_cfg.get("temperature", llm_cfg.get("temperature", 0.1)),
            "timeout_seconds": local_cfg.get("timeout_seconds", llm_cfg.get("timeout_seconds", 60)),
        }

    if model is not None:
        merged_cfg["model"] = model
    if model_name is not None:
        merged_cfg["model"] = model_name
    if base_url is not None:
        merged_cfg["base_url"] = base_url
    if api_key is not None:
        merged_cfg["api_key"] = api_key
    if temperature is not None:
        merged_cfg["temperature"] = temperature
    if timeout_seconds is not None:
        merged_cfg["timeout_seconds"] = timeout_seconds

    merged_cfg["provider"] = resolved_provider
    merged_cfg["model_name"] = merged_cfg.get("model")
    return merged_cfg


def _remove_empty_fields(value: Any):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            cleaned = _remove_empty_fields(item)
            if cleaned not in (None, "", [], {}, ()):
                out[key] = cleaned
        return out
    if isinstance(value, list):
        out = [_remove_empty_fields(item) for item in value]
        return [item for item in out if item not in (None, "", [], {}, ())]
    return value


def _public_llm_config(llm_cfg: dict[str, Any]) -> dict[str, Any]:
    public_cfg = dict(llm_cfg)
    public_cfg.pop("api_key", None)
    return public_cfg


def _chapter_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"chapter_(\d+)", path.stem)
    if match:
        return int(match.group(1)), path.name
    return 0, path.name


def _load_json_files(input_dir: Path) -> list[tuple[Path, Any]]:
    files = sorted(input_dir.glob("*.json"), key=_chapter_sort_key)
    payloads: list[tuple[Path, Any]] = []
    for file_path in files:
        payloads.append((file_path, json.loads(file_path.read_text(encoding="utf-8"))))
    return payloads


def _write_json_and_md(output_json_path: Path, output_md_path: Path, title: str, payload: dict[str, Any]) -> None:
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md_path.write_text(
        f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n",
        encoding="utf-8",
    )


def _coerce_summary_json_payload(result: Any) -> Any:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("characters", "items", "result", "data"):
            value = result.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict) and key in {"result", "data"}:
                return value
        return result
    return result


def _coerce_summary_list_payload(result: Any, *, dimension: str) -> list[dict[str, Any]]:
    payload = _coerce_summary_json_payload(result)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        value = payload.get(dimension)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if payload:
            return [payload]
    return []


def _entry_name(entry: dict[str, Any], fallback_prefix: str, index: int) -> str:
    for key in ("name", "character_name", "item_name", "title"):
        value = str(entry.get(key) or "").strip()
        if value:
            return value
    return f"{fallback_prefix}_{index:03d}"


def _write_character_summary_files(
    *,
    dimension_dir: Path,
    result: Any,
) -> tuple[Path, list[dict[str, Any]]]:
    character_dir = dimension_dir / "character_json"
    character_dir.mkdir(parents=True, exist_ok=True)

    characters = _coerce_summary_list_payload(result, dimension="characters")
    index_rows: list[dict[str, Any]] = []

    for idx, character in enumerate(characters, start=1):
        name = _entry_name(character, "character", idx)
        safe_name = _safe_folder_name(name)
        character_payload = dict(character)
        character_payload.setdefault("name", name)

        character_path = character_dir / f"{safe_name}.json"
        character_path.write_text(
            json.dumps(character_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        index_rows.append(
            {
                "name": name,
                "summary": str(character_payload.get("summary") or ""),
                "identity": str(character_payload.get("identity") or ""),
                "summary_local_url": character_path.as_posix(),
                "summary_oss_url": "",
            }
        )

    all_characters_path = dimension_dir / "all_characters.json"
    all_characters_path.write_text(
        json.dumps(index_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return all_characters_path, index_rows


def _merge_text_field(target: dict[str, Any], source: dict[str, Any], target_key: str, source_keys: tuple[str, ...]) -> None:
    if target.get(target_key):
        return
    for key in source_keys:
        value = source.get(key)
        if value not in (None, "", [], {}, ()):
            if isinstance(value, list):
                target[target_key] = "；".join(str(item) for item in value if str(item).strip())
            elif isinstance(value, dict):
                target[target_key] = json.dumps(value, ensure_ascii=False)
            else:
                target[target_key] = str(value)
            return


def _collect_dict_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        entries: list[dict[str, Any]] = []
        if any(key in value for key in ("name", "character_name", "item_name", "title")):
            entries.append(value)
        for child in value.values():
            entries.extend(_collect_dict_entries(child))
        return entries
    if isinstance(value, list):
        entries = []
        for child in value:
            entries.extend(_collect_dict_entries(child))
        return entries
    return []


def _fallback_summary_entries(chapter_jsons: list[tuple[Path, Any]], *, dimension: str) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    section_name = "characters" if dimension == "characters" else "items"

    for _file_path, payload in chapter_jsons:
        chapter_payload = payload if isinstance(payload, dict) else {}
        section_value = chapter_payload.get(section_name)
        for entry in _collect_dict_entries(section_value):
            name = _entry_name(entry, "character" if dimension == "characters" else "item", len(merged) + 1)
            target = merged.setdefault(name, {"name": name, "summary": ""})
            if dimension == "characters":
                _merge_text_field(target, entry, "summary", ("summary", "description", "chapter_behavior", "behavior", "actions", "experiences"))
                _merge_text_field(target, entry, "identity", ("identity", "role", "occupation", "social_relation", "relationship"))
                _merge_text_field(target, entry, "appearance", ("appearance", "look", "外貌"))
                _merge_text_field(target, entry, "personality", ("personality", "traits", "psychology", "emotion"))
            else:
                _merge_text_field(target, entry, "summary", ("summary", "description", "本章表现", "appearance", "owner", "所属角色"))

    return list(merged.values())


def _summary_md_from_result(*, title: str, dimension: str, result: Any) -> str:
    if isinstance(result, str):
        body = result.strip()
    else:
        body = json.dumps(result, ensure_ascii=False, indent=2)
    return f"# {title} - {dimension}\n\n{body}\n"


def _format_value_for_markdown(value: Any) -> str:
    if value in (None, "", [], {}, ()):
        return ""
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _card_markdown_from_result(
    *,
    title: str,
    character_name: str,
    dimension: str,
    summary_character: dict[str, Any] | None,
    result: Any,
    field_map: list[tuple[str, list[str]]] | None = None,
) -> str:
    if isinstance(result, str):
        return result.strip().rstrip() + "\n"

    result_dict = result if isinstance(result, dict) else {}
    source_entries: list[str] = [
        f"# {title} - {dimension}",
        "",
        f"## 角色名称",
        character_name,
    ]

    if field_map is None:
        field_map = [
            ("简介", ["intro", "summary", "description"]),
            ("外形特征", ["appearance", "look"]),
            ("性格标签", ["personality", "traits", "tags"]),
            ("关键经历", ["key_events", "experiences", "events"]),
            ("经典台词", ["quotes", "speech", "sayings"]),
            ("与其他角色关系", ["relations", "relationships", "relation"]),
            ("前端展示文案", ["display_text", "teaser", "card_text", "intro_text"]),
        ]

    for label, keys in field_map:
        value = ""
        for key in keys:
            candidate = result_dict.get(key)
            if candidate not in (None, "", [], {}, ()):
                value = _format_value_for_markdown(candidate)
                break
        if not value and summary_character:
            for key in keys:
                candidate = summary_character.get(key)
                if candidate not in (None, "", [], {}, ()):
                    value = _format_value_for_markdown(candidate)
                    break
        source_entries.extend(["", f"## {label}", value or "-"])

    if summary_character:
        source_entries.extend([
            "",
            "## summary.characters 选中条目",
            "```json",
            json.dumps(summary_character, ensure_ascii=False, indent=2),
            "```",
        ])

    if result_dict:
        source_entries.extend([
            "",
            "## 模型原始结构化结果",
            "```json",
            json.dumps(result_dict, ensure_ascii=False, indent=2),
            "```",
        ])

    return "\n".join(source_entries).rstrip() + "\n"


def _normalize_card_markdown_sections(card_field_map: Any) -> list[str]:
    default_sections = [
        "# 角色名称",
        "## 简介",
        "## 形象特征",
        "## 性格特点",
        "## 关键经历",
        "## 经典台词",
        "## 与其他角色关系",
    ]

    if not isinstance(card_field_map, list):
        return default_sections

    sections: list[str] = []
    for item in card_field_map:
        if isinstance(item, str):
            text = item.strip()
            if text:
                sections.append(text)
        elif isinstance(item, (list, tuple)) and item:
            text = str(item[0]).strip()
            if text:
                sections.append(text)

    return sections or default_sections


def _call_dimension_prompt(*, text: str, prompt_description: str, llm_cfg: dict[str, Any]) -> dict:
    parsed = call_ollama_json(
        text_or_documents=text,
        prompt_description=prompt_description,
        model=llm_cfg["model"],
        base_url=llm_cfg["base_url"],
        temperature=llm_cfg.get("temperature", 0.1),
        timeout_seconds=llm_cfg.get("timeout_seconds", 60),
        provider=llm_cfg.get("provider"),
        api_key=llm_cfg.get("api_key"),
        model_name=llm_cfg.get("model_name"),
    )
    return _remove_empty_fields(parsed) if isinstance(parsed, dict) else {}


def _call_dimension_prompt_text(*, text: str, prompt_description: str, llm_cfg: dict[str, Any]) -> str:
    """Call LLM for text/markdown output instead of JSON"""
    result = call_llm_text(
        text_or_documents=text,
        prompt_description=prompt_description,
        model=llm_cfg["model"],
        base_url=llm_cfg["base_url"],
        temperature=llm_cfg.get("temperature", 0.1),
        timeout_seconds=llm_cfg.get("timeout_seconds", 60),
        provider=llm_cfg.get("provider"),
        api_key=llm_cfg.get("api_key"),
    )
    return result


SUMMARY_SECTION_MAP: dict[str, tuple[str, ...]] = {
    "characters": ("chapter_info", "plot", "characters"),
    "items": ("chapter_info", "plot", "items"),
    "storyline_events": ("chapter_info", "plot"),
    "world_locations": ("chapter_info", "plot", "world"),
}


def _select_summary_excerpt(chapter_payload: dict[str, Any], dimension: str) -> dict[str, Any]:
    selected: dict[str, Any] = {}

    chapter_title = chapter_payload.get("chapter_title")
    if chapter_title not in (None, "", [], {}, ()):
        selected["chapter_title"] = chapter_title

    chapter_sections = SUMMARY_SECTION_MAP.get(dimension, tuple())
    for section_name in chapter_sections:
        section_value = chapter_payload.get(section_name)
        cleaned_value = _remove_empty_fields(section_value)
        if cleaned_value not in (None, "", [], {}, ()):
            selected[section_name] = cleaned_value

    return selected


def _compose_summary_context(
    chapter_jsons: list[tuple[Path, Any]],
    *,
    dimension: str,
    prompt_description: str,
) -> str:
    chunks: list[str] = [
        f"【任务维度】{dimension}",
        f"【任务说明】{prompt_description}",
        "【上下文要求】仅依据每章中与当前维度相关的片段进行汇总，不要依赖无关字段。",
    ]

    for file_path, payload in chapter_jsons:
        excerpt = _select_summary_excerpt(payload if isinstance(payload, dict) else {}, dimension)
        if not excerpt:
            continue
        chunks.append(f"【章节文件】{file_path.name}\n{json.dumps(excerpt, ensure_ascii=False, indent=2)}")

    return "\n\n".join(chunks)


def dispatch_chapter_prompts(
    *,
    chapters: list[dict[str, Any]],
    source_file_id: str,
    cache_folder: str,
    enabled_dimensions: list[str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    timeout_seconds: int | None = None,
    max_chars_per_chapter: int | None = 6000,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    config = _load_config()
    prompts = _resolve_prompt_group(config, "chapter_prompts")
    llm_cfg = _resolve_llm_config(
        config,
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )

    dimensions = enabled_dimensions or list(prompts.keys())
    extraction_output_dir = Path(cache_folder) / "extraction_json"
    extraction_output_dir.mkdir(parents=True, exist_ok=True)

    _emit_progress(
        progress_callback,
        {
            "stage": "l2_chapter",
            "event": "chapter_batch_start",
            "total_chapters": len(chapters),
            "total_dimensions": len(dimensions),
            "source_file_id": source_file_id,
        },
    )

    l2_records: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(chapters, start=1):
        chapter_no = int(chapter.get("chapter_no", 0))
        chapter_title = str(chapter.get("chapter_title", ""))
        chapter_text = str(chapter.get("content_text", ""))

        _emit_progress(
            progress_callback,
            {
                "stage": "l2_chapter",
                "event": "chapter_start",
                "chapter_index": chapter_index,
                "chapter_no": chapter_no,
                "chapter_title": chapter_title,
                "total_chapters": len(chapters),
            },
        )

        extraction_json = {"chapter_title": chapter_title}
        for dim_index, dim in enumerate(dimensions, start=1):
            prompt = prompts.get(dim)
            if not prompt:
                continue
            try:
                chapter_input = f"{chapter_title}\n{chapter_text}" if max_chars_per_chapter is None else f"{chapter_title}\n{chapter_text[:max_chars_per_chapter]}"
                cleaned = _call_dimension_prompt(
                    text=chapter_input,
                    prompt_description=prompt,
                    llm_cfg=llm_cfg,
                )
                if cleaned:
                    extraction_json[dim] = cleaned
                _emit_progress(
                    progress_callback,
                    {
                        "stage": "l2_chapter",
                        "event": "chapter_dimension_done",
                        "chapter_index": chapter_index,
                        "chapter_no": chapter_no,
                        "chapter_title": chapter_title,
                        "dimension": dim,
                        "dimension_index": dim_index,
                        "total_dimensions": len(dimensions),
                        "total_chapters": len(chapters),
                    },
                )
            except Exception as exc:
                extraction_json.setdefault("errors", []).append({"dimension": dim, "error": str(exc)})
                _emit_progress(
                    progress_callback,
                    {
                        "stage": "l2_chapter",
                        "event": "chapter_dimension_error",
                        "chapter_index": chapter_index,
                        "chapter_no": chapter_no,
                        "chapter_title": chapter_title,
                        "dimension": dim,
                        "dimension_index": dim_index,
                        "total_dimensions": len(dimensions),
                        "total_chapters": len(chapters),
                        "error": str(exc),
                    },
                )

        extraction_file = extraction_output_dir / f"{source_file_id}_chapter_{chapter_no:04d}.json"
        extraction_file.write_text(json.dumps(extraction_json, ensure_ascii=False, indent=2), encoding="utf-8")
        l2_records.append(
            {
                "chapter_no": chapter_no,
                "chapter_title": chapter_title,
                "extraction_json_url": extraction_file.as_posix(),
            }
        )

        _emit_progress(
            progress_callback,
            {
                "stage": "l2_chapter",
                "event": "chapter_done",
                "completed_chapters": chapter_index,
                "chapter_no": chapter_no,
                "chapter_title": chapter_title,
                "total_chapters": len(chapters),
                "output_file": extraction_file.as_posix(),
            },
        )

    _emit_progress(
        progress_callback,
        {
            "stage": "l2_chapter",
            "event": "chapter_batch_done",
            "total_chapters": len(chapters),
            "output_dir": extraction_output_dir.as_posix(),
        },
    )

    return {
        "chapter_extraction_rows": l2_records,
        "chapter_extraction_cache_dir": extraction_output_dir.as_posix(),
        "llm": _public_llm_config(llm_cfg),
    }


def _compose_book_context(chapter_jsons: list[tuple[Path, Any]]) -> str:
    chunks: list[str] = []
    for file_path, payload in chapter_jsons:
        chunks.append(f"【章节文件】{file_path.name}\n{json.dumps(payload, ensure_ascii=False, indent=2)}")
    return "\n\n".join(chunks)


def _value_contains_text(value: Any, needle: str) -> bool:
    if not needle:
        return False
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(_value_contains_text(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_value_contains_text(item, needle) for item in value)
    return needle in str(value)


def _extract_card_section(section_value: Any, character_name: str) -> Any:
    cleaned_value = _remove_empty_fields(section_value)
    if cleaned_value in (None, "", [], {}, ()):
        return None

    if isinstance(cleaned_value, dict):
        characters = cleaned_value.get("characters")
        if isinstance(characters, list):
            matched_characters = [entry for entry in characters if _value_contains_text(entry, character_name)]
            if matched_characters:
                return {"characters": matched_characters}

    if isinstance(cleaned_value, list):
        matched_items = [entry for entry in cleaned_value if _value_contains_text(entry, character_name)]
        if matched_items:
            return matched_items

    if _value_contains_text(cleaned_value, character_name):
        return cleaned_value

    return None


def _compose_card_context(
    chapter_jsons: list[tuple[Path, Any]],
    *,
    character_name: str,
    prompt_description: str,
    summary_character: dict[str, Any] | None = None,
) -> str:
    chunks: list[str] = [
        f"【任务角色】{character_name}",
        f"【任务说明】{prompt_description}",
        "【上下文要求】优先依据 summary.characters 中选中的角色条目生成角色卡，再结合每章中与目标角色相关的片段补充，不要引入无关人物或章节噪声。",
    ]

    if summary_character:
        chunks.append(
            "【summary角色条目】\n"
            + json.dumps(summary_character, ensure_ascii=False, indent=2)
        )

    for file_path, payload in chapter_jsons:
        chapter_payload = payload if isinstance(payload, dict) else {}
        chapter_excerpt: dict[str, Any] = {}

        chapter_title = chapter_payload.get("chapter_title")
        if chapter_title not in (None, "", [], {}, ()):
            chapter_excerpt["chapter_title"] = chapter_title

        for section_name in ("chapter_info", "plot", "characters", "items", "world"):
            section_value = chapter_payload.get(section_name)
            selected_value = _extract_card_section(section_value, character_name)
            if selected_value not in (None, "", [], {}, ()):
                chapter_excerpt[section_name] = selected_value

        if chapter_excerpt:
            chunks.append(f"【章节文件】{file_path.name}\n{json.dumps(chapter_excerpt, ensure_ascii=False, indent=2)}")

    return "\n\n".join(chunks)


def dispatch_summary_prompts(
    *,
    chapter_json_dir: str | Path,
    source_file_id: str,
    book_title: str | None = None,
    enabled_dimensions: list[str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    timeout_seconds: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    config = _load_config()
    prompts = _resolve_prompt_group(config, "summary_prompts")
    llm_cfg = _resolve_llm_config(
        config,
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )

    input_dir = Path(chapter_json_dir)
    chapter_jsons = _load_json_files(input_dir)
    if not chapter_jsons:
        raise FileNotFoundError(f"No chapter json files found in {input_dir}")

    book_cache_dir = input_dir.parent
    summary_root_dir = book_cache_dir / "summary"
    summary_root_dir.mkdir(parents=True, exist_ok=True)

    title = book_title or source_file_id
    dimensions = enabled_dimensions or list(prompts.keys())
    summary_rows: list[dict[str, Any]] = []

    _emit_progress(
        progress_callback,
        {
            "stage": "summary",
            "event": "summary_start",
            "total_dimensions": len(dimensions),
            "source_file_id": source_file_id,
        },
    )

    for dim_index, dimension in enumerate(dimensions, start=1):
        prompt = prompts.get(dimension)
        if not prompt:
            continue
        _emit_progress(
            progress_callback,
            {
                "stage": "summary",
                "event": "summary_dimension_start",
                "dimension": dimension,
                "dimension_index": dim_index,
                "total_dimensions": len(dimensions),
            },
        )
        context_text = _compose_summary_context(
            chapter_jsons,
            dimension=dimension,
            prompt_description=prompt,
        )
        
        # Call appropriate LLM function based on dimension type
        if dimension in {"characters", "items"}:
            # JSON-based dimensions
            result = _call_dimension_prompt(text=context_text, prompt_description=prompt, llm_cfg=llm_cfg)
        else:
            # Markdown-based dimensions (storyline_events, world_locations)
            result = _call_dimension_prompt_text(text=context_text, prompt_description=prompt, llm_cfg=llm_cfg)
        
        dimension_dir = summary_root_dir / dimension
        dimension_dir.mkdir(parents=True, exist_ok=True)

        if dimension in {"characters", "items"}:
            if dimension == "characters":
                if not _coerce_summary_list_payload(result, dimension="characters"):
                    result = _fallback_summary_entries(chapter_jsons, dimension="characters")
                output_file_path, _index_rows = _write_character_summary_files(
                    dimension_dir=dimension_dir,
                    result=result,
                )
            else:
                output_json_path = dimension_dir / "items.json"
                payload = _coerce_summary_list_payload(result, dimension="items")
                if not payload:
                    payload = _fallback_summary_entries(chapter_jsons, dimension="items")
                output_json_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                output_file_path = output_json_path
            output_kind = "json"
        else:
            output_md_path = dimension_dir / f"{dimension}.md"
            md_content = _summary_md_from_result(title=title, dimension=dimension, result=result)
            output_md_path.write_text(md_content, encoding="utf-8")
            output_file_path = output_md_path
            output_kind = "md"

        summary_rows.append(
            {
                "dimension": dimension,
                "content_url": output_file_path.as_posix(),
                "content_kind": output_kind,
            }
        )
        _emit_progress(
            progress_callback,
            {
                "stage": "summary",
                "event": "summary_dimension_done",
                "dimension": dimension,
                "dimension_index": dim_index,
                "total_dimensions": len(dimensions),
                "content_url": output_file_path.as_posix(),
                "content_kind": output_kind,
            },
        )

    _emit_progress(
        progress_callback,
        {
            "stage": "summary",
            "event": "summary_done",
            "total_dimensions": len(summary_rows),
            "output_dir": summary_root_dir.as_posix(),
        },
    )

    return {
        "summary_rows": summary_rows,
        "summary_root_dir": summary_root_dir.as_posix(),
        "llm": _public_llm_config(llm_cfg),
    }


def dispatch_card_prompts(
    *,
    chapter_json_dir: str | Path | None = None,
    input_dir: str | Path | None = None,
    source_file_id: str,
    character_name: str,
    book_title: str | None = None,
    summary_character: dict[str, Any] | None = None,
    enabled_dimensions: list[str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    timeout_seconds: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    config = _load_config()
    prompts = _resolve_prompt_group(config, "card_prompts")
    card_field_map = config.get("card_field_map")
    card_markdown_sections = _normalize_card_markdown_sections(card_field_map)
    llm_cfg = _resolve_llm_config(
        config,
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )

    resolved_input_dir = chapter_json_dir or input_dir
    if not resolved_input_dir:
        raise ValueError("dispatch_card_prompts requires chapter_json_dir or input_dir")

    source_dir = Path(resolved_input_dir)
    payloads = _load_json_files(source_dir)
    if not payloads:
        raise FileNotFoundError(f"No json files found in {source_dir}")

    book_cache_dir = source_dir.parent
    card_root_dir = book_cache_dir / "card"

    title = book_title or source_file_id
    dimensions = enabled_dimensions or list(prompts.keys())
    card_rows: list[dict[str, Any]] = []
    safe_character_name = _safe_folder_name(character_name)

    _emit_progress(
        progress_callback,
        {
            "stage": "card",
            "event": "card_start",
            "total_dimensions": len(dimensions),
            "source_file_id": source_file_id,
            "character_name": character_name,
        },
    )

    for dim_index, dimension in enumerate(dimensions, start=1):
        prompt = prompts.get(dimension)
        if not prompt:
            continue
        _emit_progress(
            progress_callback,
            {
                "stage": "card",
                "event": "card_dimension_start",
                "dimension": dimension,
                "dimension_index": dim_index,
                "total_dimensions": len(dimensions),
                "character_name": character_name,
            },
        )
        context_text = _compose_card_context(
            payloads,
            character_name=character_name,
            prompt_description=prompt,
            summary_character=summary_character,
        )
        card_prompt = (
            f"角色名：{character_name}\n{prompt}\n\n"
            "请严格按以下 Markdown 结构输出，禁止输出 JSON、代码块、表格或额外解释：\n"
            + "\n".join(card_markdown_sections)
            + "\n\n如果某部分没有可靠证据，可留空，但不要臆造。"
        )
        result = call_llm_text(
            text_or_documents=context_text,
            prompt_description=card_prompt,
            model=llm_cfg["model"],
            base_url=llm_cfg["base_url"],
            temperature=llm_cfg.get("temperature", 0.1),
            timeout_seconds=llm_cfg.get("timeout_seconds", 60),
            provider=llm_cfg.get("provider"),
            api_key=llm_cfg.get("api_key"),
        )
        card_root_dir.mkdir(parents=True, exist_ok=True)
        output_md_path = card_root_dir / f"{source_file_id}_{safe_character_name}_{dimension}.md"
        markdown_content = result.strip()
        output_md_path.write_text(markdown_content.rstrip() + "\n", encoding="utf-8")
        card_rows.append(
            {
                "dimension": dimension,
                "content_url": output_md_path.as_posix(),
                "content_kind": "md",
            }
        )
        _emit_progress(
            progress_callback,
            {
                "stage": "card",
                "event": "card_dimension_done",
                "dimension": dimension,
                "dimension_index": dim_index,
                "total_dimensions": len(dimensions),
                "content_url": output_md_path.as_posix(),
                "character_name": character_name,
            },
        )

    _emit_progress(
        progress_callback,
        {
            "stage": "card",
            "event": "card_done",
            "total_dimensions": len(card_rows),
            "output_dir": card_root_dir.as_posix(),
            "character_name": character_name,
        },
    )

    return {
        "card_rows": card_rows,
        "card_root_dir": card_root_dir.as_posix(),
        "llm": _public_llm_config(llm_cfg),
    }


def dispatch_fulltext_extraction(
    *,
    full_text: str,
    source_file_id: str,
    book_title: str | None = None,
    cache_folder: str,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    timeout_seconds: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """全文一次性提取：将完整文本发送给 GLM，一次性提取全部维度。"""
    config = _load_config()
    prompts = _resolve_prompt_group(config, "fulltext_prompts")
    prompt = prompts.get("full_extraction")
    if not prompt:
        raise ValueError("fulltext_prompts.full_extraction not found in config.json")

    llm_cfg = _resolve_llm_config(
        config,
        provider="glm",
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds or 600,
    )

    title = book_title or source_file_id
    context = f"【书名】{title}\n【来源ID】{source_file_id}\n\n【完整原文】\n{full_text}"

    _emit_progress(
        progress_callback,
        {
            "stage": "fulltext",
            "event": "fulltext_start",
            "source_file_id": source_file_id,
            "text_length": len(full_text),
            "model": llm_cfg["model"],
        },
    )

    parsed = _call_dimension_prompt(
        text=context,
        prompt_description=prompt,
        llm_cfg=llm_cfg,
    )

    result = parsed if isinstance(parsed, dict) else {}

    # 写入缓存
    cache_dir = Path(cache_folder)
    fulltext_dir = cache_dir / "fulltext_extraction"
    fulltext_dir.mkdir(parents=True, exist_ok=True)

    output_json_path = fulltext_dir / f"{source_file_id}_fulltext.json"
    output_json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _emit_progress(
        progress_callback,
        {
            "stage": "fulltext",
            "event": "fulltext_done",
            "source_file_id": source_file_id,
            "output_file": output_json_path.as_posix(),
            "characters_count": len(result.get("characters") or []),
            "items_count": len(result.get("items") or []),
            "events_count": len(result.get("storyline_events") or []),
            "locations_count": len(result.get("world_locations") or []),
        },
    )

    return {
        "fulltext_result": result,
        "fulltext_json_path": output_json_path.as_posix(),
        "fulltext_dir": fulltext_dir.as_posix(),
        "llm": _public_llm_config(llm_cfg),
    }


def build_fulltext_dispatch_from_source(
    *,
    source_path: str | None = None,
    source_type: str = "txt",
    source_file_id: str = "sf_local_001",
    file_name: str | None = None,
    file_url: str | None = None,
    filter_noise: bool = True,
    book_id: str | None = None,
    book_title: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    timeout_seconds: int | None = None,
    max_chapters: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """L0/L1 预处理后，拼接全文发送给 GLM 一次性提取。"""
    from backend.source_preprocess import process_source_file

    l0_l1 = process_source_file(
        source_path=source_path,
        source_type=source_type,
        source_file_id=source_file_id,
        file_name=file_name,
        file_url=file_url,
        filter_noise=filter_noise,
        book_id=book_id,
        book_title=book_title,
    )
    chapters = l0_l1["chapters"]
    if max_chapters is not None:
        chapters = chapters[: max(0, int(max_chapters))]

    # 拼接全部章节为完整文本
    full_text_parts: list[str] = []
    for ch in chapters:
        title = str(ch.get("chapter_title", ""))
        content = str(ch.get("content_text", ""))
        full_text_parts.append(f"【{title}】\n{content}")
    full_text = "\n\n".join(full_text_parts)

    fulltext_dispatch = dispatch_fulltext_extraction(
        full_text=full_text,
        source_file_id=source_file_id,
        book_title=book_title,
        cache_folder=l0_l1["cache_folder"],
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        progress_callback=progress_callback,
    )

    chapter_rows = [
        {
            "chapter_no": ch["chapter_no"],
            "chapter_title": ch["chapter_title"],
            "chapter_range": ch["chapter_range"],
            "word_count": ch["word_count"],
            "content_text_url": ch["content_text_url"],
        }
        for ch in chapters
    ]

    return {
        "source_file_row": {
            "source_file_id": source_file_id,
            "source_type": l0_l1["source_type"],
            "unified_format_url": l0_l1["unified_format_url"],
            "file_name": l0_l1.get("file_name"),
            "local_source_url": l0_l1.get("local_source_url"),
        },
        "chapter_rows": chapter_rows,
        "fulltext_result": fulltext_dispatch["fulltext_result"],
        "fulltext_json_path": fulltext_dispatch["fulltext_json_path"],
        "fulltext_dir": fulltext_dispatch["fulltext_dir"],
        "cache_folder": l0_l1["cache_folder"],
        "llm": fulltext_dispatch["llm"],
    }


def build_chapter_dispatch_from_source(
    *,
    source_path: str | None = None,
    source_type: str = "txt",
    source_file_id: str = "sf_local_001",
    file_name: str | None = None,
    file_url: str | None = None,
    filter_noise: bool = True,
    book_id: str | None = None,
    book_title: str | None = None,
    enabled_dimensions: list[str] | None = None,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    timeout_seconds: int | None = None,
    max_chapters: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    l0_l1 = process_source_file(
        source_path=source_path,
        source_type=source_type,
        source_file_id=source_file_id,
        file_name=file_name,
        file_url=file_url,
        filter_noise=filter_noise,
        book_id=book_id,
        book_title=book_title,
    )
    chapters = l0_l1["chapters"]
    if max_chapters is not None:
        limit = max(0, int(max_chapters))
        chapters = chapters[:limit]

    chapter_dispatch = dispatch_chapter_prompts(
        chapters=chapters,
        source_file_id=source_file_id,
        cache_folder=l0_l1["cache_folder"],
        enabled_dimensions=enabled_dimensions,
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        max_chars_per_chapter=None if provider in {"glm", "bigmodel"} else 6000,
        progress_callback=progress_callback,
    )

    chapter_rows = [
        {
            "chapter_no": chapter["chapter_no"],
            "chapter_title": chapter["chapter_title"],
            "chapter_range": chapter["chapter_range"],
            "word_count": chapter["word_count"],
            "content_text_url": chapter["content_text_url"],
        }
        for chapter in chapters
    ]

    return {
        "source_file_row": {
            "source_file_id": source_file_id,
            "source_type": l0_l1["source_type"],
            "unified_format_url": l0_l1["unified_format_url"],
            "file_name": l0_l1.get("file_name"),
            "local_source_url": l0_l1.get("local_source_url"),
        },
        "chapter_rows": chapter_rows,
        "chapter_extraction_rows": chapter_dispatch["chapter_extraction_rows"],
        "chapter_extraction_cache_dir": chapter_dispatch["chapter_extraction_cache_dir"],
        "cache_folder": l0_l1["cache_folder"],
        "llm": chapter_dispatch["llm"],
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CharPick LLM dispatch for chapter, summary, or card prompts.")
    subparsers = parser.add_subparsers(dest="task", required=True)

    chapter_parser = subparsers.add_parser("chapter", help="Run chapter prompt dispatch from raw source files.")
    chapter_parser.add_argument("--source-path")
    chapter_parser.add_argument("--source-type", default="txt")
    chapter_parser.add_argument("--source-file-id", default="sf_local_001")
    chapter_parser.add_argument("--file-name")
    chapter_parser.add_argument("--file-url")
    chapter_parser.add_argument("--filter-noise", action="store_true")
    chapter_parser.add_argument("--book-id")
    chapter_parser.add_argument("--book-title")
    chapter_parser.add_argument("--provider")
    chapter_parser.add_argument("--model")
    chapter_parser.add_argument("--base-url")
    chapter_parser.add_argument("--temperature", type=float)
    chapter_parser.add_argument("--timeout-seconds", type=int)
    chapter_parser.add_argument("--dimensions", nargs="*")

    summary_parser = subparsers.add_parser("summary", help="Run summary prompt dispatch from chapter extraction json files.")
    summary_parser.add_argument("--chapter-json-dir", required=True)
    summary_parser.add_argument("--source-file-id", required=True)
    summary_parser.add_argument("--book-title")
    summary_parser.add_argument("--provider")
    summary_parser.add_argument("--model")
    summary_parser.add_argument("--base-url")
    summary_parser.add_argument("--temperature", type=float)
    summary_parser.add_argument("--timeout-seconds", type=int)
    summary_parser.add_argument("--dimensions", nargs="*")

    card_parser = subparsers.add_parser("card", help="Run card prompt dispatch from chapter extraction json files.")
    card_parser.add_argument("--chapter-json-dir", "--input-dir", dest="chapter_json_dir", required=True)
    card_parser.add_argument("--source-file-id", required=True)
    card_parser.add_argument("--character-name", required=True)
    card_parser.add_argument("--book-title")
    card_parser.add_argument("--provider")
    card_parser.add_argument("--model")
    card_parser.add_argument("--base-url")
    card_parser.add_argument("--temperature", type=float)
    card_parser.add_argument("--timeout-seconds", type=int)
    card_parser.add_argument("--dimensions", nargs="*")

    return parser


def main() -> None:
    parser = _build_cli()
    args = parser.parse_args()

    if args.task == "chapter":
        result = build_chapter_dispatch_from_source(
            source_path=args.source_path,
            source_type=args.source_type,
            source_file_id=args.source_file_id,
            file_name=args.file_name,
            file_url=args.file_url,
            filter_noise=args.filter_noise,
            book_id=args.book_id,
            book_title=args.book_title,
            enabled_dimensions=args.dimensions,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            temperature=args.temperature,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.task == "summary":
        result = dispatch_summary_prompts(
            chapter_json_dir=args.chapter_json_dir,
            source_file_id=args.source_file_id,
            book_title=args.book_title,
            enabled_dimensions=args.dimensions,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            temperature=args.temperature,
            timeout_seconds=args.timeout_seconds,
        )
    else:
        result = dispatch_card_prompts(
            chapter_json_dir=args.chapter_json_dir,
            source_file_id=args.source_file_id,
            character_name=args.character_name,
            book_title=args.book_title,
            enabled_dimensions=args.dimensions,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            temperature=args.temperature,
            timeout_seconds=args.timeout_seconds,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
