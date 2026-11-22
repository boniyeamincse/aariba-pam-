"""Configuration settings for Ariba PAM."""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    app_name: str = "Ariba PAM Control Plane"
    environment: str = "lab"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./lab_pam.db"

    # Security & Tokens
    secret_key: str = "synthetic-lab-secret-key-ariba-pam-do-not-use-in-production-32b"
    token_algorithm: str = "HS256"
    session_lifetime_minutes: int = 60
    csrf_token_secret: str = "synthetic-csrf-secret-key-32-chars-min"

    # Identity Provider (IdP) settings for pilot
    idp_issuer: str = "https://idp.lab.ariba.internal"
    idp_audience: str = "ariba-pam-control-plane"
    require_phishing_resistant_mfa: bool = True

    # Gateway communication
    gateway_lease_duration_seconds: int = 300  # 5 minutes bounded lease
    gateway_api_secret: str = "synthetic-gateway-shared-secret-lab"

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
