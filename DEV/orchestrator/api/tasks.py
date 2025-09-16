# orchestrator/api/tasks.py
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any
from ..tasks.manager import TaskManager, TaskStatus

router = APIRouter(prefix="/v1")
task_manager = TaskManager()

@router.post("/bots/{bot_id}/actions/{action}")
async def create_action(
    request: Request,
    bot_id: str,
    action: str,
    params: Dict[str, Any]
) -> JSONResponse:
    """Create a new asynchronous task"""

    # Validate bot exists (implement your logic)

    # Create task
    task_id = task_manager.create_task(action, params)

    # Generate status URL
    status_url = f"{request.base_url}v1/tasks/{task_id}"

    # Return 202 Accepted with Location header
    return JSONResponse(
        content={"task_id": task_id},
        status_code=202,
        headers={"Location": status_url}
    )

@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of a task"""
    task_result = task_manager.get_task_status(task_id)

    if not task_result:
        raise HTTPException(status_code=404, detail="Task not found")

    return task_result