from __future__ import annotations

import logging

from fastapi import HTTPException

from backend.app.ai.providers.retrieval import rerank
from backend.app.db.base_repository import SQLiteRepository
from backend.app.domains.settings import llm
from backend.app.domains.settings.selection import load_function_profile
from backend.app.domains.settings.repository import SettingsRepository

from .vector import search_vector


logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, db):
        self.repo = SQLiteRepository(db)

    def search(self, user_id: str, query: str, book_id: str | None, limit: int):
        db = self.repo.database
        embedding = load_function_profile(db, user_id, "embedding")
        reranker = load_function_profile(db, user_id, "reranker")
        selection = SettingsRepository(db).selections(user_id) or {}
        top_k = min(limit, selection.get("reranker_top_k", 5))
        sql = "SELECT c.id,c.book_id,c.title,c.content FROM chapters c JOIN books b ON c.book_id=b.book_id WHERE b.user_id=?"
        params = [user_id]
        if book_id:
            sql += " AND c.book_id=?"
            params.append(book_id)
        rows = self.repo.all(sql, params)
        try:
            items = search_vector(db, embedding, llm.settings_from_profile(embedding), query, rows,
                                  max(limit, top_k * 4) if reranker else limit)
        except Exception as exc:
            message = f"Embedding 检索失败：{llm.error_message(exc)}。请前往「偏好设置 → 模型选用」检查绑定，并在「模型设置」重新测试。"
            logger.error("%s", message)
            raise HTTPException(502, message) from exc
        if reranker and items:
            try:
                results = rerank(llm.settings_from_profile(reranker), query,
                                 [item["title"] + "\n" + item["content"] for item in items], top_k)
                items = [{**items[result["index"]], "vector_score": items[result["index"]]["score"],
                          "score": result["score"]} for result in results]
            except Exception as exc:
                message = f"Reranker 精排失败：{llm.error_message(exc)}。请前往「偏好设置 → 模型选用」检查绑定，并在「模型设置」重新测试。"
                logger.error("%s", message)
                raise HTTPException(502, message) from exc
        return {"items": items, "query": query}
