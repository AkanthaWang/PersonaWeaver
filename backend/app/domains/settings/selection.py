import logging

from fastapi import HTTPException

from . import llm
from .repository import SettingsRepository


logger = logging.getLogger(__name__)
FUNCTIONS = {
    "extraction": ("llm", "提取模型"),
    "embedding": ("embedding", "Embedding 模型"),
    "reranker": ("reranker", "Reranker 模型"),
}
DEFAULT_SELECTION = {
    "extraction_model_id": None, "embedding_model_id": None,
    "reranker_model_id": None, "reranker_top_k": 5,
}


def selection_status(repo, user_id, function, profile_id):
    model_type, label = FUNCTIONS[function]
    if not profile_id:
        return {"status": "disabled" if function == "reranker" else "unconfigured",
                "message": "未启用" if function == "reranker" else "尚未选择模型", "model": None}
    profile = repo.profile_for_user(user_id, profile_id)
    if not profile:
        return {"status": "missing", "message": "该模型已被删除，请重新选择", "model": None}
    summary = {"id": profile["id"], "name": profile["name"], "model": profile["model"],
               "provider_name": profile["provider_name"] or profile["provider"]}
    if profile["model_type"] != model_type:
        status, message = "invalid", f"模型类型不匹配，请重新选择{label}"
    elif profile["test_status"] == "failed":
        status, message = "failed", "该模型连接失败，请前往「模型设置」重新测试"
    elif profile["test_status"] != "passed":
        status, message = "untested", "该模型尚未通过连接测试，请前往「模型设置」测试"
    else:
        status, message = "healthy", "正常"
    return {"status": status, "message": message, "model": summary}


def load_function_profile(db, user_id, function):
    repo = SettingsRepository(db)
    values = repo.selections(user_id) or DEFAULT_SELECTION
    profile_id = values[f"{function}_model_id"]
    status = selection_status(repo, user_id, function, profile_id)
    if status["status"] == "disabled":
        return None
    if status["status"] != "healthy":
        message = f"{FUNCTIONS[function][1]}：{status['message']}。请前往「偏好设置 → 模型选用」重新绑定。"
        logger.error("Model selection unavailable: %s (user=%s, profile=%s)", message, user_id, profile_id)
        raise HTTPException(422, message)
    return repo.profile_for_user(user_id, profile_id)


def load_function_settings(db, user_id, function):
    profile = load_function_profile(db, user_id, function)
    return llm.settings_from_profile(profile) if profile else None
