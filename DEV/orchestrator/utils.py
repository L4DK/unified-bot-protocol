# FilePath: "/DEV/orchestrator/utils.py"
# Projekt: Unified Bot Protocol (UBP)
# Beskrivelse: Fælles hjælpefunktioner.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

import secrets

def create_one_time_token() -> str:
     """Genererer et sikkert URL-safe token."""
     return secrets.token_urlsafe(32)
