import json
from pathlib import Path

from .extractor_client import call_ollama_json


DIMENSION_KEY_MAP = {
    "chapter_info": "chapter_info",
    "plot": "plot",
    "characters": "characters",
    "items": "items",
    "world": "world",
    "scene_description": "scene_description",
}


def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parents[1] / "config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _remove_empty_fields(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            cleaned = _remove_empty_fields(v)
            if cleaned not in (None, "", [], {}, ()):  # keep only non-empty
                out[k] = cleaned
        return out
    if isinstance(value, list):
        out = [_remove_empty_fields(v) for v in value]
        return [v for v in out if v not in (None, "", [], {}, ())]
    return value


def extract_chapter_structured(
    chapter_title: str,
    chapter_text: str,
    enabled_dimensions: list[str] | None = None,
) -> dict:
    cfg = _load_config()
    llm_cfg = cfg["llm"]
    prompts = cfg.get("chapter_prompts") or cfg.get("prompts", {})

    dimensions = enabled_dimensions or list(DIMENSION_KEY_MAP.keys())
    result = {"chapter_title": chapter_title}

    base_text = f"{chapter_title}\n{chapter_text[:6000]}"

    for dim in dimensions:
        prompt = prompts.get(dim)
        if not prompt:
            continue

        try:
            parsed = call_ollama_json(
                text_or_documents=base_text,
                prompt_description=prompt,
                model=llm_cfg["model"],
                base_url=llm_cfg["base_url"],
                temperature=llm_cfg.get("temperature", 0.1),
                timeout_seconds=llm_cfg.get("timeout_seconds", 60),
            )
            cleaned = _remove_empty_fields(parsed)
            if cleaned:
                result[DIMENSION_KEY_MAP[dim]] = cleaned
        except Exception as exc:
            result.setdefault("errors", []).append({"dimension": dim, "error": str(exc)})

    return _remove_empty_fields(result)
