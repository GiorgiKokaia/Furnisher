from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from the environment or a repo-root .env file.

    Model names and provider market settings live here and nowhere else (see docs/11).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str | None = None
    chat_model: str = "gemini-2.5-flash"
    image_model: str = "gemini-2.5-flash-image"

    ikea_country: str = "de"
    ikea_language: str = "de"

    cache_dir: Path = Path.home() / ".furnisher"
