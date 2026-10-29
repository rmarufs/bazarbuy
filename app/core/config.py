from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET_KEY = "change-me-to-a-long-random-string"
MIN_PRODUCTION_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None
    SECRET_KEY: str
    APP_ENV: str = "development"
    CLOUDINARY_CLOUD_NAME: str | None = None
    CLOUDINARY_API_KEY: str | None = None
    CLOUDINARY_API_SECRET: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_production_secret_key(self) -> Self:
        if self.APP_ENV == "production":
            if self.SECRET_KEY == PLACEHOLDER_SECRET_KEY:
                raise ValueError(
                    "SECRET_KEY must not use the default placeholder from .env.example "
                    "in production"
                )
            if len(self.SECRET_KEY) < MIN_PRODUCTION_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"SECRET_KEY must be at least {MIN_PRODUCTION_SECRET_KEY_LENGTH} "
                    "characters long in production"
                )
        return self


settings = Settings()
