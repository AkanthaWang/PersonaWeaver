from datetime import datetime, timezone
import json
import uuid

from fastapi import HTTPException

from backend.app.domains.settings import llm
from backend.app.ai.providers.settings_store import AgentSettingsStore
from backend.app.ai.providers import retrieval

from .repository import SettingsRepository
from .selection import DEFAULT_SELECTION, FUNCTIONS, selection_status


class SettingsService:
    def __init__(self, db):
        self.repo = SettingsRepository(db)
        self.store = AgentSettingsStore(db.path.parent)

    def get_model(self, user_id: str):
        return llm.public_settings(llm.load_settings(self.repo.database, user_id))

    def save_model(self, user_id: str, payload):
        settings = payload.model_dump()
        if settings["api_key"] is None:
            settings["api_key"] = llm.load_settings(self.repo.database, user_id)["api_key"]
        self.repo.save_model(user_id, settings)
        self.store.set_user_model(user_id, settings)
        # Keep the active saved profile aligned with the legacy settings endpoint.
        active = self.repo.active_profile_for_user(user_id)
        if active:
            self.repo.sync_active_profile(user_id, active["id"], settings)
            self.repo.execute("UPDATE model_profiles SET context_window=? WHERE id=?",
                              (settings["context_window"], active["id"]))
        return llm.public_settings(settings)

    def test_model(self, user_id: str):
        active = self.repo.active_profile_for_user(user_id)
        if active:
            return self.test_profile(user_id, active["id"])
        try:
            reply = llm.chat(llm.load_settings(self.repo.database, user_id), [{"role": "user", "content": "请回复 OK"}])
        except Exception as exc:
            raise HTTPException(502, llm.error_message(exc)) from exc
        return {"ok": True, "response": reply}

    def test_profile(self, user_id: str, profile_id: str):
        profile = self.repo.profile_for_user(user_id, profile_id)
        if not profile:
            raise HTTPException(404, "模型配置不存在")
        settings = llm.settings_from_profile(profile)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            if profile["model_type"] == "embedding":
                vector = retrieval.embed(settings, ["连接测试"])[0]
                reply = f"Embedding 连接正常，向量维度：{len(vector)}"
            elif profile["model_type"] == "reranker":
                retrieval.rerank(settings, "连接测试", ["连接测试文档"], 1)
                reply = "Reranker 连接正常"
            else:
                reply = llm.chat(settings, [{"role": "user", "content": "请回复 OK"}])
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError("模型返回空回复")
        except Exception as exc:
            message = llm.error_message(exc)
            self.repo.record_test(user_id, profile, "failed", message, timestamp)
            raise HTTPException(502, message) from exc
        if not self.repo.record_test(user_id, profile, "passed", reply[:500], timestamp):
            raise HTTPException(409, "测试期间模型配置发生变化，请重新测试")
        return {"ok": True, "response": reply, "profile_id": profile_id}

    def get_selections(self, user_id: str):
        saved = self.repo.selections(user_id)
        values = {key: saved[key] for key in DEFAULT_SELECTION} if saved else dict(DEFAULT_SELECTION)
        return {**values, "statuses": {
            function: selection_status(self.repo, user_id, function, values[f"{function}_model_id"])
            for function in FUNCTIONS
        }}

    def save_selections(self, user_id: str, payload):
        values = payload.model_dump()
        # Validate and persist against the same database snapshot.
        with self.repo.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for function, (model_type, label) in FUNCTIONS.items():
                profile_id = values[f"{function}_model_id"]
                if profile_id is None:
                    continue
                row = conn.execute("SELECT * FROM model_profiles WHERE user_id=? AND id=?", (user_id, profile_id)).fetchone()
                if not row:
                    raise HTTPException(422, f"{label}已被删除，请重新选择")
                if row["model_type"] != model_type or row["test_status"] != "passed":
                    raise HTTPException(422, f"{label}类型不匹配或尚未通过连接测试，请重新选择")
            conn.execute(
                "INSERT INTO model_selections(user_id,extraction_model_id,embedding_model_id,reranker_model_id,reranker_top_k) "
                "VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                "extraction_model_id=excluded.extraction_model_id,embedding_model_id=excluded.embedding_model_id,"
                "reranker_model_id=excluded.reranker_model_id,reranker_top_k=excluded.reranker_top_k",
                (user_id, values["extraction_model_id"], values["embedding_model_id"],
                 values["reranker_model_id"], values["reranker_top_k"]),
            )
        return self.get_selections(user_id)

    @staticmethod
    def _public(profile):
        result = {key: value for key, value in profile.items() if key not in {"api_key", "user_id", "headers_json"}}
        result["has_api_key"] = bool(profile.get("api_key"))
        result["active"] = bool(profile.get("active"))
        result["headers"] = json.loads(profile.get("headers_json") or "{}")
        if not result.get("provider_name"):
            result["provider_name"] = {
                "ollama": "Ollama", "remote_api": "OpenAI", "openai_responses": "OpenAI Responses", "vivo": "vivo",
            }.get(result.get("provider"), result.get("provider", "Provider"))
        return result

    def list_profiles(self, user_id: str):
        if not self.repo.profiles_for_user(user_id):
            current = self.repo.model_for_user(user_id)
            if current:
                profile_id = f"model_{uuid.uuid4().hex}"
                timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
                values = {
                    "id": profile_id, "user_id": user_id, "name": "当前配置",
                    "provider": current["provider"], "base_url": current["base_url"], "model": current["model"],
                    "provider_name": "", "api_protocol": "", "headers_json": "{}",
                    "model_type": "llm",
                    "api_key": current["api_key"], "temperature": current["temperature"], "top_p": current["top_p"],
                    "max_tokens": current["max_tokens"], "timeout_seconds": current["timeout_seconds"],
                    "created_at": timestamp, "updated_at": timestamp,
                }
                self.repo.create_profile(values)
                self.repo.activate_profile(user_id, values)
        return {"models": [self._public(profile) for profile in self.repo.profiles_for_user(user_id)]}

    def save_profile(self, user_id: str, payload):
        values = payload.model_dump()
        source_id = values.pop("source_profile_id", None)
        if source_id and values["api_key"] is None:
            source = self.repo.profile_for_user(user_id, source_id)
            if not source or any(source[field] != values[field] for field in ("provider_name", "base_url", "provider")):
                raise HTTPException(422, "服务商配置已变化，请重新填写 API Key")
            values["api_key"] = source["api_key"]
        profile_id = f"model_{uuid.uuid4().hex}"
        timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        values.update(id=profile_id, user_id=user_id, api_key=values.get("api_key") or "", created_at=timestamp, updated_at=timestamp)
        values["headers_json"] = json.dumps(values.pop("headers", {}), ensure_ascii=False)
        try:
            self.repo.create_profile(values)
            self.repo.execute("UPDATE model_profiles SET context_window=? WHERE id=?",
                              (values["context_window"], profile_id))
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(409, "配置名称已存在") from exc
            raise
        profile = self.repo.profile_for_user(user_id, profile_id)
        should_activate = payload.activate and values["model_type"] == "llm"
        if should_activate:
            self.repo.activate_profile(user_id, profile)
            profile = self.repo.profile_for_user(user_id, profile_id)
            self.store.set_user_model(user_id, llm.settings_from_profile(profile))
        return self._public({**profile, "active": should_activate})

    def update_profile(self, user_id: str, profile_id: str, payload):
        current = self.repo.profile_for_user(user_id, profile_id)
        if not current:
            raise HTTPException(404, "模型配置不存在")
        values = payload.model_dump()
        values.update(api_key=current["api_key"] if values.get("api_key") is None else values["api_key"] or "")
        values["headers_json"] = json.dumps(values.pop("headers", {}), ensure_ascii=False)
        values["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        changed = any(values[field] != current[field] for field in (
            "provider", "provider_name", "api_protocol", "headers_json", "base_url", "model", "api_key", "model_type",
        ))
        values.update(
            test_status="untested" if changed else current["test_status"],
            test_message="" if changed else current["test_message"],
            tested_at=None if changed else current["tested_at"],
        )
        active = self.repo.active_profile_for_user(user_id)
        was_active = bool(active and active["id"] == profile_id)
        if was_active and values["model_type"] != "llm":
            raise HTTPException(409, "当前对话模型不能改为其他类型，请先切换对话模型")
        try:
            self.repo.update_profile(user_id, profile_id, values)
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise HTTPException(409, "配置名称已存在") from exc
            raise
        profile = self.repo.profile_for_user(user_id, profile_id)
        should_activate = values["model_type"] == "llm" and (payload.activate or was_active)
        if should_activate:
            self.repo.activate_profile(user_id, profile)
            profile = self.repo.profile_for_user(user_id, profile_id)
            self.store.set_user_model(user_id, llm.settings_from_profile(profile))
        profile["active"] = should_activate
        return self._public(profile)

    def activate_profile(self, user_id: str, profile_id: str):
        profile = self.repo.profile_for_user(user_id, profile_id)
        if not profile:
            raise HTTPException(404, "模型配置不存在")
        if profile["model_type"] != "llm":
            raise HTTPException(422, "只有大语言模型可以设为当前对话模型")
        self.repo.activate_profile(user_id, profile)
        self.store.set_user_model(user_id, llm.settings_from_profile(profile))
        return self._public({**profile, "active": True})

    def delete_profile(self, user_id: str, profile_id: str):
        profile = self.repo.profile_for_user(user_id, profile_id)
        if not profile:
            raise HTTPException(404, "模型配置不存在")
        active = self.repo.active_profile_for_user(user_id)
        if active and active["id"] == profile_id:
            raise HTTPException(409, "当前配置正在使用，请先切换到其他配置")
        self.repo.delete_profile(user_id, profile_id)
        return {"ok": True}
