# core/orchestrator.py
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from core.schemas import (
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
)


class Status(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    AUDITING = "auditing"
    EXTENDING = "extending"
    EVOLVING = "evolving"
    COMPLETE = "complete"
    ERROR = "error"


class OrchestratorState(BaseModel):
    status: Status = Status.PLANNING
    task_id: UUID
    history: List[ResponseEnvelope] = Field(default_factory=list)
    retry_count: int = 0
    loop_count: int = 0
    max_retries: int = 3
    max_loops: int = 5
    needs_tool: bool = False


class Orchestrator:
    def __init__(self):
        self.state: Optional[OrchestratorState] = None

    def start(self, task_id: UUID) -> OrchestratorState:
        self.state = OrchestratorState(task_id=task_id)
        return self.state

    def process_response(
        self, request: Envelope, response: ResponseEnvelope
    ) -> Status:
        if self.state is None:
            raise RuntimeError("Orchestrator has not been started")

        # 1. Enforce task_id correlation
        if response.task_id != request.task_id:
            raise ValueError(
                f"Task ID mismatch: request={request.task_id} response={response.task_id}"
            )

        # 2. Record history
        self.state.history.append(response)

        # 3. Hard error
        if response.error and not response.error.recoverable:
            self.state.status = Status.ERROR
            return Status.ERROR

        # 4. Recoverable error → retry planning
        if response.error and response.error.recoverable:
            if self.state.retry_count < self.state.max_retries:
                self.state.retry_count += 1
                self.state.status = Status.PLANNING
                return Status.PLANNING
            self.state.status = Status.ERROR
            return Status.ERROR

        # 5. Success path transitions
        match self.state.status:
            case Status.PLANNING:
                self.state.status = Status.EXECUTING
                return Status.EXECUTING

            case Status.EXECUTING:
                self.state.status = Status.VALIDATING
                return Status.VALIDATING

            case Status.VALIDATING:
                self.state.status = Status.AUDITING
                return Status.AUDITING

            case Status.AUDITING:
                if self.state.needs_tool:
                    if self.state.loop_count >= self.state.max_loops:
                        self.state.status = Status.ERROR
                        return Status.ERROR
                    self.state.loop_count += 1
                    self.state.status = Status.EXTENDING
                    return Status.EXTENDING
                self.state.status = Status.COMPLETE
                return Status.COMPLETE

            case Status.EXTENDING:
                # After successful tool creation → replan
                self.state.needs_tool = False
                self.state.status = Status.PLANNING
                return Status.PLANNING

            case Status.EVOLVING:
                self.state.status = Status.COMPLETE
                return Status.COMPLETE

            case _:
                self.state.status = Status.COMPLETE
                return Status.COMPLETE

    def set_needs_tool(self, value: bool = True) -> None:
        if self.state:
            self.state.needs_tool = value
