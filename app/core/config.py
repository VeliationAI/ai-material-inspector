from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Material Inspector"
    app_env: str = "development"
    app_debug: bool = True
    app_version: str = "1.0.0"
    secret_key: str = "dev-only-secret-change-in-production"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"

    database_url: str = Field(
        default=f"sqlite:///{(ROOT / 'data' / 'processed' / 'material_inspector.db').as_posix()}"
    )
    cors_origins: str = (
        "http://localhost:8080,http://127.0.0.1:8080,"
        "https://tisc-telangana-solutions.onrender.com"
    )

    default_org_name: str = "TGSPDCL Stores"
    default_admin_email: str = "officer@tgspdcl.example"
    default_admin_password: str = "ChangeMeNow!23"
    allow_demo_login: bool = True

    upload_dir: Path = ROOT / "data" / "uploads"
    annotated_dir: Path = ROOT / "data" / "annotated"
    reports_dir: Path = ROOT / "data" / "reports"
    sample_pos_path: Path = ROOT / "data" / "sample_pos.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for path in (settings.upload_dir, settings.annotated_dir, settings.reports_dir, ROOT / "data" / "processed"):
        path.mkdir(parents=True, exist_ok=True)
    return settings
