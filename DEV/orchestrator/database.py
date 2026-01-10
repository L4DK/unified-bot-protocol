"""
FilePath: "/orchestrator/settings.py"
Project: Unified Bot Protocol (UBP)
Description: Loads configuration from .env and constructs the async DB connection string.
Author: "Michael Landbo"
Date created: "31/12/2025"
Date Modified: "31/12/2025"
Version: "1.2.1"
"""

from functools import lru_cache
from typing import Any, Optional

from pydantic import validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # --- App Config ---
    APP_NAME: str = "UBP Orchestrator"
    UBP_ENV: str = "development"

    # --- Security ---
    UBP_SECRET_KEY: str = "unsafe_default_key_change_me"
    UBP_API_KEY: str = ""

    # --- Database Variables (Read from .env) ---
    DB_PG_USER: str = "postgres"
    DB_PG_PASSWORD: str = "postgres"
    DB_PG_HOST: str = "localhost"
    DB_PG_PORT: str = "5432"
    DB_PG_NAME: str = "ubp"

    # --- Calculated Database URL ---
    # RETTELSE HER: Vi definerer den som 'str' og giver den en tom streng som startværdi.
    # Dette gør Pylance glad, fordi typen nu er 'str' og ikke 'str | None'.
    DATABASE_URL: str = ""

    validator("DATABASE_URL", pre=True, always=True)
    def assemble_db_connection(self, v: Optional[str], values: dict[str, Any]) -> str:
        """
        Constructs the SQLAlchemy Async Database URL.
        """
        # Hvis v er sat (fra .env), returner vi den.
        if isinstance(v, str) and v:
            return v

        # Ellers bygger vi den selv.
        return str(f"postgresql+asyncpg://" f"{values.get('DB_PG_USER')}:{values.get('DB_PG_PASSWORD')}@" f"{values.get('DB_PG_HOST')}:{values.get('DB_PG_PORT')}/" f"{values.get('DB_PG_NAME')}")

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        case_sensitive = True


@lru_cache()
def get_settings():
    return Settings()
