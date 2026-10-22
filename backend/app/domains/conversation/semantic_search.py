"""Semantic recall over the same filtered documents used by local chat search."""

import logging

from backend.app.domains.retrieval.vector import search_vector
from backend.app.domains.settings import llm
from backend.app.domains.settings.repository import SettingsRepository
from backend.app.domains.settings.selection import load_function_profile

logger = logging.getLogger(__name__)


def recall(database, scoped, user_id, query, documents, limit):
    selection = SettingsRepository(database).selections(user_id) or {}
    if not selection.get("embedding_model_id") or not documents:
        return []
    try:
        profile = load_function_profile(database, user_id, "embedding")
        # Namespace chat chunks separately from the independent chapter index.
        rows = [
            {"id": "chat:" + item["id"], "title": item["title"], "content": item["content"]}
            for item in documents
        ]
        matches = search_vector(
            scoped, profile, llm.settings_from_profile(profile), query, rows, limit,
        )
        by_id = {"chat:" + item["id"]: item for item in documents}
        return [by_id[row["id"]] for row in matches if row["score"] > 0]
    except Exception as exc:
        logger.warning("Conversation embedding unavailable; using keyword recall (%s)",
                       llm.error_diagnostics(exc))
        return []


def fuse(keyword, semantic, limit):
    scores, items = {}, {}
    for ranking in (keyword, semantic):
        for rank, item in enumerate(ranking, 1):
            key = item["id"]
            items[key] = item
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
    return [items[key] for key in sorted(scores, key=scores.get, reverse=True)[:limit]]
