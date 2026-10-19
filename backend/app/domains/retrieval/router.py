from fastapi import APIRouter, Depends

from backend.app.core.dependencies import current_user, get_db

from .schemas import RetrievalQuery
from .service import RetrievalService

router = APIRouter()


@router.post("/search")
def search(payload: RetrievalQuery, user=Depends(current_user), db=Depends(get_db)):
    return RetrievalService(db).search(user["user_id"], payload.query, payload.book_id, payload.limit)
