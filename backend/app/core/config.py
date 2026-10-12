"""Application settings.

All configuration comes from environment variables (optionally a `.env` file). Required secrets are
validated at startup so a misconfigured deployment fails fast instead of at the first request.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRETS = {"", "change-me", "changeme", "secret", "dev"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "AnalystOS"
    log_level: str = "INFO"
    log_json: bool = True

    # Persistence
    database_url: str = Field(..., description="SQLAlchemy URL for the application Postgres database")
    redis_url: str = "redis://localhost:6379/0"
    data_dir: Path = Path("./var/data")

    # Security
    secret_key: str = Field(..., description="JWT signing key")
    encryption_key: str = Field(..., description="Fernet key used to encrypt stored DB credentials")
    access_token_ttl_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    allow_registration: bool = True

    # LLM provider (OpenAI-compatible endpoint: OpenAI, Azure OpenAI, Ollama, vLLM, LM Studio...)
    llm_provider: Literal["openai_compatible", "azure_openai"] = "openai_compatible"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3:8b"
    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 180.0
    llm_max_output_tokens: int = 2048
    llm_disable_thinking: bool = True
    azure_api_version: str = "2024-08-01-preview"
    pricing_file: Path | None = None

    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # Agent limits
    agent_max_steps: int = 12
    agent_max_replans: int = 2
    agent_max_retries_per_step: int = 3
    agent_job_timeout_seconds: int = 900
    run_analyses_inline: bool = False  # True = run in the API process (tests / no Redis)

    # Data limits
    max_upload_mb: int = 200
    preview_rows: int = 50
    profile_sample_rows: int = 200_000

    # SQL execution limits
    sql_timeout_seconds: float = 20.0
    sql_max_rows: int = 5000
    sql_max_joins: int = 6
    sql_max_subquery_depth: int = 4

    # Python sandbox
    sandbox_enabled: bool = True
    sandbox_image: str = "analystos-sandbox:latest"
    sandbox_cpus: float = 1.0
    sandbox_memory_mb: int = 512
    sandbox_timeout_seconds: int = 30
    sandbox_pids_limit: int = 128
    sandbox_max_output_bytes: int = 2_000_000

    # Observability
    otel_exporter_otlp_endpoint: str | None = None
    metrics_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _validate_secrets(self) -> Settings:
        if self.environment == "production" and (
            self.secret_key.lower() in _INSECURE_SECRETS or len(self.secret_key) < 32
        ):
            raise ValueError("SECRET_KEY must be a random value of at least 32 characters in production")
        if len(self.secret_key) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters")
        try:
            from cryptography.fernet import Fernet

            Fernet(self.encryption_key.encode())
        except Exception as exc:  # pragma: no cover - message path tested via ValueError
            raise ValueError(
                "ENCRYPTION_KEY must be a urlsafe base64 Fernet key "
                "(generate with: python -c 'from cryptography.fernet import Fernet;"
                "print(Fernet.generate_key().decode())')"
            ) from exc
        return self

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    def ensure_dirs(self) -> None:
        for path in (self.uploads_dir, self.datasets_dir, self.artifacts_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # values come from the environment
    settings.ensure_dirs()
    return settings
