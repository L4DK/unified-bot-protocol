# orchestrator/tasks/manager.py
from enum import Enum
from typing import Dict, Optional, Any
import asyncio
import uuid
from datetime import datetime
import logging
from pydantic import BaseModel

class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class TaskResult(BaseModel):
    status: TaskStatus
    progress: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, TaskResult] = {}
        self.logger = logging.getLogger("task_manager")

    def create_task(self, action: str, params: Dict[str, Any]) -> str:
        """Create a new task and return its ID"""
        task_id = str(uuid.uuid4())

        self.tasks[task_id] = TaskResult(
            status=TaskStatus.PENDING,
            started_at=datetime.utcnow()
        )

        # Start task processing in background
        asyncio.create_task(
            self._process_task(task_id, action, params)
        )

        return task_id

    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """Get the current status of a task"""
        return self.tasks.get(task_id)

    async def _process_task(
        self,
        task_id: str,
        action: str,
        params: Dict[str, Any]
    ):
        """Process a task asynchronously"""
        try:
            self.logger.info(f"Starting task {task_id} - Action: {action}")

            # Update status to running
            self.tasks[task_id].status = TaskStatus.RUNNING

            # Process based on action type
            if action == "analyze-document":
                result = await self._analyze_document(task_id, params)
            else:
                raise ValueError(f"Unknown action: {action}")

            # Update task with success result
            self.tasks[task_id].status = TaskStatus.COMPLETED
            self.tasks[task_id].result = result
            self.tasks[task_id].completed_at = datetime.utcnow()

        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {str(e)}")

            # Update task with error
            self.tasks[task_id].status = TaskStatus.FAILED
            self.tasks[task_id].error = str(e)
            self.tasks[task_id].completed_at = datetime.utcnow()

    async def _analyze_document(
        self,
        task_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate document analysis"""
        total_steps = 5

        for step in range(total_steps):
            # Simulate work
            await asyncio.sleep(2)

            # Update progress
            progress = int((step + 1) * 100 / total_steps)
            self.tasks[task_id].progress = progress

            self.logger.info(f"Task {task_id} progress: {progress}%")

        return {
            "analysis_complete": True,
            "processing_time": 10,
            "document_stats": {
                "pages": 5,
                "words": 1000,
                "entities": 50
            }
        }
