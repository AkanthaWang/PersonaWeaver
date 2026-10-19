from __future__ import annotations


def rank(results: list[dict], limit: int = 10) -> list[dict]:
    return sorted(results, key=lambda item: item.get("score", 0), reverse=True)[:limit]
