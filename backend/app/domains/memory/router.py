from fastapi import APIRouter, Depends, Request

from backend.app.core.dependencies import current_user

from .schemas import MemorySearch
from .service import MemoryService

router = APIRouter()


@router.post("/memory/search")
def search(payload: MemorySearch, request: Request, user=Depends(current_user)):
    if not payload.conversation_id:
        return MemoryService().search(payload.query)
    result = request.app.state.conversation_engine.memory.list(user["user_id"], payload.conversation_id)
    return {"query": payload.query, "items": [v for v in result["items"] if not v["deleted"] and
            payload.query.casefold() in (v["memory_key"] + v["content"]).casefold()]}
