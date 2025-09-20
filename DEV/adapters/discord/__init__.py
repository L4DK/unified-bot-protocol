# adapters/discord/__init__.py
"""
Discord Adapter Package for Unified Bot Protocol (UBP).

Provides integration with Discord API, event handling, and UBP orchestration.
"""

from .discord_adapter import DiscordAdapter

__all__ = ["DiscordAdapter"]
