from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
INSECURE_DEFAULT_SECRET = "dev-only-secret-change-me-dev-only-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "Udyam-Nirdesh API"
    environment: Literal["development", "production", "test"] = "development"

    database_url: str = f"sqlite:///{BACKEND_DIR / 'udyam.db'}"

    # --- auth ---
    secret_key: str = INSECURE_DEFAULT_SECRET
    access_token_expire_minutes: int = 60
    login_max_failed_attempts: int = 10      # per (client ip, email) ...
    login_lockout_seconds: int = 300         # ... within this window

    # --- CORS (only needed when the frontend is served from a different origin) ---
    cors_origins: str = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,http://localhost:8080"

    # --- documents ---
    upload_dir: Path = BACKEND_DIR / "storage" / "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024

    # --- seeding ---
    seed_on_startup: bool = True
    seed_demo_user: bool = True              # user@udyam.local -- turn OFF in production
    demo_user_email: str = "user@udyam.local"
    demo_user_password: str = "user123"
    admin_email: str = "admin@udyam.local"
    admin_password: str = ""                 # dev falls back to a demo password; production requires it

    # --- optionally serve ../frontend from the same origin (no CORS needed) ---
    serve_frontend: bool = True
    frontend_dir: Path = BACKEND_DIR.parent / "frontend"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _production_guards(self):
        if self.environment == "production":
            if self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
