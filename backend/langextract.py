import json
from pathlib import Path

from backend.llm_chapter_extraction.extractor_client import call_ollama_json


def _load_llm_config() -> dict:
    cfg_path = Path(__file__).resolve().parent / "config.json"
    if not cfg_path.exists():
        return {
            "base_url": "http://localhost:11434",
            "model": "gemma2:9b",
            "temperature": 0.1,
            "timeout_seconds": 60,
        }

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    llm_cfg = data.get("llm", {})
    return {
        "base_url": llm_cfg.get("base_url", "http://localhost:11434"),
        "model": llm_cfg.get("model", "gemma2:9b"),
        "temperature": llm_cfg.get("temperature", 0.1),
        "timeout_seconds": llm_cfg.get("timeout_seconds", 60),
    }


def extract(text_or_documents: str, prompt_description: str, examples: list, model: str) -> dict:
    """兼容旧接口：返回 {"extractions": [{"attributes": ...}]}。"""
    cfg = _load_llm_config()
    chosen_model = model or cfg["model"]

    try:
        parsed = call_ollama_json(
            text_or_documents=text_or_documents,
            prompt_description=prompt_description,
            model=chosen_model,
            base_url=cfg["base_url"],
            temperature=cfg["temperature"],
            timeout_seconds=cfg["timeout_seconds"],
        )
        if isinstance(parsed, dict):
            return {"extractions": [{"attributes": parsed}]}
        return {"extractions": []}
    except Exception as exc:
        print(f"[langextract] error: {exc}")
        return {"extractions": []}
