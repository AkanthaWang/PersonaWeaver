"""Lazy chapter indexing with a separate cache for each embedding configuration."""

import hashlib
import json
import math

from backend.app.ai.providers.retrieval import embed


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cosine(left, right):
    if len(left) != len(right):
        raise ValueError("Embedding 向量维度不匹配，请重新测试模型并重建索引")
    denominator = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))
    if not denominator:
        raise ValueError("Embedding 返回无效零向量，请检查模型")
    return sum(a * b for a, b in zip(left, right)) / denominator


def search_vector(db, profile, settings, query, rows, limit):
    if not rows:
        return []
    # Include connection changes without retaining credentials in cache keys.
    model_key = _hash(json.dumps({
        "profile_id": profile["id"], "settings": settings,
    }, sort_keys=True, ensure_ascii=False))
    query_vector = embed(settings, [query])[0]
    output = []
    for row in rows:
        content = row["title"] + "\n" + row["content"]
        content_hash = _hash(content)
        cached = db.one(
            "SELECT content_hash,vector_json FROM chapter_vectors WHERE chapter_id=? AND model_key=?",
            (row["id"], model_key),
        )
        vector = json.loads(cached["vector_json"]) if cached and cached["content_hash"] == content_hash else None
        if vector is None or len(vector) != len(query_vector):
            chunks = [content[offset:offset + 2000] for offset in range(0, len(content), 2000)]
            vectors = []
            for offset in range(0, len(chunks), 16):
                vectors.extend(embed(settings, chunks[offset:offset + 16]))
            if any(len(item) != len(query_vector) for item in vectors):
                raise ValueError("Embedding 向量维度发生变化，请重新测试模型并重建索引")
            vector = [sum(values) / len(vectors) for values in zip(*vectors)]
            db.execute(
                "INSERT INTO chapter_vectors(chapter_id,model_key,content_hash,vector_json) VALUES (?,?,?,?) "
                "ON CONFLICT(chapter_id,model_key) DO UPDATE SET content_hash=excluded.content_hash,vector_json=excluded.vector_json",
                (row["id"], model_key, content_hash, json.dumps(vector)),
            )
        output.append({**row, "score": _cosine(query_vector, vector)})
    return sorted(output, key=lambda item: item["score"], reverse=True)[:limit]
