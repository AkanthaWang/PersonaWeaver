from __future__ import annotations
from pathlib import Path

from fastapi import HTTPException

from backend.app.db.database import identifier, now
from backend.app.domains.settings import llm
from backend.app.domains.settings.selection import load_function_profile
from backend.app.domains.workflow import tasks as workflow

from .chapter_storage import chapter_output_paths, remove_chapter_outputs, save_chapter_outputs
from .parsing.chapter_chunker import split_into_chapters
from .parsing.parsers import parse_input_to_text
from .parsing.text_cleaner import clean_text
from .repository import DocumentRepository


SUMMARY_LABELS = {"characters": "角色", "items": "物品", "storyline_events": "剧情", "world_locations": "世界与地点"}
SUPPORTED = {"txt", "md", "epub", "pdf", "docx"}


class DocumentService:
    def __init__(self, db):
        self.db = db
        self.repo = DocumentRepository(db)

    def _view(self, book):
        return {
            **{k: v for k, v in book.items() if k not in {"source_path", "user_id"}},
            "book_name": book["title"],
            "chapter_count": DocumentRepository(self.db.book_database(book["book_id"])).chapter_count(book["book_id"]),
        }

    def list(self, user_id: str):
        return {"books": [self._view(book) for book in self.repo.list_for_user(user_id)]}

    def get_owned(self, user_id: str, book_id: str):
        book = self.repo.get_owned(user_id, book_id)
        if not book:
            raise HTTPException(404, "书籍不存在")
        return self._view(book)

    def owned_record(self, user_id: str, book_id: str):
        book = self.repo.get_owned(user_id, book_id)
        if not book:
            raise HTTPException(404, "书籍不存在")
        return book

    def create(self, user_id: str, *, title, author, language, filename, suffix, source_path):
        book_id, stamp = identifier("book"), now()
        self.repo.create_book((
            book_id, user_id, title, author, language, suffix, filename, str(source_path), stamp, stamp,
        ))
        self.db.book_database(book_id)
        return self._view(self.owned_record(user_id, book_id))

    def delete(self, user_id: str, book_id: str):
        book = self.owned_record(user_id, book_id)
        if DocumentRepository(self.db.book_database(book_id)).has_active_task(book_id):
            raise HTTPException(409, "任务执行中，暂不能删除书籍")
        self.repo.delete_book(book_id)
        remove_chapter_outputs(self.db, book_id)
        return book

    def chapters(self, user_id: str, book_id: str):
        self.owned_record(user_id, book_id)
        return {"chapters": DocumentRepository(self.db.book_database(book_id)).chapters(book_id)}

    def chapter(self, user_id: str, book_id: str, chapter_id: str):
        self.owned_record(user_id, book_id)
        row = DocumentRepository(self.db.book_database(book_id)).chapter(book_id, chapter_id)
        if not row:
            raise HTTPException(404, "章节不存在")
        return row

    def extractions(self, user_id: str, book_id: str):
        self.owned_record(user_id, book_id)
        import json

        rows = DocumentRepository(self.db.book_database(book_id)).extractions(book_id)
        return {"extractions": [{**row, "content": json.loads(row["content"])} for row in rows]}

    def summaries(self, user_id: str, book_id: str):
        import json

        snapshot = self.repo.knowledge_snapshot(
            user_id, book_id, self.db.book_database(book_id),
        )
        if snapshot is None:
            raise HTTPException(404, "书籍不存在")
        book, rows, chapters, pending, storyline = snapshot
        summaries = [
            {**row, "name": SUMMARY_LABELS[row["type"]], "content": json.loads(row["content"])}
            for row in rows
        ]
        chapters_by_title = {}
        for chapter in chapters:
            chapters_by_title.setdefault(chapter["title"], []).append(chapter)
        for summary in summaries:
            for entry in summary["content"]:
                for evidence in entry.get("evidence", []):
                    matches = chapters_by_title.get(evidence.get("chapter"), [])
                    if not evidence.get("chapter_id") and len(matches) == 1:
                        evidence["chapter_id"] = matches[0]["chapter_id"]
                        evidence["chapter_no"] = matches[0]["chapter_no"]
        warnings = []
        for row in chapters:
            for question in json.loads(row["content"]).get("questions", []):
                warnings.append({**question, "chapter_id": row["chapter_id"], "chapter_title": row["title"]})
        return {"summaries": summaries, "revision": book["knowledge_revision"],
                "coverage": [row["chapter_no"] for row in chapters],
                "pending_count": sum(entry.get("needs_review", False) for row in summaries for entry in row["content"])
                + len(pending) + len(warnings),
                "pending_resolutions": pending, "warnings": warnings,
                "storylines": json.loads(storyline["content"]) if storyline else [],
                "storyline_status": storyline["status"] if storyline else "pending"}

    # --- parsing / extraction ---

    def parse_book(self, book):
        text = clean_text(parse_input_to_text(book["source_path"], book["source_type"]))
        if not text.strip():
            raise ValueError("源文件没有可解析的文本；扫描版 PDF 需要先进行 OCR")
        chapters = split_into_chapters(text, filter_noise=False)
        if not chapters:
            raise ValueError("没有有效章节内容")
        text_paths = chapter_output_paths(self.db, book["book_id"], len(chapters))
        book_db = self.db.book_database(book["book_id"])
        with book_db.connect() as conn:
            conn.execute("DELETE FROM chapters WHERE book_id=?", (book["book_id"],))
            for index, chapter in enumerate(chapters, start=1):
                conn.execute(
                    "INSERT INTO chapters "
                    "(id,book_id,chapter_no,title,content,word_count,source_start,source_end,split_method,confidence,text_path) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        identifier("chapter"), book["book_id"], index, chapter["title"], chapter["content"],
                        len(chapter["content"]), chapter["source_start"], chapter["source_end"],
                        chapter["split_method"], chapter["confidence"], str(text_paths[index - 1]),
                    ),
                )
        save_chapter_outputs(self.db, book["book_id"], text, chapters)
        return book_db.all("SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_no", (book["book_id"],))

    def start_parse(self, user_id: str, book_id: str):
        book = self.owned_record(user_id, book_id)
        book_db = self.db.book_database(book_id)
        if DocumentRepository(book_db).has_extractions(book_id):
            raise HTTPException(409, "已存在提取结果，请创建新书籍版本以重新解析")
        task_id = workflow.create_task(book_db, book_id, "parse")
        return book, task_id

    def start_extract(self, user_id: str, book_id: str, max_chapters=None, *, request=None, parent_task_id=None):
        from backend.app.ai.extraction_pipeline import model_fingerprint
        from backend.app.domains.workflow.extraction import input_fingerprint, select_chapters

        book = self.owned_record(user_id, book_id)
        profile = load_function_profile(self.db, user_id, "extraction")
        settings = llm.settings_from_profile(profile)
        request = request or {"max_chapters": max_chapters}
        book_db = self.db.book_database(book_id)
        chapters = book_db.all("SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_no", (book_id,))
        selected = select_chapters(chapters, request) if chapters else []
        if settings["provider"] == "vivo" and not settings["api_key"]:
            raise HTTPException(422, "请先配置模型 API Key")
        task_id = workflow.create_task(
            book_db, book_id, "extract", request, profile["id"], model_fingerprint(settings), parent_task_id,
        )
        if selected:
            book_db.execute("UPDATE tasks SET input_fingerprint=? WHERE id=?", (input_fingerprint(selected), task_id))
        return book, task_id, settings

    def run_extraction(self, book, task_id, task_type, settings=None, max_chapters=None):
        workflow.run_task(self.db.book_database(book["book_id"]), book, task_id, task_type, settings, max_chapters)

    @staticmethod
    def report_error(exc):
        return llm.error_message(exc)

    def resolve_source(self, book, uploads: Path):
        target = Path(book["source_path"]).resolve()
        if uploads.resolve() not in target.parents or not target.is_file():
            raise HTTPException(404, "源文件不存在")
        return target
