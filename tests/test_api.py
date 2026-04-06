"""Integration tests for the FastAPI server."""

import pytest
from fastapi.testclient import TestClient

from server.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "healthy"}


class TestMetadataEndpoint:
    def test_metadata(self, client):
        r = client.get("/metadata")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "incident_response_env"
        assert "tasks" in data
        assert len(data["tasks"]) == 3

    def test_metadata_has_action_types(self, client):
        r = client.get("/metadata")
        data = r.json()
        assert "check_service" in data["action_types"]
        assert "rollback_deploy" in data["action_types"]


class TestSchemaEndpoint:
    def test_schema(self, client):
        r = client.get("/schema")
        assert r.status_code == 200
        data = r.json()
        assert "action" in data
        assert "observation" in data
        assert "state" in data


class TestRootEndpoint:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "running"
        assert "/health" in data["endpoints"]


class TestResetEndpoint:
    def test_reset_default(self, client):
        r = client.post("/reset", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["done"] is False
        assert data["reward"] == 0.0
        assert "available_actions" in data

    def test_reset_specific_task(self, client):
        r = client.post("/reset", json={"task_name": "cascading_failure"})
        assert r.status_code == 200
        data = r.json()
        assert data["data"]["task"] == "cascading_failure"
        assert data["data"]["level"] == 3

    @pytest.mark.parametrize("task", ["service_outage", "db_connection_exhaustion", "cascading_failure"])
    def test_reset_all_tasks(self, client, task):
        r = client.post("/reset", json={"task_name": task})
        assert r.status_code == 200


class TestStepEndpoint:
    def test_step_valid_action(self, client):
        client.post("/reset", json={"task_name": "service_outage"})
        r = client.post("/step", json={
            "action_type": "check_service",
            "target": "web-frontend",
        })
        assert r.status_code == 200
        data = r.json()
        assert "reward" in data
        assert "done" in data
        assert "message" in data

    def test_step_invalid_action_type(self, client):
        client.post("/reset", json={"task_name": "service_outage"})
        r = client.post("/step", json={
            "action_type": "invalid_action",
            "target": "web-frontend",
        })
        assert r.status_code == 400

    def test_step_with_parameters(self, client):
        client.post("/reset", json={"task_name": "db_connection_exhaustion"})
        r = client.post("/step", json={
            "action_type": "update_config",
            "target": "api-backend",
            "parameters": {"key": "max_pool_size", "value": 20},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["done"] is True


class TestStateEndpoint:
    def test_state_after_reset(self, client):
        client.post("/reset", json={"task_name": "service_outage"})
        r = client.get("/state")
        assert r.status_code == 200
        data = r.json()
        assert data["step_count"] == 0
        assert data["task_name"] == "service_outage"
        assert data["resolved"] is False

    def test_state_after_steps(self, client):
        client.post("/reset", json={"task_name": "service_outage"})
        client.post("/step", json={"action_type": "check_service", "target": "web-frontend"})
        client.post("/step", json={"action_type": "check_logs", "target": "web-frontend"})
        r = client.get("/state")
        data = r.json()
        assert data["step_count"] == 2
        assert len(data["actions_taken"]) == 2


class TestFullEpisodeIntegration:
    """End-to-end test: reset → step through → verify final state."""

    def test_l1_full_episode(self, client):
        # Reset
        r = client.post("/reset", json={"task_name": "service_outage"})
        assert r.json()["done"] is False

        # Diagnose
        r = client.post("/step", json={"action_type": "check_service", "target": "web-frontend"})
        assert r.json()["done"] is False
        assert r.json()["reward"] > 0

        r = client.post("/step", json={"action_type": "check_logs", "target": "web-frontend"})
        assert r.json()["done"] is False

        # Fix
        r = client.post("/step", json={"action_type": "restart_service", "target": "web-frontend"})
        assert r.json()["done"] is True
        assert r.json()["reward"] > 0

        # Verify state
        r = client.get("/state")
        data = r.json()
        assert data["resolved"] is True
        assert data["score"] == 1.0
        assert data["step_count"] == 3

    def test_l2_full_episode(self, client):
        """L2 resolves on config fix; verify credit is awarded via API."""
        client.post("/reset", json={"task_name": "db_connection_exhaustion"})
        client.post("/step", json={"action_type": "check_service", "target": "api-backend"})
        client.post("/step", json={"action_type": "check_logs", "target": "api-backend"})
        client.post("/step", json={"action_type": "check_metrics", "target": "api-backend"})
        r = client.post("/step", json={
            "action_type": "update_config",
            "target": "api-backend",
            "parameters": {"key": "max_pool_size", "value": 20},
        })
        assert r.json()["done"] is True
        state = client.get("/state").json()
        assert state["score"] >= 0.9
        assert state["resolved"] is True

    def test_l3_full_episode(self, client):
        """L3: scale and notify before rollback to get full credit."""
        client.post("/reset", json={"task_name": "cascading_failure"})
        client.post("/step", json={"action_type": "check_service", "target": "payment-service"})
        client.post("/step", json={"action_type": "check_service", "target": "order-service"})
        client.post("/step", json={"action_type": "check_logs", "target": "order-service"})
        client.post("/step", json={"action_type": "check_metrics", "target": "order-service"})
        # Scale and notify before rollback (rollback resolves the episode)
        client.post("/step", json={
            "action_type": "scale_service",
            "target": "order-service",
            "parameters": {"replicas": 3},
        })
        client.post("/step", json={
            "action_type": "send_notification",
            "target": "team",
            "parameters": {"message": "Incident resolved"},
        })
        r = client.post("/step", json={"action_type": "rollback_deploy", "target": "order-service"})
        assert r.json()["done"] is True
        state = client.get("/state").json()
        assert state["score"] == 1.0
        assert state["resolved"] is True
