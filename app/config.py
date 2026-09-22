from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    database_url: str = "sqlite:///./shop.db"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    admin_email: str | None = None
    admin_password: str | None = None

    # Email verification codes on registration. Checked in this order:
    # 1) Brevo HTTP API (works even on hosts that block outbound SMTP ports, e.g.
    #    Render's free plan) — set BREVO_API_KEY.
    # 2) Plain SMTP — set SMTP_HOST (won't work on Render's free plan).
    # 3) Neither set -> the code is printed to the server log (fine for local dev).
    brevo_api_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    app_name: str = "Свежо"


settings = Settings()
