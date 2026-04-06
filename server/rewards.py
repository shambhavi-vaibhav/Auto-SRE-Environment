"""Shaped reward function with incremental rewards and penalties."""

from __future__ import annotations

from typing import List

from .tasks import TaskDef
from .types import Action, ActionType, State

# Penalty constants
LOOP_PENALTY = -0.1          # Repeating the exact same action
IRRELEVANT_PENALTY = -0.05   # Action on a service unrelated to the incident
MAX_STEPS_PENALTY = -0.3     # Running out of steps without resolving


def compute_step_reward(
    task: TaskDef,
    state: State,
    action: Action,
    action_history: List[Action],
    prev_score: float,
    new_score: float,
) -> float:
    """Compute the shaped reward for a single step.

    Returns a float reward. Positive for progress, negative for waste/loops.
    """
    reward = 0.0

    # 1. Progress reward: delta between previous and new grader score
    delta = new_score - prev_score
    if delta > 0:
        reward += delta

    # 2. Diagnostic bonus: small reward for first-time checks on relevant services
    if action.action_type in (ActionType.CHECK_SERVICE, ActionType.CHECK_LOGS, ActionType.CHECK_METRICS):
        is_first_check = not any(
            a.action_type == action.action_type and a.target == action.target
            for a in action_history[:-1]
        )
        if is_first_check and action.target in task.services:
            reward += 0.02  # Small exploration bonus

    # 3. Loop penalty: exact duplicate of the previous action
    if len(action_history) >= 2:
        prev = action_history[-2]
        if (
            prev.action_type == action.action_type
            and prev.target == action.target
            and prev.parameters == action.parameters
        ):
            reward += LOOP_PENALTY

    # 4. Wrong-fix penalty: applying a fix to the wrong service
    fix_actions = {ActionType.RESTART_SERVICE, ActionType.ROLLBACK_DEPLOY,
                   ActionType.UPDATE_CONFIG, ActionType.SCALE_SERVICE}
    if action.action_type in fix_actions and action.target != task.fix_target:
        reward += IRRELEVANT_PENALTY

    # 5. Step-budget penalty on final step if unresolved
    if state.step_count >= state.max_steps and not state.resolved:
        reward += MAX_STEPS_PENALTY

    return round(reward, 2)
