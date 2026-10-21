import asyncio

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.app.core.dependencies import current_user, get_db

from .schemas import ActiveNodeRequest, CompactRequest, ConversationCreate, ConversationUpdate, LabelRequest, MessageRequest, ContextPreview
from .service import ConversationService

router = APIRouter()


@router.get("/conversations")
def list_conversations(user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).list(user["user_id"])


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).create(user["user_id"], payload)


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).get(user["user_id"], conversation_id)


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationUpdate, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).rename(user["user_id"], conversation_id, payload)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).delete(user["user_id"], conversation_id)


@router.delete("/conversations/{conversation_id}/messages")
def clear_messages(conversation_id: str, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).clear(user["user_id"], conversation_id)


@router.patch("/conversations/{conversation_id}/active-node")
def set_active_node(conversation_id: str, payload: ActiveNodeRequest, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).set_active_node(user["user_id"], conversation_id, payload)


@router.post("/conversations/{conversation_id}/compact")
def compact_conversation(conversation_id: str, payload: CompactRequest, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).compact(user["user_id"], conversation_id, payload)


@router.post("/conversations/{conversation_id}/fork")
def fork_conversation(conversation_id: str, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).fork(user["user_id"], conversation_id)


@router.put("/conversations/{conversation_id}/nodes/{node_id}/label")
def set_label(conversation_id: str, node_id: str, payload: LabelRequest, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).set_label(user["user_id"], conversation_id, node_id, payload.label)


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, payload: MessageRequest, request: Request, user=Depends(current_user)):
    engine = request.app.state.conversation_engine
    live = await engine.start(user["user_id"], conversation_id, payload, user.get("prompt", ""))
    if live.task:
        try:
            await asyncio.shield(live.task)
        except asyncio.CancelledError:
            await engine.cancel(user["user_id"], conversation_id, live.request_id, "interrupted")
            raise
    result = engine.result(user["user_id"], conversation_id, live.request_id)
    if not result["reply"] and result["status"] != "completed":
        raise HTTPException(502, result["error"] or "生成未完成")
    return result


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(conversation_id: str, payload: MessageRequest, request: Request, user=Depends(current_user)):
    engine = request.app.state.conversation_engine
    live = await engine.start(user["user_id"], conversation_id, payload, user.get("prompt", ""))
    return StreamingResponse(engine.events(live), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations/{conversation_id}/generations/{request_id}")
def generation_status(conversation_id: str, request_id: str, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.public(user["user_id"], conversation_id, request_id)


@router.post("/conversations/{conversation_id}/generations/{request_id}/cancel")
async def cancel_generation(conversation_id: str, request_id: str, request: Request, user=Depends(current_user)):
    return await request.app.state.conversation_engine.cancel(user["user_id"], conversation_id, request_id)


@router.post("/conversations/{conversation_id}/context-preview")
def context_preview(conversation_id: str, payload: ContextPreview, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.preview(user["user_id"], conversation_id, payload, user.get("prompt", ""))
