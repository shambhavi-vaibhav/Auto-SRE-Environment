"""Task definitions for L1-L3 incident response scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .types import ServiceStatus


@dataclass
class ServiceDef:
    name: str
    status: ServiceStatus
    logs: List[str]
    metrics: Dict[str, float]
    config: Dict[str, Any] = field(default_factory=dict)
    deploy_version: str = "v1.0.0"


@dataclass
class TaskDef:
    name: str
    level: int
    description: str
    alert_message: str
    services: Dict[str, ServiceDef]
    root_cause_service: str
    required_fix: str  # action_type that resolves
    fix_target: str  # service to apply fix to
    fix_params: Dict[str, Any] = field(default_factory=dict)
    max_steps: int = 20
    partial_credit: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# L1: Web server is down — identify and restart
# ---------------------------------------------------------------------------
TASK_L1 = TaskDef(
    name="service_outage",
    level=1,
    description=(
        "ALERT: The customer-facing web application is returning 502 errors. "
        "Users are unable to access the platform. Diagnose and resolve."
    ),
    alert_message="PagerDuty: 502 errors spiking on web-frontend. 95th-percentile error rate > 50%.",
    services={
        "web-frontend": ServiceDef(
            name="web-frontend",
            status=ServiceStatus.DOWN,
            logs=[
                "[ERROR] 2026-04-05T02:13:01Z Process exited with code 137 (OOM killed)",
                "[ERROR] 2026-04-05T02:13:02Z Failed to bind to port 8080 — address already in use",
                "[ERROR] 2026-04-05T02:13:03Z Service health check failed 5 consecutive times",
                "[INFO]  2026-04-05T02:13:04Z Marking service as DOWN",
            ],
            metrics={"cpu_pct": 0.0, "mem_mb": 0, "req_per_sec": 0, "error_rate": 1.0},
        ),
        "api-gateway": ServiceDef(
            name="api-gateway",
            status=ServiceStatus.HEALTHY,
            logs=[
                "[WARN]  2026-04-05T02:13:05Z Upstream web-frontend unreachable, returning 502",
                "[INFO]  2026-04-05T02:12:00Z Health check OK",
            ],
            metrics={"cpu_pct": 12.3, "mem_mb": 256, "req_per_sec": 450, "error_rate": 0.52},
        ),
        "postgres-primary": ServiceDef(
            name="postgres-primary",
            status=ServiceStatus.HEALTHY,
            logs=["[INFO]  2026-04-05T02:12:00Z Checkpoint complete"],
            metrics={"cpu_pct": 8.1, "mem_mb": 1024, "connections": 42, "error_rate": 0.0},
        ),
    },
    root_cause_service="web-frontend",
    required_fix="restart_service",
    fix_target="web-frontend",
    max_steps=15,
    partial_credit={
        "checked_root_cause": 0.3,
        "checked_logs": 0.2,
        "identified_cause": 0.2,
        "applied_fix": 0.3,
    },
)


# ---------------------------------------------------------------------------
# L2: DB connection pool exhaustion from bad config change
# ---------------------------------------------------------------------------
TASK_L2 = TaskDef(
    name="db_connection_exhaustion",
    level=2,
    description=(
        "ALERT: API response times have spiked to 12s (normal: 200ms). "
        "No recent deployments, but a config change was pushed 30 minutes ago. "
        "Diagnose the root cause and fix it."
    ),
    alert_message=(
        "Grafana: api-backend p99 latency 12,340ms. "
        "postgres-primary active connections at 98% capacity."
    ),
    services={
        "web-frontend": ServiceDef(
            name="web-frontend",
            status=ServiceStatus.DEGRADED,
            logs=[
                "[WARN]  2026-04-05T03:00:12Z Slow upstream response from api-backend (11.8s)",
                "[WARN]  2026-04-05T03:00:15Z Request timeout for /api/v1/listings",
            ],
            metrics={"cpu_pct": 15.0, "mem_mb": 310, "req_per_sec": 120, "error_rate": 0.35},
        ),
        "api-backend": ServiceDef(
            name="api-backend",
            status=ServiceStatus.DEGRADED,
            logs=[
                "[ERROR] 2026-04-05T03:00:01Z Connection pool exhausted — waiting for available connection",
                "[ERROR] 2026-04-05T03:00:02Z Timeout acquiring DB connection after 10000ms",
                "[WARN]  2026-04-05T02:30:00Z Config reload: max_pool_size changed from 20 to 2",
                "[INFO]  2026-04-05T02:29:55Z Applying config update from config-service",
            ],
            metrics={"cpu_pct": 85.2, "mem_mb": 1800, "req_per_sec": 45, "error_rate": 0.78},
            config={"max_pool_size": 2, "pool_timeout_ms": 10000, "max_retries": 3},
        ),
        "postgres-primary": ServiceDef(
            name="postgres-primary",
            status=ServiceStatus.OVERLOADED,
            logs=[
                "[WARN]  2026-04-05T03:00:05Z Max connections approaching limit (196/200)",
                "[WARN]  2026-04-05T03:00:06Z Long-running queries detected (avg 8.2s)",
                "[INFO]  2026-04-05T02:00:00Z Checkpoint complete",
            ],
            metrics={"cpu_pct": 72.0, "mem_mb": 3800, "connections": 196, "error_rate": 0.05},
        ),
        "redis-cache": ServiceDef(
            name="redis-cache",
            status=ServiceStatus.HEALTHY,
            logs=["[INFO]  2026-04-05T02:00:00Z Background save completed"],
            metrics={"cpu_pct": 5.0, "mem_mb": 512, "hit_rate": 0.92, "error_rate": 0.0},
        ),
    },
    root_cause_service="api-backend",
    required_fix="update_config",
    fix_target="api-backend",
    fix_params={"key": "max_pool_size", "value": 20},
    max_steps=20,
    partial_credit={
        "checked_root_cause": 0.15,
        "checked_logs": 0.15,
        "checked_metrics": 0.1,
        "identified_config": 0.2,
        "applied_fix": 0.3,
        "verified_fix": 0.1,
    },
)


# ---------------------------------------------------------------------------
# L3: Cascading failure from memory-leaking deployment — with red herrings
# ---------------------------------------------------------------------------
TASK_L3 = TaskDef(
    name="cascading_failure",
    level=3,
    description=(
        "ALERT: Multiple services degraded. payment-service, order-service, and "
        "notification-service all showing elevated error rates. A deployment to "
        "order-service went out 2 hours ago. Several teams are pointing fingers. "
        "Find the true root cause and stabilize the system."
    ),
    alert_message=(
        "PagerDuty: Multiple critical alerts.\n"
        "  - payment-service: 504 Gateway Timeouts (15%)\n"
        "  - order-service: OOM kills every ~20min\n"
        "  - notification-service: message queue backlog 50k+\n"
        "  - redis-sessions: evictions spiking"
    ),
    services={
        "api-gateway": ServiceDef(
            name="api-gateway",
            status=ServiceStatus.DEGRADED,
            logs=[
                "[WARN]  2026-04-05T04:00:01Z Upstream order-service: 504 timeout",
                "[WARN]  2026-04-05T04:00:02Z Upstream payment-service: 504 timeout",
                "[INFO]  2026-04-05T03:55:00Z Rate limiter engaged for /api/v1/orders",
            ],
            metrics={"cpu_pct": 45.0, "mem_mb": 400, "req_per_sec": 800, "error_rate": 0.18},
        ),
        "order-service": ServiceDef(
            name="order-service",
            status=ServiceStatus.DOWN,
            logs=[
                "[ERROR] 2026-04-05T04:00:10Z OOM killed — RSS 7.8GB (limit 8GB)",
                "[ERROR] 2026-04-05T03:40:05Z OOM killed — RSS 7.9GB (limit 8GB)",
                "[ERROR] 2026-04-05T03:20:02Z OOM killed — RSS 7.7GB (limit 8GB)",
                "[WARN]  2026-04-05T03:00:00Z Memory usage growing linearly: 2.1GB -> 4.3GB -> 6.5GB",
                "[INFO]  2026-04-05T02:00:00Z Deployed v2.4.1 (commit abc123f: 'add order analytics pipeline')",
                "[INFO]  2026-04-05T02:00:01Z New feature flag: analytics_pipeline=enabled",
            ],
            metrics={"cpu_pct": 95.0, "mem_mb": 7800, "req_per_sec": 10, "error_rate": 0.92},
            config={"analytics_pipeline": "enabled", "cache_ttl": 300, "max_retries": 5},
            deploy_version="v2.4.1",
        ),
        "payment-service": ServiceDef(
            name="payment-service",
            status=ServiceStatus.DEGRADED,
            logs=[
                "[ERROR] 2026-04-05T04:00:15Z Timeout calling order-service for validation (10s)",
                "[WARN]  2026-04-05T04:00:16Z Falling back to cached order data",
                "[WARN]  2026-04-05T04:00:17Z 3 payment retries failed for order #98712",
                "[INFO]  2026-04-05T02:00:00Z No recent deployments",
            ],
            metrics={"cpu_pct": 30.0, "mem_mb": 600, "req_per_sec": 200, "error_rate": 0.15},
        ),
        "notification-service": ServiceDef(
            name="notification-service",
            status=ServiceStatus.DEGRADED,
            logs=[
                "[WARN]  2026-04-05T04:00:20Z Message queue backlog: 52,341 messages",
                "[WARN]  2026-04-05T04:00:21Z Cannot reach order-service for order details",
                "[INFO]  2026-04-05T02:00:00Z No recent deployments",
            ],
            metrics={"cpu_pct": 20.0, "mem_mb": 350, "queue_backlog": 52341, "error_rate": 0.08},
        ),
        "redis-sessions": ServiceDef(
            name="redis-sessions",
            status=ServiceStatus.DEGRADED,
            logs=[
                "[WARN]  2026-04-05T04:00:25Z Eviction policy triggered — maxmemory reached",
                "[WARN]  2026-04-05T04:00:26Z 1,203 keys evicted in last 5 minutes",
                "[INFO]  2026-04-05T02:00:00Z No config changes",
            ],
            metrics={"cpu_pct": 40.0, "mem_mb": 2048, "hit_rate": 0.61, "evictions_per_min": 240},
        ),
        "postgres-primary": ServiceDef(
            name="postgres-primary",
            status=ServiceStatus.HEALTHY,
            logs=[
                "[INFO]  2026-04-05T04:00:00Z Checkpoint complete",
                "[INFO]  2026-04-05T03:00:00Z Routine vacuum completed",
            ],
            metrics={"cpu_pct": 18.0, "mem_mb": 2048, "connections": 85, "error_rate": 0.0},
        ),
    },
    root_cause_service="order-service",
    required_fix="rollback_deploy",
    fix_target="order-service",
    max_steps=25,
    partial_credit={
        "checked_order_service": 0.1,
        "checked_order_logs": 0.1,
        "checked_order_metrics": 0.05,
        "identified_memory_leak": 0.15,
        "identified_deployment": 0.1,
        "ruled_out_red_herring": 0.05,
        "applied_rollback": 0.25,
        "scaled_up": 0.1,
        "notified_team": 0.1,
    },
)


TASKS = {
    "service_outage": TASK_L1,
    "db_connection_exhaustion": TASK_L2,
    "cascading_failure": TASK_L3,
}
