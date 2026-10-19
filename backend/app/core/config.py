from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[2]


def ecnu_model_env():
    values = dotenv_values(ROOT / ".env", encoding="utf-8-sig", interpolate=False)
    keys = ("ECNU_API_BASE_URL", "ECNU_API_KEY", "ECNU_MODEL_NAME", "ECNU_API_PROTOCOL")
    return {
        key: value
        for key in keys
        if (value := (os.getenv(key, values.get(key)) or "").strip())
    }


@dataclass(frozen=True)
class Config:
    data_dir: Path
    database_path: Path
    max_upload_bytes: int = 20 * 1024 * 1024
    max_batch_files: int = 20
    max_batch_upload_bytes: int = 100 * 1024 * 1024
    session_days: int = 7

    @classmethod
    def from_env(cls):
        # Data lives under <repo>/db (next to db/agent), not inside backend/.
        db_root = ROOT.parent / "db"
        data = Path(os.getenv("PERSONAWEAVER_DATA_DIR", str(db_root))).resolve()
        database = Path(os.getenv("PERSONAWEAVER_DB_PATH", str(data / "personaweaver.sqlite3"))).resolve()
        def integer(name: str, default: int) -> int:
            try:
                value = int(os.getenv(name, str(default)))
            except ValueError:
                return default
            return value if value > 0 else default

        return cls(
            data_dir=data,
            database_path=database,
            max_upload_bytes=integer("PERSONAWEAVER_MAX_UPLOAD_BYTES", cls.max_upload_bytes),
            max_batch_files=integer("PERSONAWEAVER_MAX_BATCH_FILES", cls.max_batch_files),
            max_batch_upload_bytes=integer(
                "PERSONAWEAVER_MAX_BATCH_UPLOAD_BYTES", cls.max_batch_upload_bytes,
            ),
        )
