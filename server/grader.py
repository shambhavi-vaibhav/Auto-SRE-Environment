"""Deterministic graders for each task level."""

from __future__ import annotations

from typing import List, Tuple

from .tasks import TaskDef
from .types import Action, ActionType, State


def _action_targets(actions: List[Action], action_type: ActionType, target: str) -> bool:
    """Check if any action in history matches type + target."""
    return any(
        a.action_type == action_type and a.target == target
        for a in actions
    )


def _action_with_params(
    actions: List[Action], action_type: ActionType, target: str, key: str, value
) -> bool:
    """Check if any action matches type + target + specific param."""
    return any(
        a.action_type == action_type
        and a.target == target
        and a.parameters.get(key) == value
        for a in actions
    )


def grade(task: TaskDef, state: State, action_history: List[Action]) -> Tuple[float, dict]:
    """Return (score, breakdown) for the current episode.

    Score is in [0.0, 1.0]. The breakdown dict maps credit-key -> awarded float.
    """
    breakdown: dict[str, float] = {}
    root = task.root_cause_service

    # --- Common partial credits ---

    # Checked the root-cause service status
    if _action_targets(action_history, ActionType.CHECK_SERVICE, root):
        breakdown["checked_root_cause"] = task.partial_credit.get("checked_root_cause", 0.0)

    # Checked logs of root-cause service
    if _action_targets(action_history, ActionType.CHECK_LOGS, root):
        breakdown["checked_logs"] = task.partial_credit.get("checked_logs", 0.0)

    # Checked metrics of root-cause service
    if _action_targets(action_history, ActionType.CHECK_METRICS, root):
        breakdown["checked_metrics"] = task.partial_credit.get("checked_metrics", 0.0)

    # --- Task-specific credits ---

    if task.name == "service_outage":
        # L1: restart the web-frontend
        if _action_targets(action_history, ActionType.RESTART_SERVICE, root):
            breakdown["applied_fix"] = task.partial_credit.get("applied_fix", 0.0)
            breakdown["identified_cause"] = task.partial_credit.get("identified_cause", 0.0)

    elif task.name == "db_connection_exhaustion":
        # L2: update api-backend config max_pool_size back to 20
        if _action_targets(action_history, ActionType.CHECK_LOGS, "api-backend"):
            breakdown["identified_config"] = task.partial_credit.get("identified_config", 0.0)

        if _action_with_params(
            action_history, ActionType.UPDATE_CONFIG, root, "key", "max_pool_size"
        ):
            # Accept any reasonable pool size >= 10
            for a in action_history:
                if (
                    a.action_type == ActionType.UPDATE_CONFIG
                    and a.target == root
                    and a.parameters.get("key") == "max_pool_size"
                ):
                    val = a.parameters.get("value")
                    if isinstance(val, (int, float)) and val >= 10:
                        breakdown["applied_fix"] = task.partial_credit.get("applied_fix", 0.0)
                        break

        # Verified fix by re-checking service
        check_after_fix = False
        fix_seen = False
        for a in action_history:
            if a.action_type == ActionType.UPDATE_CONFIG and a.target == root:
                fix_seen = True
            if fix_seen and a.action_type == ActionType.CHECK_SERVICE and a.target == root:
                check_after_fix = True
        if check_after_fix:
            breakdown["verified_fix"] = task.partial_credit.get("verified_fix", 0.0)

    elif task.name == "cascading_failure":
        # L3: rollback order-service deployment
        if _action_targets(action_history, ActionType.CHECK_SERVICE, "order-service"):
            breakdown["checked_order_service"] = task.partial_credit.get("checked_order_service", 0.0)
        if _action_targets(action_history, ActionType.CHECK_LOGS, "order-service"):
            breakdown["checked_order_logs"] = task.partial_credit.get("checked_order_logs", 0.0)
        if _action_targets(action_history, ActionType.CHECK_METRICS, "order-service"):
            breakdown["checked_order_metrics"] = task.partial_credit.get("checked_order_metrics", 0.0)

        # Identified memory leak (checked logs mentioning OOM / linear growth)
        if (
            _action_targets(action_history, ActionType.CHECK_LOGS, "order-service")
            and _action_targets(action_history, ActionType.CHECK_METRICS, "order-service")
        ):
            breakdown["identified_memory_leak"] = task.partial_credit.get("identified_memory_leak", 0.0)

        # Identified deployment as cause
        if _action_targets(action_history, ActionType.CHECK_LOGS, "order-service"):
            breakdown["identified_deployment"] = task.partial_credit.get("identified_deployment", 0.0)

        # Ruled out red herrings (checked at least one non-root-cause service)
        non_root = [s for s in task.services if s != root]
        if any(_action_targets(action_history, ActionType.CHECK_SERVICE, s) for s in non_root):
            breakdown["ruled_out_red_herring"] = task.partial_credit.get("ruled_out_red_herring", 0.0)

        # Applied rollback
        if _action_targets(action_history, ActionType.ROLLBACK_DEPLOY, "order-service"):
            breakdown["applied_rollback"] = task.partial_credit.get("applied_rollback", 0.0)

        # Scaled up to handle backlog
        if _action_targets(action_history, ActionType.SCALE_SERVICE, "order-service"):
            breakdown["scaled_up"] = task.partial_credit.get("scaled_up", 0.0)

        # Notified team
        if _action_targets(action_history, ActionType.SEND_NOTIFICATION, "team"):
            breakdown["notified_team"] = task.partial_credit.get("notified_team", 0.0)

    score = min(1.0, round(sum(breakdown.values()), 2))
    return score, breakdown
