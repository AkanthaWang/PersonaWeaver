from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response

from backend.app.core.dependencies import current_user, get_db

from .schemas import CardCreate, CardUpdate, CharacterListResponse, RelationListResponse
from .service import CharacterService

router = APIRouter()


@router.get("/cards")
def list_characters(book_id: Optional[str] = Query(default=None), user=Depends(current_user), db=Depends(get_db)):
    return CharacterService(db).list(user["user_id"], book_id)


@router.post("/cards", status_code=status.HTTP_201_CREATED)
def create_card(payload: CardCreate, user=Depends(current_user), db=Depends(get_db)):
    return CharacterService(db).create(user["user_id"], payload)


@router.patch("/cards/{card_id}")
def update_card(card_id: str, payload: CardUpdate, user=Depends(current_user), db=Depends(get_db)):
    return CharacterService(db).update(user["user_id"], card_id, payload)


@router.delete("/cards/{card_id}")
def delete_card(card_id: str, user=Depends(current_user), db=Depends(get_db)):
    return CharacterService(db).delete(user["user_id"], card_id)


@router.get("/cards/{card_id}/export")
def export_card(card_id: str, user=Depends(current_user), db=Depends(get_db)):
    card = CharacterService(db).export(user["user_id"], card_id)
    return Response(card["content"], media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{card_id}.md"'})


@router.get("/knowledge/characters")
def list_characters_knowledge(book_id: str, user=Depends(current_user), db=Depends(get_db)):
    """获取知识库中的人物列表"""
    characters = CharacterService(db).get_characters(user["user_id"], book_id)
    return CharacterListResponse(characters=characters)


@router.get("/knowledge/relations")
def list_relations_knowledge(book_id: str, user=Depends(current_user), db=Depends(get_db)):
    """获取知识库中的人物关系列表"""
    relations = CharacterService(db).get_relations(user["user_id"], book_id)
    return RelationListResponse(relations=relations)
