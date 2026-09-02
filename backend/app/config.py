"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = "SoilEdge Field System"
    app_env: str = "dev"
    app_port: int = 8000

    # --- Security ---
    secret_key: str = "dev-only-change-me-please-32+chars-aaaaaa"
    access_token_expire_minutes: int = 60 * 24  # 1 day

    # --- DB ---
    database_url: str = "sqlite:///./soiledge.db"

    # --- CORS ---
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])

    # --- Copernicus / Sentinel ---
    copernicus_client_id: str = ""
    copernicus_client_secret: str = ""
    copernicus_token_url: str = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    copernicus_process_url: str = "https://sh.dataspace.copernicus.eu/api/v1/process"
    copernicus_catalogue_url: str = "https://catalogue.dataspace.copernicus.eu/odata/v1"
    copernicus_lookback_days: int = 15
    copernicus_max_cloud_pct: int = 30

    # --- Rate limit ---
    telemetry_rate_per_min: int = 60

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        """Allow CORS_ORIGINS to be a comma-separated string in .env."""
        if v is None or v == "":
            return ["*"]
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
