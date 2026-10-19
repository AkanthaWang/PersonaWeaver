from __future__ import annotations
from fastapi import HTTPException

from .repository import WorkflowRepository


class WorkflowService:
    def __init__(self, db):
        self.db = db
        self.repo = WorkflowRepository(db)

    def list_tasks(self, user_id: str, book_id: str | None = None):
        return {"tasks": self.repo.tasks(user_id, book_id)}

    def get_task(self, user_id: str, task_id: str):
        row = self.repo.task(user_id, task_id)
        if not row:
            raise HTTPException(404, "任务不存在")
        return row

    def list_logs(self, user_id: str, book_id: str | None = None, limit: int = 50):
        return {"logs": self.repo.logs(user_id, book_id, limit)}

    def units(self, user_id, task_id):
        import json

        self.get_task(user_id, task_id)
        rows = self.db.all("SELECT * FROM extraction_units WHERE task_id=? ORDER BY created_at,id", (task_id,))
        # Full model payloads can be large; return diagnostics and counts only.
        return {"units": [
            {**{k: v for k, v in row.items() if k != "payload"},
             "fact_count": sum(len(json.loads(row["payload"]).get(k, [])) for k in
                               ("characters", "items", "storyline_events", "world_locations")) if row["payload"] else 0}
            for row in rows
        ]}

    def cancel(self, user_id, task_id):
        task = self.get_task(user_id, task_id)
        if task["task_type"] != "extract":
            raise HTTPException(422, "仅资料提取任务支持取消")
        changed = self.db.execute(
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
        settings = load_function_settings(self.db, user_id, "extraction")
        request = json.loads(task["request_json"])
        chapters = self.db.all("SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_no", (task["book_id"],))
        if not task["config_fingerprint"] or model_fingerprint(settings) != task["config_fingerprint"]:
            raise HTTPException(409, "模型配置已改变，请重新发起提取")
        if task["input_fingerprint"] and input_fingerprint(select_chapters(chapters, request)) != task["input_fingerprint"]:
            raise HTTPException(409, "章节原文已改变，请重新发起提取")
        return DocumentService(self.db).start_extract(user_id, task["book_id"], request=request, parent_task_id=task_id)
