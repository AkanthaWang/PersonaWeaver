from typing import Literal, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class ModelSettings(BaseModel):
    provider: Literal["ollama", "remote_api", "openai_responses", "vivo"] = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = Field(default="qwen2.5:7b", min_length=1, max_length=120)
    api_key: Optional[str] = Field(default=None, max_length=1000)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.9, gt=0, le=1)
    max_tokens: int = Field(default=2048, ge=128, le=16384)
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    context_window: int = Field(default=32768, ge=512, le=2000000)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("模型地址必须是 HTTP/HTTPS URL，且不能包含凭据")
        if parsed.query or parsed.fragment:
            raise ValueError("模型地址不能包含查询参数")
        return value.strip().rstrip("/")

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        if not value.strip():
            raise ValueError("模型名称不能为空")
        return value.strip()


class ModelProfileCreate(ModelSettings):
    name: str = Field(min_length=1, max_length=80)
    provider_name: str = Field(default="", max_length=80)
    api_protocol: str = Field(default="", max_length=40)
    headers: dict[str, str] = Field(default_factory=dict)
    model_type: Literal["llm", "embedding", "reranker"] = "llm"
    source_profile_id: Optional[str] = Field(default=None, max_length=100)
    activate: bool = True


class ModelProfileUpdate(ModelSettings):
    name: str = Field(min_length=1, max_length=80)
    provider_name: str = Field(default="", max_length=80)
    api_protocol: str = Field(default="", max_length=40)
    headers: dict[str, str] = Field(default_factory=dict)
    model_type: Literal["llm", "embedding", "reranker"] = "llm"
    activate: bool = False


class ModelProfileRename(BaseModel):
    name: str = Field(min_length=1, max_length=80)

class ModelSelection(BaseModel):
    extraction_model_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    embedding_model_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    reranker_model_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    reranker_top_k: int = Field(default=5, ge=1, le=100)


__all__ = ["ModelSettings", "ModelProfileCreate", "ModelProfileUpdate", "ModelProfileRename", "ModelSelection"]
