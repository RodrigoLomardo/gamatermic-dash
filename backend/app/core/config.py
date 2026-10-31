from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_prefix="GAMA_", extra="ignore")

    env: str = "dev"  # dev | test | prod
    database_url: str = "postgresql+asyncpg://gama@localhost:5433/gamatermic"
    jwt_secret: str = Field(default="dev-only-secret-change-me-dev-only-secret", min_length=32)
    jwt_kid: str = "k1"
    jwt_issuer: str = "gamatermic-dash"
    access_ttl_seconds: int = 600
    device_access_ttl_seconds: int = 900
    refresh_idle_days: int = 7
    refresh_absolute_days: int = 30
    refresh_reuse_window_seconds: int = 10
    fernet_key: str = "ZGV2LW9ubHktZmVybmV0LWtleS1kZXYtb25seS0wMDA="  # 32 bytes b64; trocar em prod
    password_pepper: str = ""
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]
    upload_dir: str = "./data/uploads"
    max_upload_bytes: int = 20 * 1024 * 1024
    upload_retention_days: int = 90
    statement_timeout_ms: int = 5000
    pairing_ttl_seconds: int = 600
    pairing_interval_seconds: int = 3
    device_cred_days: int = 365
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    rate_limit_enabled: bool = True
    run_worker_inprocess: bool = True
    frontend_version: str = "dev"
    docs_enabled: bool = True
    # IA (ADR 0010): host fixo da Groq; so muda para apontar o E2E a um servidor falso
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ai_timeout_seconds: float = 45.0

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
