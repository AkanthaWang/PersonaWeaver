"""Embedding and reranking transports, independent of chat generation."""

import math
from urllib.parse import urlsplit, urlunsplit

import requests


def _endpoint(settings, operation):
    parts = urlsplit(settings["base_url"].rstrip("/"))
    path = parts.path
    suffixes = ("/chat/completions", "/responses", "/embeddings", "/rerank", "/api/embed")
    for suffix in suffixes:
        if path.endswith(suffix):
            path = path[:-len(suffix)]
            break
    if operation == "embed" and settings["provider"] == "ollama":
        path = path.removesuffix("/api").removesuffix("/v1") + "/api/embed"
    else:
        path += "/embeddings" if operation == "embed" else "/rerank"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _post(settings, operation, payload):
    headers = dict(settings.get("headers") or {})
    if settings.get("api_key"):
        headers["Authorization"] = f"Bearer {settings['api_key']}"
    response = requests.post(
        _endpoint(settings, operation), headers=headers, json={"model": settings["model"], **payload},
        timeout=(10, settings.get("timeout_seconds", 60)),
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("模型接口返回格式错误")
    return result


def embed(settings, texts):
    result = _post(settings, "embed", {"input": texts})
    if settings["provider"] == "ollama":
        vectors = result.get("embeddings")
    else:
        rows = result.get("data")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Embedding 接口没有返回有效向量")
        if sorted(row.get("index", -1) for row in rows) != list(range(len(texts))):
            raise ValueError("Embedding 接口返回的向量索引不完整")
        vectors = [row.get("embedding") for row in sorted(rows, key=lambda row: row["index"])]
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ValueError("Embedding 接口返回的向量数量不匹配")
    dimension = None
    for vector in vectors:
        if not isinstance(vector, list) or not vector or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError("Embedding 接口返回无效向量")
        if dimension is not None and len(vector) != dimension:
            raise ValueError("Embedding 向量维度不一致，请重新索引")
        if not any(vector):
            raise ValueError("Embedding 接口返回零向量")
        dimension = len(vector)
    return vectors


def rerank(settings, query, documents, top_k):
    result = _post(settings, "rerank", {"query": query, "documents": documents, "top_n": top_k})
    rows = result.get("results")
    if not isinstance(rows, list) or len(rows) < min(top_k, len(documents)):
        raise ValueError("Reranker 接口没有返回完整精排结果")
    seen, output = set(), []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Reranker 接口返回格式错误")
        index, score = row.get("index"), row.get("relevance_score")
        if (isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(documents)
                or index in seen or isinstance(score, bool) or not isinstance(score, (int, float))
                or not math.isfinite(score)):
            raise ValueError("Reranker 接口返回无效精排结果")
        seen.add(index)
        output.append({"index": index, "score": float(score)})
    return sorted(output, key=lambda row: row["score"], reverse=True)[:top_k]
