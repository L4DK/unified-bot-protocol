# FilePath: "/DEV/orchestrator/api/__init__.py"
# Beskrivelse: Eksponerer API routere.
# Author: "Michael Landbo"

from .tasks import router as tasks_router
from .management_api import router as management_router

__all__ = ["tasks_router", "management_router"]
