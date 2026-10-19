from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from backend.app.core.dependencies import current_user, get_db

from .service import WorkflowService

router = APIRouter()


@router.get("/tasks")
def tasks(book_id: Optional[str] = Query(default=None), user=Depends(current_user), db=Depends(get_db)):
    return WorkflowService(db).list_tasks(user["user_id"], book_id)


@router.get("/tasks/{task_id}")
def task(task_id: str, user=Depends(current_user), db=Depends(get_db)):
    return WorkflowService(db).get_task(user["user_id"], task_id)


@router.get("/tasks/{task_id}/units")
def task_units(task_id: str, user=Depends(current_user), db=Depends(get_db)):
    return WorkflowService(db).units(user["user_id"], task_id)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, user=Depends(current_user), db=Depends(get_db)):
    return WorkflowService(db).cancel(user["user_id"], task_id)


@router.post("/tasks/{task_id}/retry", status_code=202)
def retry_task(task_id: str, background: BackgroundTasks, user=Depends(current_user), db=Depends(get_db)):
    from backend.app.domains.documents.service import DocumentService
    book, new_id, settings = WorkflowService(db).retry(user["user_id"], task_id)
    background.add_task(DocumentService(db).run_extraction, book, new_id, "extract", settings)
    return {"task_id": new_id, "status": "pending"}


@router.get("/task-logs")
def logs(
    book_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(current_user), db=Depends(get_db),
):
    return WorkflowService(db).list_logs(user["user_id"], book_id, limit)
