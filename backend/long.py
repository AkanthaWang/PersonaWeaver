import hashlib
import json
from pathlib import Path

import requests

from backend.source_preprocess.chapter_chunker import split_into_chapters
from backend.source_preprocess.parsers.txt_parser import detect_encoding
from backend.source_preprocess.text_cleaner import clean_text


def _load_model_name() -> str:
    config_path = Path(__file__).resolve().parent / "config.json"
    if not config_path.exists():
        return "gemma2:9b"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data.get("llm", {}).get("model", "gemma2:9b")


local_model = _load_model_name()

EXAMPLES = [
    {
        "text": "石野大喊：‘我不信！’，他紧握拳头看向镜子。",
        "attributes": {
            "characters": [
                {
                    "name": "石野",
                    "behavior": ["大喊", "紧握拳头", "看向镜子"],
                    "speech": ["我不信！"],
                    "psychology": ["质疑"],
                }
            ]
        },
    }
]


def advanced_split_novel(file_path: str, filter_noise: bool = False):
    enc = detect_encoding(Path(file_path))
    text = Path(file_path).read_text(encoding=enc, errors="ignore")
    cleaned = clean_text(text)
    return split_into_chapters(cleaned, filter_noise=filter_noise)


def _deterministic_vector(text: str, dim: int = 256):
    md = hashlib.md5(text.encode("utf-8")).digest()
    vec = []
    for i in range(dim):
        b = md[i % len(md)]
        vec.append((b / 255.0) * 2 - 1)
    return vec


def get_ollama_embedding(text: str):
    if not text:
        return []

    try:
        resp = requests.post(
            "http://localhost:11434/embeddings",
            json={"model": local_model, "input": text},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                if "embeddings" in data:
                    return data["embeddings"]
                if "data" in data and isinstance(data["data"], list) and data["data"]:
                    if "embedding" in data["data"][0]:
                        return data["data"][0]["embedding"]
            if isinstance(data, list):
                return data
    except Exception:
        pass

    return _deterministic_vector(text, dim=256)
