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


settings = Settings()
