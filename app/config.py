"""Environment-driven settings without side effects or secret logging."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "Zhiku Enterprise RAG"
    app_version: str = "1.0.0"
    app_mode: str = "standalone"
    environment: str = "development"
    log_level: str = "INFO"

    auth_enabled: bool = False
    jwt_secret: str = "development-only-change-me"
    jwt_expire_minutes: int = 60
    admin_username: str = "local-admin"
    admin_password: str = "local-password"

    cors_origins: tuple[str, ...] = (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )
    max_upload_bytes: int = 20 * 1024 * 1024
    default_top_k: int = 5
    seed_standalone_data: bool = True
    standalone_data_dir: Path = PROJECT_ROOT / "examples"
    runtime_data_dir: Path = PROJECT_ROOT / "data" / "runtime"

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        raw_mode = os.getenv("APP_MODE", "standalone").strip().lower()
        mode = "standalone" if raw_mode == "demo" else raw_mode
        environment = os.getenv("APP_ENV", "development").strip().lower()
        settings = cls(
            app_name=os.getenv("APP_NAME", defaults.app_name),
            app_version=os.getenv("APP_VERSION", defaults.app_version),
            app_mode=mode,
            environment=environment,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            auth_enabled=_as_bool(os.getenv("AUTH_ENABLED"), default=False),
            jwt_secret=os.getenv("JWT_SECRET", defaults.jwt_secret),
            jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "60")),
            admin_username=os.getenv("ADMIN_USERNAME", defaults.admin_username),
            admin_password=os.getenv("ADMIN_PASSWORD", defaults.admin_password),
            cors_origins=_as_csv(os.getenv("CORS_ORIGINS"), defaults.cors_origins),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024,
            default_top_k=int(os.getenv("DEFAULT_TOP_K", "5")),
            seed_standalone_data=_as_bool(
                os.getenv("SEED_STANDALONE_DATA", os.getenv("SEED_DEMO_DATA")), default=True
            ),
            standalone_data_dir=Path(
                os.getenv(
                    "STANDALONE_DATA_DIR",
                    os.getenv("DEMO_DATA_DIR", str(PROJECT_ROOT / "examples")),
                )
            ),
            runtime_data_dir=Path(os.getenv("RUNTIME_DATA_DIR", str(PROJECT_ROOT / "data" / "runtime"))),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.app_mode not in {"standalone", "full"}:
            raise ValueError("APP_MODE must be either 'standalone' or 'full'")
        if not 1 <= self.default_top_k <= 20:
            raise ValueError("DEFAULT_TOP_K must be between 1 and 20")
        if self.max_upload_bytes < 1024:
            raise ValueError("MAX_UPLOAD_MB is too small")
        if self.auth_enabled and self.environment == "production":
            insecure = {
                "development-only-change-me",
                "change-me",
                "local-password",
                "demo-password",
                "",
            }
            if self.jwt_secret in insecure or self.admin_password in insecure:
                raise ValueError("Production authentication requires non-default JWT_SECRET and ADMIN_PASSWORD")
