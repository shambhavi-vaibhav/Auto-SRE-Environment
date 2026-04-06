"""Unit tests for task definitions."""

from server.tasks import TASKS, TASK_L1, TASK_L2, TASK_L3


class TestTaskDefinitions:
    def test_all_tasks_registered(self):
        assert "service_outage" in TASKS
        assert "db_connection_exhaustion" in TASKS
        assert "cascading_failure" in TASKS
        assert len(TASKS) == 3

    def test_task_levels(self):
        assert TASK_L1.level == 1
        assert TASK_L2.level == 2
        assert TASK_L3.level == 3

    def test_task_has_services(self):
        for task in TASKS.values():
            assert len(task.services) > 0

    def test_root_cause_exists_in_services(self):
        for task in TASKS.values():
            assert task.root_cause_service in task.services

    def test_fix_target_exists_in_services(self):
        for task in TASKS.values():
            assert task.fix_target in task.services

    def test_partial_credit_sums_to_one(self):
        for name, task in TASKS.items():
            total = sum(task.partial_credit.values())
            assert 0.99 <= total <= 1.01, f"{name} partial credit sums to {total}"

    def test_max_steps_positive(self):
        for task in TASKS.values():
            assert task.max_steps > 0

    def test_l3_has_red_herrings(self):
        """L3 should have services beyond the root cause."""
        non_root = [s for s in TASK_L3.services if s != TASK_L3.root_cause_service]
        assert len(non_root) >= 3, "L3 needs multiple non-root services as red herrings"
