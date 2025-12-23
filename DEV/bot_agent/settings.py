# FilePath: "/DEV/bot_agent/settings.py"
# Project: Unified Bot Protocol (UBP)
# Description: Configuration loading for the Bot Agent.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

from pathlib import Path
from typing import Set
from pydantic_settings import BaseSettings

class BotSettings(BaseSettings):
     """Configuration for the Bot Agent."""

     # Identity
     BOT_ID: str
     CAPABILITIES: Set[str] = {"default"}
     AGENT_VERSION: str = "2.0.0"

     # Orchestrator Connection
     ORCHESTRATOR_URL: str = "ws://localhost:8000"

     # Security
     INITIAL_TOKEN: str = "" # Used only for the first time
     CONFIG_DIR: Path = Path.home() / ".ubp"

     # Server (Health/Metrics)
     HTTP_HOST: str = "0.0.0.0"
     HTTP_PORT: int = 8001

     class Config:
          env_file = ".env"
          env_file_encoding = "utf-8"

     @property
     def credentials_file(self) -> Path:
          """Path to the file where we save the permanent API key."""
          return self.CONFIG_DIR / f"{self.BOT_ID}_credentials.json"

def get_settings() -> BotSettings:
     return BotSettings()
