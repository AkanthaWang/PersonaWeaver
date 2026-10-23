import asyncio

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.app.core.dependencies import current_user, get_db

from .schemas import ActiveNodeRequest, CompactRequest, ConversationCreate, ConversationUpdate, LabelRequest, MessageRequest, ContextPreview
from .service import ConversationService
from .memories import MemoryInput

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
async def delete_conversation(conversation_id: str, request: Request, user=Depends(current_user), db=Depends(get_db)):
    result = await asyncio.to_thread(ConversationService(db).delete, user["user_id"], conversation_id)
    await request.app.state.conversation_engine.memory.cancel_conversation(conversation_id)
    return result


@router.delete("/conversations/{conversation_id}/messages")
async def clear_messages(conversation_id: str, request: Request, user=Depends(current_user), db=Depends(get_db)):
    result = await asyncio.to_thread(ConversationService(db).clear, user["user_id"], conversation_id)
    await request.app.state.conversation_engine.memory.cancel_conversation(conversation_id)
    return result


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
            while not live.task.done():
                if await request.is_disconnected():
                    await engine.cancel(user["user_id"], conversation_id, live.request_id, "interrupted")
                    break
                await asyncio.wait({live.task}, timeout=.15)
            await asyncio.shield(live.task)
        except asyncio.CancelledError:
            await engine.cancel(user["user_id"], conversation_id, live.request_id, "interrupted")
            raise
    result = engine.result(user["user_id"], conversation_id, live.request_id)
    if result["status"] == "running":
        raise HTTPException(503, f"回复持久化未完成，请保留请求 ID {live.request_id} 并查询或重连",
                            headers={"X-Request-ID": live.request_id})
    if not result["reply"] and result["status"] != "completed":
        raise HTTPException(502, result["error"] or "生成未完成", headers={"X-Request-ID": live.request_id})
    return result


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(conversation_id: str, payload: MessageRequest, request: Request, user=Depends(current_user)):
    engine = request.app.state.conversation_engine
    live = await engine.start(user["user_id"], conversation_id, payload, user.get("prompt", ""))
    return StreamingResponse(engine.events(live), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations/{conversation_id}/generations")
def recent_generations(conversation_id: str, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.recent(user["user_id"], conversation_id)


@router.get("/conversations/{conversation_id}/generations/{request_id}")
def generation_status(conversation_id: str, request_id: str, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.public(user["user_id"], conversation_id, request_id)


@router.post("/conversations/{conversation_id}/generations/{request_id}/cancel")
async def cancel_generation(conversation_id: str, request_id: str, request: Request, user=Depends(current_user)):
    return await request.app.state.conversation_engine.cancel(user["user_id"], conversation_id, request_id)


@router.get("/conversations/{conversation_id}/generations/{request_id}/trace")
def generation_trace(conversation_id: str, request_id: str, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.trace(user["user_id"], conversation_id, request_id)


@router.post("/conversations/{conversation_id}/generations/{request_id}/resume")
async def resume_generation(conversation_id: str, request_id: str, request: Request, user=Depends(current_user)):
    live = await request.app.state.conversation_engine.resume(user["user_id"], conversation_id, request_id)
    return StreamingResponse(request.app.state.conversation_engine.events(live), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/{conversation_id}/context-preview")
def context_preview(conversation_id: str, payload: ContextPreview, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.preview(user["user_id"], conversation_id, payload, user.get("prompt", ""))


@router.get("/conversations/{conversation_id}/memories")
def memories(conversation_id: str, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.memory.list(user["user_id"], conversation_id)


@router.post("/conversations/{conversation_id}/memories", status_code=201)
def create_memory(conversation_id: str, payload: MemoryInput, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.memory.mutate(user["user_id"], conversation_id, payload)


@router.put("/conversations/{conversation_id}/memories/{memory_id}")
def edit_memory(conversation_id: str, memory_id: str, payload: MemoryInput, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.memory.mutate(user["user_id"], conversation_id, payload, memory_id)


@router.delete("/conversations/{conversation_id}/memories/{memory_id}")
def delete_memory(conversation_id: str, memory_id: str, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.memory.mutate(
        user["user_id"], conversation_id, memory_id=memory_id, operation="delete")


@router.post("/conversations/{conversation_id}/memories/{memory_id}/undo")
def undo_memory(conversation_id: str, memory_id: str, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.memory.mutate(
        user["user_id"], conversation_id, memory_id=memory_id, operation="undo")


@router.post("/conversations/{conversation_id}/memory-jobs/{job_id}/retry")
async def retry_memory(conversation_id: str, job_id: str, request: Request, user=Depends(current_user)):
    return request.app.state.conversation_engine.memory.retry(user["user_id"], conversation_id, job_id)
