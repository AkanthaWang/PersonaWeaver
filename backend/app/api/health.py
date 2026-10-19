from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request):
    request.app.state.db.one("SELECT 1")
    return {"status": "ok", "storage": "sqlite", "version": "3.0.0", "model_config_version": "ecnu-env-v1"}
