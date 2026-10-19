import json
import logging
import sqlite3

from fastapi import HTTPException

from backend.app.db.database import identifier, now
from backend.app.domains.documents.chapter_storage import chapter_output_paths, save_chapter_outputs
from backend.app.domains.documents.parsing.chapter_chunker import split_into_chapters
from backend.app.domains.documents.parsing.parsers import parse_input_to_text
from backend.app.domains.documents.parsing.text_cleaner import clean_text
from backend.app.domains.settings import llm


logger = logging.getLogger(__name__)


def owned_book(db, user_id, book_id):
    book = db.one("SELECT * FROM books WHERE book_id=? AND user_id=?", (book_id, user_id))
    if not book:
        raise HTTPException(404, "书籍不存在")
    return book


def create_task(db, book_id, task_type, request=None, profile_id=None, fingerprint=None, parent_task_id=None):
    task_id, stamp = identifier("task"), now()
    try:
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO tasks(id,book_id,task_type,created_at,updated_at,request_json,model_profile_id,"
                "config_fingerprint,parent_task_id) VALUES(?,?,?,?,?,?,?,?,?)",
                (task_id, book_id, task_type, stamp, stamp, json.dumps(request or {}), profile_id, fingerprint, parent_task_id),
            )
            conn.execute(
                "UPDATE books SET status='processing',progress=0,err_message=NULL,updated_at=? WHERE book_id=?",
                (stamp, book_id),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "该书籍已有正在执行的任务") from exc
    return task_id


def progress(db, task_id, book_id, percent, step, status="running", error=None):
    with db.connect() as conn:
        stamp = now()
        conn.execute(
            "UPDATE tasks SET status=?,progress=?,current_step=?,error_message=?,updated_at=? WHERE id=?",
            (status, percent, step, error, stamp, task_id),
        )
        book_status = "parsed" if status in {"completed", "completed_with_warnings", "cancelled"} else "failed" if status == "failed" else "processing"
        conn.execute(
            "UPDATE books SET status=?,progress=?,err_message=?,updated_at=? WHERE book_id=?",
            (book_status, percent, error, stamp, book_id),
        )
        conn.execute(
            "INSERT INTO task_logs VALUES(?,?,?,?,?)",
            (identifier("log"), task_id, "error" if error else "info", step, stamp),
        )


def parse_book(db, book):
    text = clean_text(parse_input_to_text(book["source_path"], book["source_type"]))
    if not text.strip():
        raise ValueError("源文件没有可解析的文本；扫描版 PDF 需要先进行 OCR")
    chapters = split_into_chapters(text, filter_noise=False)
    if not chapters:
        raise ValueError("没有有效章节内容")
    text_paths = chapter_output_paths(db, book["book_id"], len(chapters))
    with db.connect() as conn:
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
    save_chapter_outputs(db, book["book_id"], text, chapters)
    return db.all("SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_no", (book["book_id"],))


def run_task(db, book, task_id, task_type, settings=None, max_chapters=None):
    book_id = book["book_id"]
    try:
        if task_type == "extract":
            from .extraction import Cancelled
            task = db.one("SELECT cancel_requested FROM tasks WHERE id=?", (task_id,))
            if task["cancel_requested"]:
                raise Cancelled()
        progress(db, task_id, book_id, 5, "正在解析源文件")
        chapters = db.all("SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_no", (book_id,))
        if task_type == "parse" or not chapters:
            chapters = parse_book(db, book)
        if task_type == "parse":
            progress(db, task_id, book_id, 100, f"解析完成，共 {len(chapters)} 个章节", "completed")
            return
        from .extraction import ExtractionWorker
        ExtractionWorker(db, book, task_id, settings).run(chapters)
    except Exception as exc:
        from .extraction import Cancelled
        if isinstance(exc, Cancelled):
            progress(db, task_id, book_id, 0, "已取消，检查点已保留", "cancelled")
            return
        logger.exception("Task %s failed", task_id)
        progress(db, task_id, book_id, 0, llm.error_message(exc), "failed", llm.error_message(exc))
