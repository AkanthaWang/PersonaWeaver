from fastapi import APIRouter, Depends

from backend.app.core.dependencies import current_user

from .schemas import MemorySearch
from .service import MemoryService

router = APIRouter()


@router.post("/memory/search")
def search(payload: MemorySearch, user=Depends(current_user)):
    return MemoryService().search(payload.query)
