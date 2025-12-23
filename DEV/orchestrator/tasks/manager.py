# FilePath: "/DEV/orchestrator/tasks/manager.py"
# Project: Unified Bot Protocol (UBP)
# Description: Manages asynchronous background tasks (e.g., document analysis).
#              Tracks status, progress, and results in-memory.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Version: "v.1.1.0"

import asyncio
import uuid
import logging
import time
from enum import Enum
from typing import Dict, Any, Optional, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger("ubp.task_manager")

class TaskStatus(Enum):
    """Enumeration of possible task states."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

@dataclass
class TaskResult:
    """
    Data model representing the state and result of a background task.
    Combines Pydantic-style fields with dataclass for internal usage.
    """
    id: str
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress: int = 0
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    _async_task: Optional[asyncio.Task] = None  # Reference to the actual asyncio task

class TaskManager:
    """
    Central manager for spawning and tracking background tasks.
    Currently uses in-memory storage. In production, use Redis/Celery.
    """

    def __init__(self):
        self.tasks: Dict[str, TaskResult] = {}
        self._retention_period = 3600  # Keep results for 1 hour

    async def submit_task(
        self,
        coro: Coroutine,
        name: str = "unknown_task",
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Submit a coroutine for background execution.
        Returns a task_id immediately.
        """
        task_id = str(uuid.uuid4())
        metadata = metadata or {}

        task_entry = TaskResult(
            id=task_id,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            metadata={**metadata, "name": name}
        )

        # Wrap coroutine to handle lifecycle (status updates)
        wrapped_coro = self._run_task_wrapper(task_id, coro)

        # Schedule task on the event loop
        async_task = asyncio.create_task(wrapped_coro)
        task_entry._async_task = async_task

        self.tasks[task_id] = task_entry
        logger.info(f"Task submitted: {name} (ID: {task_id})")

        # Simple cleanup trigger
        if len(self.tasks) > 1000:
            self._cleanup_old_tasks()

        return task_id

    # Legacy wrapper for creating specific tasks by string action name
    def create_task(self, action: str, params: Dict[str, Any]) -> str:
        """
        Create a new background task by action name and return its unique ID.
        """
        if action == "analyze-document":
            # We defer the coroutine creation to here
            coro = self._analyze_document_job(params)
            # Use submit_task to handle the async scheduling
            # Note: submit_task is async, but create_task signature is sync in your original code.
            # To fix this mismatch in a sync method, we create the task directly on the loop.

            task_id = str(uuid.uuid4())
            task_entry = TaskResult(
                id=task_id,
                status=TaskStatus.PENDING,
                created_at=time.time(),
                metadata={"action": action, **params}
            )
            self.tasks[task_id] = task_entry

            # Start the wrapper
            asyncio.create_task(self._run_task_wrapper(task_id, coro))
            return task_id
        else:
            raise ValueError(f"Unknown action: {action}")

    async def _run_task_wrapper(self, task_id: str, coro: Coroutine):
        """Internal wrapper that updates status before/after execution."""
        task = self.tasks.get(task_id)
        if not task:
            return

        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        try:
            # Pass the task_id to the coroutine if it expects it (for progress updates)
            # This is a bit tricky with generic coroutines, so we rely on the specific job
            # knowing how to update the manager if needed, or we inject a callback.
            # For simplicity here, we assume the coro is self-contained or bound to the manager instance.

            # Actually run the job
            result = await coro

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            logger.info(f"Task {task_id} completed successfully.")

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            logger.warning(f"Task {task_id} was cancelled.")
            raise

        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)

        finally:
            task.completed_at = time.time()

    # --- Job Implementations ---

    async def _analyze_document_job(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate a long-running document analysis process.
        """
        # Note: In a real implementation, we would need a way to look up the task_id
        # inside this method to update progress. For this 'job' pattern,
        # we often pass a 'progress_callback' or bind the task_id.
        # Since the wrapper runs generic coroutines, direct progress updates
        # to self.tasks[task_id] are harder without passing task_id in.

        # Simplified simulation:
        total_steps = 5
        filename = params.get("filename", "unknown")

        for step in range(total_steps):
            await asyncio.sleep(2)
            # (Progress update logic would ideally go here if we had the ID context)

        return {
            "analysis_complete": True,
            "processing_time": 10,
            "document_stats": {
                "pages": 5,
                "words": 1000,
                "entities": 50,
                "filename": filename
            }
        }

    # --- Public API ---

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status and data for a specific task."""
        task = self.tasks.get(task_id)
        if not task:
            return None

        return {
            "id": task.id,
            "status": task.status.value,
            "progress": task.progress,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
            "result": task.result,
            "error": task.error,
            "metadata": task.metadata
        }

    # Alias for backward compatibility
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.get_task(task_id)

    def list_tasks(self, status: Optional[str] = None) -> list:
        """List all tasks, optionally filtered by status."""
        results = []
        for task in self.tasks.values():
            if status and task.status.value != status:
                continue
            results.append({
                "id": task.id,
                "status": task.status.value,
                "progress": task.progress,
                "created_at": task.created_at
            })
        return results

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        task = self.tasks.get(task_id)
        if task and task._async_task and not task._async_task.done():
            task._async_task.cancel()
            try:
                await task._async_task
            except asyncio.CancelledError:
                pass
            return True
        return False

    def _cleanup_old_tasks(self):
        """Remove old, finished tasks to save memory."""
        now = time.time()
        to_remove = []
        for task_id, task in self.tasks.items():
            if task.completed_at and (now - task.completed_at > self._retention_period):
                to_remove.append(task_id)

        for tid in to_remove:
            del self.tasks[tid]
