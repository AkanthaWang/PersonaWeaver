from __future__ import annotations
from fastapi import HTTPException

from .repository import WorkflowRepository


class WorkflowService:
    def __init__(self, db):
        self.db = db
        self.repo = WorkflowRepository(db)

    def list_tasks(self, user_id: str, book_id: str | None = None):
        books = self.db.all(
            "SELECT book_id,title FROM books WHERE user_id=?" + (" AND book_id=?" if book_id else ""),
            (user_id, book_id) if book_id else (user_id,),
        )
        tasks = []
        for book in books:
            rows = self.db.book_database(book["book_id"]).all(
                "SELECT * FROM tasks WHERE book_id=? ORDER BY created_at DESC LIMIT 200",
                (book["book_id"],),
            )
            tasks.extend({**row, "book_title": book["title"]} for row in rows)
        tasks.sort(key=lambda row: row["created_at"], reverse=True)
        return {"tasks": tasks[:200]}

    def _task(self, user_id: str, task_id: str):
        for book in self.db.all("SELECT book_id,title FROM books WHERE user_id=?", (user_id,)):
            task = self.db.book_database(book["book_id"]).one(
                "SELECT * FROM tasks WHERE id=?", (task_id,),
            )
            if task:
                return {**task, "book_title": book["title"]}
        return None

    def get_task(self, user_id: str, task_id: str):
        row = self._task(user_id, task_id)
        if not row:
            raise HTTPException(404, "任务不存在")
        return row

    def list_logs(self, user_id: str, book_id: str | None = None, limit: int = 50):
        logs = []
        for task in self.list_tasks(user_id, book_id)["tasks"]:
            logs.extend(self.db.book_database(task["book_id"]).all(
                "SELECT * FROM task_logs WHERE task_id=? ORDER BY created_at DESC",
                (task["id"],),
            ))
        logs.sort(key=lambda row: row["created_at"], reverse=True)
        return {"logs": logs[:limit]}

    def units(self, user_id, task_id):
        import json

        task = self.get_task(user_id, task_id)
        rows = self.db.book_database(task["book_id"]).all(
            "SELECT u.*,c.chapter_no,c.title AS chapter_title FROM extraction_units u "
            "LEFT JOIN chapters c ON c.id=u.chapter_id WHERE u.task_id=? ORDER BY u.created_at,u.id", (task_id,),
        )
        # Full model payloads can be large; return diagnostics and counts only.
        units = []
        for row in rows:
            payload = json.loads(row["payload"]) if row["payload"] else {}
            units.append({
                **{k: v for k, v in row.items() if k != "payload"},
                "fact_count": sum(len(payload.get(k, [])) for k in
                                  ("characters", "items", "storyline_events", "world_locations")),
                "recovery_tool": payload.get("tool") if row["kind"] == "agent" else None,
            })
        return {"units": units}

    def cancel(self, user_id, task_id):
        task = self.get_task(user_id, task_id)
        if task["task_type"] != "extract":
            raise HTTPException(422, "仅资料提取任务支持取消")
        changed = self.db.book_database(task["book_id"]).execute(
            "UPDATE tasks SET cancel_requested=1 WHERE id=? AND status IN ('pending','running')", (task_id,),
        )
        if not changed:
            raise HTTPException(409, "任务已结束")
        return self.get_task(user_id, task_id)

    def retry(self, user_id, task_id):
        import json

        from backend.app.ai.extraction_pipeline import model_fingerprint
        from backend.app.domains.documents.service import DocumentService
        from backend.app.domains.settings.selection import load_function_settings
        from .extraction import input_fingerprint, select_chapters

        task = self.get_task(user_id, task_id)
        if task["task_type"] != "extract" or task["status"] not in {"failed", "cancelled", "completed_with_warnings"}:
            raise HTTPException(409, "仅失败、已取消或有警告的提取任务可以续跑")
        book_db = self.db.book_database(task["book_id"])
        settings = load_function_settings(self.db, user_id, "extraction")
        request = json.loads(task["request_json"])
        chapters = book_db.all("SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_no", (task["book_id"],))
        if not task["config_fingerprint"] or model_fingerprint(settings) != task["config_fingerprint"]:
            raise HTTPException(409, "模型配置已改变，请重新发起提取")
        if task["input_fingerprint"] and input_fingerprint(select_chapters(chapters, request)) != task["input_fingerprint"]:
            raise HTTPException(409, "章节原文已改变，请重新发起提取")
        return DocumentService(self.db).start_extract(user_id, task["book_id"], request=request, parent_task_id=task_id)
