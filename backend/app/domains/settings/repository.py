from backend.app.db.base_repository import SQLiteRepository


class SettingsRepository(SQLiteRepository):
    def model_for_user(self, user_id: str):
        return self.one("SELECT * FROM model_settings WHERE user_id=?", (user_id,))

    def profiles_for_user(self, user_id: str):
        return self.all(
            "SELECT p.*, s.active_profile_id = p.id AS active "
            "FROM model_profiles p LEFT JOIN model_profile_state s ON s.user_id=p.user_id "
            "WHERE p.user_id=? ORDER BY p.updated_at DESC, p.created_at DESC",
            (user_id,),
        )

    def profile_for_user(self, user_id: str, profile_id: str):
        return self.one("SELECT * FROM model_profiles WHERE user_id=? AND id=?", (user_id, profile_id))

    def active_profile_for_user(self, user_id: str):
        return self.one(
            "SELECT p.* FROM model_profiles p JOIN model_profile_state s ON s.active_profile_id=p.id "
            "WHERE s.user_id=?",
            (user_id,),
        )

    def create_profile(self, values):
        return self.execute(
            "INSERT INTO model_profiles "
            "(id,user_id,name,provider,provider_name,api_protocol,headers_json,base_url,model,api_key,temperature,top_p,max_tokens,timeout_seconds,created_at,updated_at,model_type) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(values[key] for key in (
                "id", "user_id", "name", "provider", "provider_name", "api_protocol", "headers_json", "base_url", "model", "api_key",
                "temperature", "top_p", "max_tokens", "timeout_seconds", "created_at", "updated_at", "model_type",
            )),
        )

    def update_profile(self, user_id: str, profile_id: str, values):
        return self.execute(
            "UPDATE model_profiles SET name=?,provider=?,provider_name=?,api_protocol=?,headers_json=?,base_url=?,model=?,api_key=?,temperature=?,top_p=?," 
            "max_tokens=?,timeout_seconds=?,updated_at=?,model_type=?,test_status=?,test_message=?,tested_at=? WHERE user_id=? AND id=?",
            (values["name"], values["provider"], values["provider_name"], values["api_protocol"], values["headers_json"], values["base_url"], values["model"], values["api_key"],
             values["temperature"], values["top_p"], values["max_tokens"], values["timeout_seconds"],
             values["updated_at"], values["model_type"], values["test_status"], values["test_message"],
             values["tested_at"], user_id, profile_id),
        )

    def activate_profile(self, user_id: str, profile):
        settings = (user_id, profile["provider"], profile["base_url"], profile["model"], profile["api_key"],
                    profile["temperature"], profile["top_p"], profile["max_tokens"], profile["timeout_seconds"])
        self.execute(
            "INSERT INTO model_settings VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "provider=excluded.provider,base_url=excluded.base_url,model=excluded.model,api_key=excluded.api_key,"
            "temperature=excluded.temperature,top_p=excluded.top_p,max_tokens=excluded.max_tokens,"
            "timeout_seconds=excluded.timeout_seconds",
            settings,
        )
        self.execute(
            "INSERT INTO model_profile_state(user_id,active_profile_id) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET active_profile_id=excluded.active_profile_id",
            (user_id, profile["id"]),
        )

    def delete_profile(self, user_id: str, profile_id: str):
        return self.execute("DELETE FROM model_profiles WHERE user_id=? AND id=?", (user_id, profile_id))

    def record_test(self, user_id, profile, status, message, tested_at):
        return self.execute(
            "UPDATE model_profiles SET test_status=?,test_message=?,tested_at=? "
            "WHERE user_id=? AND id=? AND updated_at=?",
            (status, message, tested_at, user_id, profile["id"], profile["updated_at"]),
        )

    def selections(self, user_id):
        return self.one("SELECT * FROM model_selections WHERE user_id=?", (user_id,))

    def save_model(self, user_id: str, settings):
        return self.execute(
            "INSERT INTO model_settings VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "provider=excluded.provider,base_url=excluded.base_url,model=excluded.model,api_key=excluded.api_key,"
            "temperature=excluded.temperature,top_p=excluded.top_p,max_tokens=excluded.max_tokens,"
            "timeout_seconds=excluded.timeout_seconds",
            (user_id, *[settings[k] for k in (
                "provider", "base_url", "model", "api_key", "temperature", "top_p", "max_tokens", "timeout_seconds",
            )]),
        )

    def sync_active_profile(self, user_id: str, profile_id: str, settings):
        from backend.app.db.database import now

        return self.execute(
            "UPDATE model_profiles SET provider=?,base_url=?,model=?,api_key=?,temperature=?,top_p=?,"
            "max_tokens=?,timeout_seconds=?,updated_at=?,test_status='untested',test_message='',tested_at=NULL "
            "WHERE id=? AND user_id=?",
            tuple(settings[k] for k in (
                "provider", "base_url", "model", "api_key", "temperature", "top_p", "max_tokens", "timeout_seconds",
            )) + (now(), profile_id, user_id),
        )
