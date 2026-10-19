from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse

from backend.app.core.dependencies import current_user, get_config, get_db
from backend.app.db.database import identifier

from .schemas import Credentials, PasswordChange, Profile, RoleSettings
from .service import AuthService

router = APIRouter()

AVATAR_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
AVATAR_LIMIT = 2 * 1024 * 1024


async def _save_upload(request: Request, target: Path, limit: int):
    size = 0
    try:
        with target.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"文件大小不能超过 {limit // (1024 * 1024)} MB")
                output.write(chunk)
        if not size:
            raise HTTPException(422, "文件不能为空")
    except Exception:
        target.unlink(missing_ok=True)
        raise


@router.post("/register", status_code=201)
def register(payload: Credentials, db=Depends(get_db)):
    return AuthService(db).register(payload)


@router.post("/login")
def login(payload: Credentials, request: Request, db=Depends(get_db)):
    days = getattr(request.app.state.config, "session_days", 7)
    return AuthService(db).login(payload, days)


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None), user=Depends(current_user), db=Depends(get_db)):
    return AuthService(db).logout(authorization)


@router.get("/me")
def me(user=Depends(current_user), db=Depends(get_db)):
    return AuthService(db).me(user)


@router.patch("/profile")
def profile(payload: Profile, user=Depends(current_user), db=Depends(get_db)):
    return AuthService(db).update_profile(user, payload)


@router.patch("/role")
def role(payload: RoleSettings, user=Depends(current_user), db=Depends(get_db)):
    return AuthService(db).update_role(user, payload)


@router.put("/password")
def password(payload: PasswordChange, user=Depends(current_user), db=Depends(get_db)):
    return AuthService(db).change_password(user, payload)


@router.post("/avatar")
async def upload_avatar(
    request: Request, filename: str = Query(max_length=255),
    user=Depends(current_user), db=Depends(get_db), config=Depends(get_config),
):
    suffix = Path(filename).suffix.lower()
    if suffix not in AVATAR_SUFFIXES:
        raise HTTPException(422, "头像仅支持 PNG、JPEG、WEBP")
    avatars = config.data_dir / "avatars"
    avatars.mkdir(parents=True, exist_ok=True)
    file_id = identifier("avatar") + suffix
    target = avatars / file_id
    await _save_upload(request, target, AVATAR_LIMIT)
    with target.open("rb") as stream:
        signature = stream.read(12)
    valid = signature.startswith(b"\x89PNG\r\n\x1a\n") if suffix == ".png" else (
        signature.startswith(b"\xff\xd8\xff") if suffix in {".jpg", ".jpeg"} else
        signature.startswith(b"RIFF") and signature[8:12] == b"WEBP"
    )
    if not valid:
        target.unlink(missing_ok=True)
        raise HTTPException(422, "图片内容与扩展名不匹配")
    url = f"/api/v1/avatars/{file_id}"
    AuthService(db).set_avatar(user["user_id"], url)
    return {"avatar_url": url}


@router.get("/avatars/{file_id}")
def avatar(file_id: str, config=Depends(get_config)):
    if not file_id.startswith("avatar_") or Path(file_id).name != file_id:
        raise HTTPException(404)
    target = config.data_dir / "avatars" / file_id
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, headers={"X-Content-Type-Options": "nosniff"})
