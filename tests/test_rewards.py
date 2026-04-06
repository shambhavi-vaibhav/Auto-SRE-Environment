"""Unit tests for the shaped reward function."""

from server.rewards import compute_step_reward, LOOP_PENALTY, IRRELEVANT_PENALTY, MAX_STEPS_PENALTY
from server.tasks import TASK_L1, TASK_L3
from server.types import Action, ActionType, State


def _state(step=1, max_steps=20, resolved=False):
    return State(step_count=step, max_steps=max_steps, resolved=resolved)


class TestProgressReward:
    def test_positive_delta_gives_reward(self):
        action = Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend")
        r = compute_step_reward(TASK_L1, _state(), action, [action], 0.0, 0.3)
        assert r > 0

    def test_no_delta_no_progress_reward(self):
        action = Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend")
        r = compute_step_reward(TASK_L1, _state(), action, [action], 0.3, 0.3)
        # Should only get exploration bonus, no progress reward
        assert r >= 0


class TestExplorationBonus:
    def test_first_check_gets_bonus(self):
        action = Action(action_type=ActionType.CHECK_LOGS, target="web-frontend")
        r = compute_step_reward(TASK_L1, _state(), action, [action], 0.0, 0.0)
        assert r == 0.02

    def test_duplicate_check_no_bonus(self):
        action = Action(action_type=ActionType.CHECK_LOGS, target="web-frontend")
        history = [action, action]
        r = compute_step_reward(TASK_L1, _state(), action, history, 0.0, 0.0)
        # Gets loop penalty instead
        assert r < 0


class TestLoopPenalty:
    def test_exact_duplicate_penalized(self):
        action = Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend")
        history = [action, action]
        r = compute_step_reward(TASK_L1, _state(step=2), action, history, 0.3, 0.3)
        assert r <= LOOP_PENALTY

    def test_different_target_no_penalty(self):
        a1 = Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend")
        a2 = Action(action_type=ActionType.CHECK_SERVICE, target="api-gateway")
        history = [a1, a2]
        r = compute_step_reward(TASK_L1, _state(step=2), a2, history, 0.0, 0.0)
        assert r >= 0  # exploration bonus, no loop penalty


class TestWrongFixPenalty:
    def test_fix_wrong_service(self):
        action = Action(action_type=ActionType.RESTART_SERVICE, target="postgres-primary")
        r = compute_step_reward(TASK_L1, _state(), action, [action], 0.0, 0.0)
        assert IRRELEVANT_PENALTY in [r] or r < 0

    def test_fix_correct_service_no_penalty(self):
        action = Action(action_type=ActionType.RESTART_SERVICE, target="web-frontend")
        r = compute_step_reward(TASK_L1, _state(), action, [action], 0.0, 0.5)
        assert r > 0


class TestTimeoutPenalty:
    def test_max_steps_unresolved(self):
        action = Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend")
        r = compute_step_reward(TASK_L1, _state(step=20, max_steps=20), action, [action], 0.0, 0.0)
        # Timeout penalty (-0.3) + exploration bonus (+0.02) = -0.28
        assert r < 0

    def test_max_steps_resolved_no_penalty(self):
        action = Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend")
        r = compute_step_reward(
            TASK_L1, _state(step=20, max_steps=20, resolved=True), action, [action], 1.0, 1.0
        )
        assert r >= 0
