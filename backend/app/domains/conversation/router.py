from fastapi import APIRouter, Depends, status

from backend.app.core.dependencies import current_user, get_db

from .schemas import ActiveNodeRequest, CompactRequest, ConversationCreate, ConversationUpdate, LabelRequest, MessageRequest
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
def send_message(conversation_id: str, payload: MessageRequest, user=Depends(current_user), db=Depends(get_db)):
    return ConversationService(db).send(user["user_id"], conversation_id, payload, user.get("prompt", ""))
