# FilePath: "/DEV/orchestrator/api/tasks.py"
# Projekt: Unified Bot Protocol (UBP)
# Beskrivelse: API endpoints til håndtering af asynkrone baggrundsopgaver.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.0.0"

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any

# Retter import sti til at pege korrekt relative til denne fil
from ..tasks.manager import TaskManager, TaskStatus

router = APIRouter(prefix="/v1", tags=["Tasks"])

# Instansier manageren (Singleton i dette modul)
task_manager = TaskManager()

@router.post("/bots/{bot_id}/actions/{action}")
async def create_action(
    request: Request,
    bot_id: str,
    action: str,
    params: Dict[str, Any]
) -> JSONResponse:
    """Create a new asynchronous task for a specific bot action."""

    # TODO: Validate bot exists via Storage service here

    # Create task
    task_id = task_manager.create_task(action, params)

    # Generate status URL dynamically based on request host
    status_url = str(request.url_for("get_task_status", task_id=task_id))

    # Return 202 Accepted with Location header
    return JSONResponse(
        content={"task_id": task_id, "status": "PENDING"},
        status_code=202,
        headers={"Location": status_url}
    )

@router.get("/tasks/{task_id}", name="get_task_status")
async def get_task_status(task_id: str):
    """Get the status of a task by ID."""
    task_result = task_manager.get_task_status(task_id)

    if not task_result:
        raise HTTPException(status_code=404, detail="Task not found")

    return task_result
