"""Unit tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from server.types import Action, ActionType, Observation, ServiceStatus, State


class TestAction:
    def test_valid_action(self):
        a = Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend")
        assert a.action_type == ActionType.CHECK_SERVICE
        assert a.target == "web-frontend"
        assert a.parameters == {}
        assert a.metadata == {}

    def test_action_with_params(self):
        a = Action(
            action_type=ActionType.UPDATE_CONFIG,
            target="api-backend",
            parameters={"key": "max_pool_size", "value": 20},
        )
        assert a.parameters["key"] == "max_pool_size"
        assert a.parameters["value"] == 20

    def test_action_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            Action(action_type=ActionType.CHECK_SERVICE, target="x", bogus="field")

    def test_invalid_action_type(self):
        with pytest.raises(ValidationError):
            Action(action_type="not_real", target="x")


class TestObservation:
    def test_defaults(self):
        obs = Observation()
        assert obs.done is False
        assert obs.reward is None
        assert obs.message == ""
        assert obs.data == {}
        assert obs.available_actions == []

    def test_full_observation(self):
        obs = Observation(
            done=True,
            reward=0.5,
            message="Service restarted",
            data={"status": "healthy"},
            available_actions=["check_service"],
        )
        assert obs.done is True
        assert obs.reward == 0.5


class TestState:
    def test_defaults(self):
        s = State()
        assert s.episode_id is None
        assert s.step_count == 0
        assert s.resolved is False

    def test_step_count_non_negative(self):
        with pytest.raises(ValidationError):
            State(step_count=-1)

    def test_allows_extra_fields(self):
        # State has extra="allow"
        s = State(custom_field="hello")
        assert s.custom_field == "hello"


class TestServiceStatus:
    def test_all_statuses(self):
        assert ServiceStatus.HEALTHY.value == "healthy"
        assert ServiceStatus.DEGRADED.value == "degraded"
        assert ServiceStatus.DOWN.value == "down"
        assert ServiceStatus.OVERLOADED.value == "overloaded"
