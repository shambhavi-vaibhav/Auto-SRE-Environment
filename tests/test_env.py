"""Unit tests for the environment core logic."""

import pytest

from server.env import IncidentResponseEnv
from server.types import Action, ActionType, ServiceStatus


class TestReset:
    def test_returns_observation(self):
        env = IncidentResponseEnv("service_outage")
        obs = env.reset()
        assert obs.done is False
        assert obs.reward == 0.0
        assert "service_outage" in obs.data["task"]
        assert len(obs.available_actions) > 0

    def test_state_initialized(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        s = env.state
        assert s.step_count == 0
        assert s.score == 0.0
        assert s.resolved is False
        assert s.episode_id is not None

    def test_reset_clears_previous_episode(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        env.step(Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend"))
        assert env.state.step_count == 1

        env.reset()
        assert env.state.step_count == 0
        assert env.state.score == 0.0

    def test_reset_with_different_task(self):
        env = IncidentResponseEnv("service_outage")
        env.reset(task_name="cascading_failure")
        assert env.state.task_name == "cascading_failure"
        assert env.state.task_level == 3

    @pytest.mark.parametrize("task", ["service_outage", "db_connection_exhaustion", "cascading_failure"])
    def test_all_tasks_reset(self, task):
        env = IncidentResponseEnv(task)
        obs = env.reset()
        assert obs.done is False
        assert len(obs.data["known_services"]) > 0


class TestStep:
    def test_step_increments_count(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        env.step(Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend"))
        assert env.state.step_count == 1

    def test_step_returns_observation(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        obs = env.step(Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend"))
        assert isinstance(obs.reward, float)
        assert isinstance(obs.done, bool)
        assert obs.message != ""

    def test_unknown_service(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        obs = env.step(Action(action_type=ActionType.CHECK_SERVICE, target="nonexistent"))
        assert "error" in obs.data or "Unknown" in obs.message

    def test_check_logs_returns_log_lines(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        obs = env.step(Action(action_type=ActionType.CHECK_LOGS, target="web-frontend"))
        assert "logs" in obs.data
        assert len(obs.data["logs"]) > 0

    def test_check_metrics_returns_metrics(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        obs = env.step(Action(action_type=ActionType.CHECK_METRICS, target="web-frontend"))
        assert "metrics" in obs.data

    def test_actions_tracked_in_state(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        env.step(Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend"))
        env.step(Action(action_type=ActionType.CHECK_LOGS, target="web-frontend"))
        assert len(env.state.actions_taken) == 2
        assert "check_service:web-frontend" in env.state.actions_taken


class TestResolution:
    def test_l1_resolves_on_restart(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        env.step(Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend"))
        obs = env.step(Action(action_type=ActionType.RESTART_SERVICE, target="web-frontend"))
        assert obs.done is True
        assert env.state.resolved is True

    def test_l2_resolves_on_config_fix(self):
        env = IncidentResponseEnv("db_connection_exhaustion")
        env.reset()
        obs = env.step(Action(
            action_type=ActionType.UPDATE_CONFIG,
            target="api-backend",
            parameters={"key": "max_pool_size", "value": 20},
        ))
        assert obs.done is True
        assert env.state.resolved is True

    def test_l3_resolves_on_rollback(self):
        env = IncidentResponseEnv("cascading_failure")
        env.reset()
        obs = env.step(Action(action_type=ActionType.ROLLBACK_DEPLOY, target="order-service"))
        assert obs.done is True
        assert env.state.resolved is True

    def test_wrong_fix_does_not_resolve(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        obs = env.step(Action(action_type=ActionType.RESTART_SERVICE, target="postgres-primary"))
        assert obs.done is False
        assert env.state.resolved is False


class TestMaxSteps:
    def test_terminates_at_max_steps(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        # Take max_steps actions without fixing
        for _ in range(env.state.max_steps):
            obs = env.step(Action(action_type=ActionType.CHECK_SERVICE, target="api-gateway"))
        assert obs.done is True
        assert env.state.resolved is False

    def test_no_actions_after_done(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        env.step(Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend"))
        env.step(Action(action_type=ActionType.RESTART_SERVICE, target="web-frontend"))
        # Already resolved, further steps should return terminal obs
        obs = env.step(Action(action_type=ActionType.CHECK_SERVICE, target="web-frontend"))
        assert obs.done is True
        assert obs.available_actions == []


class TestStateProperty:
    def test_state_is_copy(self):
        """Modifying returned state should not affect env."""
        env = IncidentResponseEnv("service_outage")
        env.reset()
        s = env.state
        s.step_count = 999
        assert env.state.step_count == 0

    def test_state_reflects_services(self):
        env = IncidentResponseEnv("service_outage")
        env.reset()
        assert env.state.services["web-frontend"] == ServiceStatus.DOWN
        env.step(Action(action_type=ActionType.RESTART_SERVICE, target="web-frontend"))
        assert env.state.services["web-frontend"] == ServiceStatus.HEALTHY
