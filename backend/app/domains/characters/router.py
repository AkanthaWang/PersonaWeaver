import hashlib
import html
from functools import lru_cache
from importlib.resources import files
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from backend.app.core.dependencies import current_user, get_db

from .schemas import CardCreate, CardFromCharacter, CardUpdate
from .service import CharacterService

router = APIRouter()


@lru_cache(maxsize=1)
def _dicebear_style():
    from dicebear import Style

    return Style.from_json(
        files("dicebear_styles").joinpath("adventurer-neutral.json").read_text("utf-8")
    )


def _fallback_avatar(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    color = f"#{digest[:6]}"
    initial = html.escape(seed.strip()[:1] or "?")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="16" fill="{color}"/>'
        f'<text x="32" y="40" text-anchor="middle" font-size="28" '
        f'font-family="sans-serif" fill="#ffffff">{initial}</text></svg>'
    )


@router.get("/avatars/dicebear", include_in_schema=False)
def dicebear_avatar(seed: str = Query(min_length=1, max_length=200)):
    seed = seed.strip()
    if not seed:
        raise HTTPException(status_code=400, detail="头像种子不能为空")
    try:
        from dicebear import Avatar

        svg = Avatar(_dicebear_style(), {"seed": seed}).to_string()
    except ModuleNotFoundError:
        svg = _fallback_avatar(seed)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="人物头像生成失败") from exc
    return Response(
        svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/cards")
def list_characters(book_id: Optional[str] = Query(default=None), user=Depends(current_user), db=Depends(get_db)):
    return CharacterService(db).list(user["user_id"], book_id)


@router.post("/cards", status_code=status.HTTP_201_CREATED)
def create_card(payload: CardCreate, user=Depends(current_user), db=Depends(get_db)):
    return CharacterService(db).create(user["user_id"], payload)


@router.post("/cards/from-character")
def create_card_from_character(payload: CardFromCharacter, user=Depends(current_user), db=Depends(get_db)):
    return CharacterService(db).from_character(user["user_id"], payload)


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
