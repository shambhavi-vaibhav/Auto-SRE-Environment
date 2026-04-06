"""Core environment implementing the OpenEnv interface."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import List, Optional

from .grader import grade
from .rewards import compute_step_reward
from .tasks import TASKS, TaskDef
from .types import Action, ActionType, Observation, ServiceStatus, State


class IncidentResponseEnv:
    """Simulates an IT incident response workflow.

    Implements reset(), step(action), and state property per the OpenEnv spec.
    """

    def __init__(self, task_name: str = "service_outage") -> None:
        self._task: TaskDef = TASKS[task_name]
        self._state: State = State()
        self._action_history: List[Action] = []
        self._reward_history: List[float] = []
        self._services_snapshot: dict = {}

    # -----------------------------------------------------------------
    # OpenEnv interface
    # -----------------------------------------------------------------

    def reset(self, seed: Optional[int] = None, task_name: Optional[str] = None, **kwargs) -> Observation:
        if task_name and task_name in TASKS:
            self._task = TASKS[task_name]

        self._state = State(
            episode_id=str(uuid.uuid4()),
            step_count=0,
            task_name=self._task.name,
            task_level=self._task.level,
            services={s: d.status for s, d in self._task.services.items()},
            actions_taken=[],
            score=0.0,
            max_steps=self._task.max_steps,
            resolved=False,
        )
        self._action_history = []
        self._reward_history = []
        self._services_snapshot = deepcopy({n: s for n, s in self._task.services.items()})

        return Observation(
            done=False,
            reward=0.0,
            message=self._task.alert_message,
            data={
                "task": self._task.name,
                "level": self._task.level,
                "description": self._task.description,
                "known_services": list(self._task.services.keys()),
            },
            available_actions=[a.value for a in ActionType],
        )

    def step(self, action: Action, **kwargs) -> Observation:
        if self._state.resolved or self._state.step_count >= self._state.max_steps:
            return self._terminal_obs()

        self._state.step_count += 1
        self._action_history.append(action)
        self._state.actions_taken.append(f"{action.action_type.value}:{action.target}")

        # Execute action and get observation text
        message, data = self._execute(action)

        # Grade and compute reward
        prev_score = self._state.score
        new_score, breakdown = grade(self._task, self._state, self._action_history)
        self._state.score = new_score

        reward = compute_step_reward(
            self._task, self._state, action, self._action_history, prev_score, new_score
        )
        self._reward_history.append(reward)

        # Check resolution
        done = self._check_resolved() or self._state.step_count >= self._state.max_steps

        return Observation(
            done=done,
            reward=reward,
            message=message,
            data={**data, "score_breakdown": breakdown},
            available_actions=[a.value for a in ActionType] if not done else [],
        )

    @property
    def state(self) -> State:
        return self._state.model_copy()

    # -----------------------------------------------------------------
    # Action execution
    # -----------------------------------------------------------------

    def _execute(self, action: Action) -> tuple[str, dict]:
        target = action.target
        svc = self._services_snapshot.get(target)

        if svc is None:
            return f"Unknown service: {target}", {"error": f"Service '{target}' not found"}

        match action.action_type:
            case ActionType.CHECK_SERVICE:
                return (
                    f"Service '{target}' status: {svc.status.value}",
                    {"service": target, "status": svc.status.value},
                )

            case ActionType.CHECK_LOGS:
                return (
                    f"Logs for '{target}':\n" + "\n".join(svc.logs),
                    {"service": target, "logs": svc.logs},
                )

            case ActionType.CHECK_METRICS:
                return (
                    f"Metrics for '{target}': {svc.metrics}",
                    {"service": target, "metrics": svc.metrics},
                )

            case ActionType.RESTART_SERVICE:
                svc.status = ServiceStatus.HEALTHY
                svc.metrics = {k: 0.0 for k in svc.metrics}
                svc.metrics["error_rate"] = 0.0
                self._state.services[target] = ServiceStatus.HEALTHY
                return (
                    f"Service '{target}' restarted successfully. Status: healthy",
                    {"service": target, "status": "healthy"},
                )

            case ActionType.SCALE_SERVICE:
                replicas = action.parameters.get("replicas", 2)
                return (
                    f"Service '{target}' scaled to {replicas} replicas.",
                    {"service": target, "replicas": replicas},
                )

            case ActionType.ROLLBACK_DEPLOY:
                prev_version = "v2.4.0" if svc.deploy_version != "v1.0.0" else "v1.0.0"
                svc.deploy_version = prev_version
                svc.status = ServiceStatus.HEALTHY
                svc.metrics = {k: 0.0 for k in svc.metrics}
                svc.metrics["error_rate"] = 0.0
                self._state.services[target] = ServiceStatus.HEALTHY
                return (
                    f"Service '{target}' rolled back to {prev_version}. Restarting...",
                    {"service": target, "rolled_back_to": prev_version, "status": "healthy"},
                )

            case ActionType.UPDATE_CONFIG:
                key = action.parameters.get("key", "")
                value = action.parameters.get("value", "")
                if hasattr(svc, "config") and key in svc.config:
                    svc.config[key] = value
                    # If fixing pool size, simulate recovery
                    if key == "max_pool_size" and isinstance(value, (int, float)) and value >= 10:
                        svc.status = ServiceStatus.HEALTHY
                        self._state.services[target] = ServiceStatus.HEALTHY
                    return (
                        f"Config updated: {target}.{key} = {value}",
                        {"service": target, "config_key": key, "config_value": value},
                    )
                return (
                    f"Config key '{key}' not found on '{target}'",
                    {"error": f"Unknown config key: {key}"},
                )

            case ActionType.SEND_NOTIFICATION:
                msg = action.parameters.get("message", "Incident update")
                return (
                    f"Notification sent to '{target}': {msg}",
                    {"channel": target, "message": msg},
                )

            case _:
                return f"Unknown action: {action.action_type}", {"error": "unknown_action"}

    def _check_resolved(self) -> bool:
        """Check if the root cause has been fixed."""
        root = self._task.root_cause_service
        root_svc = self._services_snapshot.get(root)
        if root_svc and root_svc.status == ServiceStatus.HEALTHY:
            # Verify the correct fix action was applied
            if any(
                a.action_type.value == self._task.required_fix and a.target == self._task.fix_target
                for a in self._action_history
            ):
                self._state.resolved = True
                return True
        return False

    def _terminal_obs(self) -> Observation:
        _, breakdown = grade(self._task, self._state, self._action_history)
        return Observation(
            done=True,
            reward=0.0,
            message="Episode already finished." if self._state.resolved else "Step limit reached.",
            data={"final_score": self._state.score, "score_breakdown": breakdown},
            available_actions=[],
        )
