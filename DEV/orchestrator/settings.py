# FilePath: "/DEV/orchestrator/settings.py"
# Project: Unified Bot Protocol (UBP)
# Description: Loads configuration from the .env file using Pydantic.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
     """Application settings loaded from environment variables."""

     # App Config
     APP_NAME: str = "UBP Orchestrator"
     UBP_ENV: str = "development"

     # Security
     UBP_SECRET_KEY: str
     UBP_API_KEY: str

     # Server
     HOST: str = "0.0.0.0"
     PORT: int = 8000

     class Config:
          # Points to the .env file in the parent folder (DEV/) or current folder
          env_file = ".env"
          env_file_encoding = 'utf-8'

@lru_cache()
def get_settings():
     """Returns a cached instance of the settings."""
     return Settings()
