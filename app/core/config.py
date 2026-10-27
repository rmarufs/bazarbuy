from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    DATABASE_URL: str
    TEST_DATABASE_URL: str
    SECRET_KEY: str
    UPLOAD_DIR: str = "uploads"
    APP_ENV: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
