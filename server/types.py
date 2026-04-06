"""Pydantic models for the Incident Response environment."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Domain enums
# ---------------------------------------------------------------------------

class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    OVERLOADED = "overloaded"


class ActionType(str, Enum):
    CHECK_SERVICE = "check_service"
    CHECK_LOGS = "check_logs"
    CHECK_METRICS = "check_metrics"
    RESTART_SERVICE = "restart_service"
    SCALE_SERVICE = "scale_service"
    ROLLBACK_DEPLOY = "rollback_deploy"
    UPDATE_CONFIG = "update_config"
    SEND_NOTIFICATION = "send_notification"


# ---------------------------------------------------------------------------
# OpenEnv Action / Observation / State
# ---------------------------------------------------------------------------

class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    action_type: ActionType
    target: str = Field(description="Service or resource name")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    done: bool = False
    reward: float | None = None
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    available_actions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class State(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    episode_id: Optional[str] = None
    step_count: int = Field(default=0, ge=0)
    task_name: str = ""
    task_level: int = 0
    services: Dict[str, ServiceStatus] = Field(default_factory=dict)
    actions_taken: List[str] = Field(default_factory=list)
    score: float = 0.0
    max_steps: int = 20
    resolved: bool = False
