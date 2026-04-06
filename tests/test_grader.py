"""Unit tests for the deterministic grader."""

import pytest

from server.grader import grade
from server.tasks import TASK_L1, TASK_L2, TASK_L3
from server.types import Action, ActionType, State


def _make_state(task):
    return State(task_name=task.name, task_level=task.level, max_steps=task.max_steps)


class TestGraderL1:
    def test_perfect_score(self):
        """Check + logs + restart = 1.0"""
        actions = [
            Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend"),
            Action(action_type=ActionType.CHECK_LOGS, target="web-frontend"),
            Action(action_type=ActionType.RESTART_SERVICE, target="web-frontend"),
        ]
        score, breakdown = grade(TASK_L1, _make_state(TASK_L1), actions)
        assert score == 1.0
        assert "checked_root_cause" in breakdown
        assert "checked_logs" in breakdown
        assert "applied_fix" in breakdown

    def test_no_actions_zero_score(self):
        score, breakdown = grade(TASK_L1, _make_state(TASK_L1), [])
        assert score == 0.0
        assert breakdown == {}

    def test_partial_credit_check_only(self):
        actions = [Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend")]
        score, _ = grade(TASK_L1, _make_state(TASK_L1), actions)
        assert 0 < score < 1.0

    def test_wrong_service_no_credit(self):
        actions = [
            Action(action_type=ActionType.RESTART_SERVICE, target="postgres-primary"),
        ]
        score, _ = grade(TASK_L1, _make_state(TASK_L1), actions)
        assert score == 0.0


class TestGraderL2:
    def test_full_fix(self):
        actions = [
            Action(action_type=ActionType.CHECK_SERVICE, target="api-backend"),
            Action(action_type=ActionType.CHECK_LOGS, target="api-backend"),
            Action(action_type=ActionType.CHECK_METRICS, target="api-backend"),
            Action(action_type=ActionType.UPDATE_CONFIG, target="api-backend",
                   parameters={"key": "max_pool_size", "value": 20}),
            Action(action_type=ActionType.CHECK_SERVICE, target="api-backend"),
        ]
        score, breakdown = grade(TASK_L2, _make_state(TASK_L2), actions)
        assert score == 1.0
        assert "verified_fix" in breakdown

    def test_wrong_pool_size_no_fix_credit(self):
        """Pool size < 10 should not get fix credit."""
        actions = [
            Action(action_type=ActionType.UPDATE_CONFIG, target="api-backend",
                   parameters={"key": "max_pool_size", "value": 3}),
        ]
        score, breakdown = grade(TASK_L2, _make_state(TASK_L2), actions)
        assert "applied_fix" not in breakdown

    def test_acceptable_pool_size(self):
        """Any pool size >= 10 should count."""
        actions = [
            Action(action_type=ActionType.UPDATE_CONFIG, target="api-backend",
                   parameters={"key": "max_pool_size", "value": 15}),
        ]
        score, breakdown = grade(TASK_L2, _make_state(TASK_L2), actions)
        assert "applied_fix" in breakdown


class TestGraderL3:
    def test_full_resolution(self):
        actions = [
            Action(action_type=ActionType.CHECK_SERVICE, target="payment-service"),
            Action(action_type=ActionType.CHECK_SERVICE, target="order-service"),
            Action(action_type=ActionType.CHECK_LOGS, target="order-service"),
            Action(action_type=ActionType.CHECK_METRICS, target="order-service"),
            Action(action_type=ActionType.ROLLBACK_DEPLOY, target="order-service"),
            Action(action_type=ActionType.SCALE_SERVICE, target="order-service",
                   parameters={"replicas": 3}),
            Action(action_type=ActionType.SEND_NOTIFICATION, target="team",
                   parameters={"message": "Incident resolved"}),
        ]
        score, breakdown = grade(TASK_L3, _make_state(TASK_L3), actions)
        assert score == 1.0

    def test_rollback_only_partial(self):
        actions = [
            Action(action_type=ActionType.ROLLBACK_DEPLOY, target="order-service"),
        ]
        score, _ = grade(TASK_L3, _make_state(TASK_L3), actions)
        assert 0 < score < 0.5

    def test_score_capped_at_one(self):
        """Score should never exceed 1.0."""
        actions = [
            Action(action_type=ActionType.CHECK_SERVICE, target="payment-service"),
            Action(action_type=ActionType.CHECK_SERVICE, target="order-service"),
            Action(action_type=ActionType.CHECK_LOGS, target="order-service"),
            Action(action_type=ActionType.CHECK_METRICS, target="order-service"),
            Action(action_type=ActionType.ROLLBACK_DEPLOY, target="order-service"),
            Action(action_type=ActionType.SCALE_SERVICE, target="order-service"),
            Action(action_type=ActionType.SEND_NOTIFICATION, target="team"),
        ]
        score, _ = grade(TASK_L3, _make_state(TASK_L3), actions)
        assert score <= 1.0


class TestGraderDeterminism:
    """Graders must be deterministic — same input, same output."""

    @pytest.mark.parametrize("task", [TASK_L1, TASK_L2, TASK_L3])
    def test_same_input_same_output(self, task):
        actions = [
            Action(action_type=ActionType.CHECK_SERVICE, target=task.root_cause_service),
            Action(action_type=ActionType.CHECK_LOGS, target=task.root_cause_service),
        ]
        state = _make_state(task)
        score1, b1 = grade(task, state, actions)
        score2, b2 = grade(task, state, actions)
        assert score1 == score2
        assert b1 == b2
