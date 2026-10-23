"""Bounded read-only tools. The server, not the model, owns scope and ordering."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domains.conversation import knowledge_search
from .storage import digest


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchKnowledge(Arguments):
    query: str = Field(min_length=1, max_length=1000)

    @field_validator("query")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("查询不能为空")
        return value.strip()


class SearchOriginal(SearchKnowledge):
    knowledge_call_id: str = Field(min_length=1, max_length=100)
    missing_question: str = Field(min_length=1, max_length=1000)


class ReadOriginal(Arguments):
    knowledge_call_id: str = Field(min_length=1, max_length=100)
    missing_question: str = Field(min_length=1, max_length=1000)
    chapter_id: str = Field(min_length=1, max_length=100)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


MODELS = {"search_knowledge": SearchKnowledge, "search_original": SearchOriginal, "read_original": ReadOriginal}
DESCRIPTIONS = {
    "search_knowledge": "Search extracted characters, facts, relations, events and setting. Always use first.",
    "search_original": "Search original text only for a specific gap after a completed knowledge query.",
    "read_original": "Read at most 2000 Unicode characters of an owned chapter to resolve a knowledge gap.",
}


def definitions():
    return [{"type": "function", "function": {
        "name": name, "description": DESCRIPTIONS[name], "parameters": model.model_json_schema(),
    }} for name, model in MODELS.items()]


class ToolCall(Arguments):
    name: Literal["search_knowledge", "search_original", "read_original"]
    arguments: dict


class Decision(Arguments):
    calls: list[ToolCall] = Field(max_length=8)


class ToolExecutor:
    def __init__(self, db, user_id, row):
        self.db, self.user_id, self.row = db, user_id, row

    def execute(self, name, arguments, observations):
        if not self.row.get("book_id") or not self.row.get("knowledge_enabled"):
            raise ValueError("当前会话未启用关联作品检索")
        if name not in MODELS:
            raise ValueError("未知工具")
        args = MODELS[name].model_validate(arguments)
        book_id = self.row["book_id"]
        if not self.db.one("SELECT book_id FROM books WHERE book_id=? AND user_id=?", (book_id, self.user_id)):
            raise ValueError("关联作品不可访问")
        if name != "search_knowledge":
            prior = next((o for o in observations if o["id"] == args.knowledge_call_id
                          and o["name"] == "search_knowledge" and not o.get("error")), None)
            if not prior or not args.missing_question.strip():
                raise ValueError("原文补查必须关联本轮已完成资料查询和明确缺失问题")
        key = digest([name, args.model_dump()])
        cached = next((o for o in observations if o.get("cache_key") == key and not o.get("error")), None)
        if cached:
            return {**cached, "cached": True}
        if name in {"search_knowledge", "search_original"}:
            items = knowledge_search.retrieve(self.db, self.user_id, book_id, args.query, limit=6,
                                              use_embeddings=False, scope="knowledge" if name == "search_knowledge" else "original")
        else:
            if args.end <= args.start or args.end - args.start > 2000:
                raise ValueError("原文读取范围必须为 1 至 2000 字符")
            book_db = self.db.book_database(book_id)
            chapter = book_db.one("SELECT * FROM chapters WHERE id=? AND book_id=?", (args.chapter_id, book_id))
            if not chapter or args.end > len(chapter["content"]):
                raise ValueError("章节或字符范围不可访问")
            quote = chapter["content"][args.start:args.end]
            items = [{"id": f"chapter:{chapter['id']}:{args.start}", "kind": "chapter", "book_id": book_id,
                      "chapter_id": chapter["id"], "chapter_no": chapter["chapter_no"],
                      "title": chapter["title"], "chapter_title": chapter["title"],
                      "content": quote, "quote": quote, "start": args.start, "end": args.end,
                      "index_revision": knowledge_search.ensure_index(book_db, book_id), "retrieval": "read"}]
        return {"id": "lookup_" + key[:20], "name": name, "arguments": args.model_dump(),
                "cache_key": key, "items": items, "cached": False}
