"""
FilePath: "/DEV/orchestrator/tasks/manager.py"
Project: Unified Bot Protocol (UBP)
Description: Manages asynchronous background tasks with Database Persistence.
Author: "Michael Landbo"
Date created: "31/12/2025"
Version: "1.2.1"
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Coroutine, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db_models import TaskModel

logger = logging.getLogger("ubp.task_manager")


class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskResult:
    id: str
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress: int = 0
    result: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskManager:
    def __init__(self):
        pass

    async def submit_task(self, coro: Coroutine, name: str = "unknown_task", metadata: Optional[Dict[str, Any]] = None) -> str:
        task_id = str(uuid.uuid4())
        metadata = metadata or {}

        async with AsyncSession() as session:
            async with session.begin():
                new_task = TaskModel(id=task_id, name=name, status=TaskStatus.PENDING.value, metadata_fields=metadata, created_at=datetime.now(timezone.utc))
                session.add(new_task)

        logger.info("Task submitted to DB: %s (ID: %s)", name, task_id)

        wrapped_coro = self._run_task_wrapper(task_id, coro)
        asyncio.create_task(wrapped_coro)

        return task_id

    async def create_task(self, action: str, params: Dict[str, Any]) -> str:
        if action == "analyze-document":
            coro = self._analyze_document_job(params)
            return await self.submit_task(coro, name=action, metadata=params)

        raise ValueError(f"Unknown action: {action}")

    async def _run_task_wrapper(self, task_id: str, coro: Coroutine):
        await self._update_task_status(task_id, TaskStatus.RUNNING, started=True)

        try:
            result = await coro
            await self._update_task_status(task_id, TaskStatus.COMPLETED, result=result, progress=100, completed=True)
            logger.info("Task %s completed successfully.", task_id)

        except asyncio.CancelledError:
            await self._update_task_status(task_id, TaskStatus.CANCELLED, completed=True)
            logger.warning("Task %s was cancelled.", task_id)
            raise

        except Exception as e:  # pylint: disable=broad-exception-caught
            await self._update_task_status(task_id, TaskStatus.FAILED, error=str(e), completed=True)
            logger.error("Task %s failed: %s", task_id, e, exc_info=True)

    async def _update_task_status(self, task_id: str, status: TaskStatus, result: Any = None, error: Optional[str] = None, progress: Optional[int] = None, started: bool = False, completed: bool = False):
        async with AsyncSession() as session:
            async with session.begin():
                stmt = select(TaskModel).where(TaskModel.id == task_id)
                res = await session.execute(stmt)
                task = res.scalar_one_or_none()

                if task:
                    task.status = status.value
                    if result is not None:
                        task.result = result
                    if error is not None:
                        task.error = error
                    if progress is not None:
                        task.progress = progress

                    now = datetime.now(timezone.utc)
                    if started:
                        task.started_at = now
                    if completed:
                        task.completed_at = now

    # --- Jobs ---
    async def _analyze_document_job(self, params: Dict[str, Any]) -> Dict[str, Any]:
        filename = params.get("filename", "unknown")
        await asyncio.sleep(5)
        return {"analysis_complete": True, "processing_time": 5, "document_stats": {"pages": 5, "words": 1000, "filename": filename}}

    # --- Public API ---
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with AsyncSession() as session:
            stmt = select(TaskModel).where(TaskModel.id == task_id)
            result = await session.execute(stmt)
            task = result.scalar_one_or_none()

            if not task:
                return None

            return {
                "id": task.id,
                "status": task.status,
                "progress": task.progress,
                "created_at": task.created_at.timestamp() if task.created_at else None,
                "completed_at": task.completed_at.timestamp() if task.completed_at else None,
                "result": task.result,
                "error": task.error,
                "metadata": task.metadata_fields,
            }

    async def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        async with AsyncSession() as session:
            stmt = select(TaskModel)
            if status:
                stmt = stmt.where(TaskModel.status == status)

            result = await session.execute(stmt)
            tasks = result.scalars().all()

            return [{"id": t.id, "status": t.status, "progress": t.progress, "created_at": t.created_at.timestamp() if t.created_at else None} for t in tasks]
