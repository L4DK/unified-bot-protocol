# FilePath: "/DEV/orchestrator/tasks/manager.py"
# Project: Unified Bot Protocol (UBP)
# Description: Manages asynchronous background tasks (e.g., document analysis).
#              Tracks status, progress, and results in-memory.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from enum import Enum
from typing import Dict, Optional, Any
import asyncio
import uuid
from datetime import datetime
import logging
from pydantic import BaseModel

class TaskStatus(Enum):
    """Enumeration of possible task states."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class TaskResult(BaseModel):
    """Data model representing the state and result of a background task."""
    status: TaskStatus
    progress: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

class TaskManager:
    """
    Central manager for spawning and tracking background tasks.
    Currently uses in-memory storage. In production, use Redis/Celery.
    """
    
    def __init__(self):
        self.tasks: Dict[str, TaskResult] = {}
        self.logger = logging.getLogger("ubp.task_manager")

    def create_task(self, action: str, params: Dict[str, Any]) -> str:
        """
        Create a new background task and return its unique ID.
        """
        task_id = str(uuid.uuid4())

        self.tasks[task_id] = TaskResult(
            status=TaskStatus.PENDING,
            started_at=datetime.utcnow()
        )

        # Start task processing in background
        # We store the task reference if needed, but for fire-and-forget:
        asyncio.create_task(
            self._process_task(task_id, action, params)
        )

        return task_id

    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """Get the current status of a task by ID."""
        return self.tasks.get(task_id)

    async def _process_task(self, task_id: str, action: str, params: Dict[str, Any]):
        """
        Internal worker method to process a task asynchronously.
        Handles state transitions and error catching.
        """
        try:
            self.logger.info(f"Starting task {task_id} - Action: {action}")

            # Update status to running
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.RUNNING

            # Process based on action type
            if action == "analyze-document":
                result = await self._analyze_document(task_id, params)
            else:
                raise ValueError(f"Unknown action: {action}")

            # Update task with success result
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = datetime.utcnow()
                task.progress = 100

        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {str(e)}")

            # Update task with error
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.utcnow()

    async def _analyze_document(self, task_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate a long-running document analysis process.
        """
        total_steps = 5

        for step in range(total_steps):
            # Simulate work (e.g., calling OCR API, parsing text)
            await asyncio.sleep(2)

            # Update progress
            if task_id in self.tasks:
                progress = int((step + 1) * 100 / total_steps)
                self.tasks[task_id].progress = progress
                self.logger.info(f"Task {task_id} progress: {progress}%")

        return {
            "analysis_complete": True,
            "processing_time": 10,
            "document_stats": {
                "pages": 5,
                "words": 1000,
                "entities": 50,
                "filename": params.get("filename", "unknown")
            }
        }
