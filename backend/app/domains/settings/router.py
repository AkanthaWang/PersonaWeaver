from fastapi import APIRouter, Depends, status

from backend.app.core.dependencies import current_user, get_db

from .service import SettingsService
from .schemas import ModelProfileCreate, ModelProfileUpdate, ModelSelection, ModelSettings

router = APIRouter()


@router.get("/model")
def model_settings(user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).get_model(user["user_id"])


@router.put("/model")
def save_model(payload: ModelSettings, user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).save_model(user["user_id"], payload)


@router.post("/model/test")
def test_model(user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).test_model(user["user_id"])


@router.get("/models")
def list_models(user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).list_profiles(user["user_id"])

@router.get("/selection")
def model_selection(user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).get_selections(user["user_id"])


@router.put("/selection")
def save_selection(payload: ModelSelection, user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).save_selections(user["user_id"], payload)


@router.post("/models/{profile_id}/test")
def test_profile(profile_id: str, user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).test_profile(user["user_id"], profile_id)


@router.post("/models", status_code=status.HTTP_201_CREATED)
def create_model(payload: ModelProfileCreate, user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).save_profile(user["user_id"], payload)


@router.put("/models/{profile_id}")
def update_model(profile_id: str, payload: ModelProfileUpdate, user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).update_profile(user["user_id"], profile_id, payload)


@router.post("/models/{profile_id}/activate")
def activate_model(profile_id: str, user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).activate_profile(user["user_id"], profile_id)


@router.delete("/models/{profile_id}")
def delete_model(profile_id: str, user=Depends(current_user), db=Depends(get_db)):
    return SettingsService(db).delete_profile(user["user_id"], profile_id)
