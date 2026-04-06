"""FastAPI server exposing the OpenEnv endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .env import IncidentResponseEnv
from .tasks import TASKS
from .types import Action, ActionType

app = FastAPI(
    title="Incident Response Environment",
    description="OpenEnv-compliant environment simulating IT incident response workflows.",
    version="0.1.0",
)

# Single-session env instance
_env = IncidentResponseEnv()


@app.get("/")
def root():
    return {
        "name": "Incident Response Environment",
        "status": "running",
        "docs": "/docs",
        "endpoints": ["/health", "/metadata", "/schema", "/reset", "/step", "/state"],
    }


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ResetRequest(BaseModel):
    task_name: Optional[str] = "service_outage"
    seed: Optional[int] = None


class StepRequest(BaseModel):
    action_type: str
    target: str
    parameters: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# OpenEnv endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/metadata")
def metadata():
    return {
        "name": "incident_response_env",
        "description": (
            "Simulates IT incident response workflows. An agent must triage, "
            "diagnose, and resolve infrastructure incidents across 3 difficulty levels."
        ),
        "tasks": list(TASKS.keys()),
        "action_types": [a.value for a in ActionType],
    }


@app.get("/schema")
def schema():
    return {
        "action": Action.model_json_schema(),
        "observation": {
            "type": "object",
            "properties": {
                "done": {"type": "boolean"},
                "reward": {"type": "number"},
                "message": {"type": "string"},
                "data": {"type": "object"},
                "available_actions": {"type": "array", "items": {"type": "string"}},
            },
        },
        "state": {
            "type": "object",
            "properties": {
                "episode_id": {"type": "string"},
                "step_count": {"type": "integer"},
                "task_name": {"type": "string"},
                "task_level": {"type": "integer"},
                "services": {"type": "object"},
                "score": {"type": "number"},
                "resolved": {"type": "boolean"},
            },
        },
    }


@app.post("/reset")
def reset(req: ResetRequest):
    obs = _env.reset(seed=req.seed, task_name=req.task_name)
    return obs.model_dump()


@app.post("/step")
def step(req: StepRequest):
    try:
        action_type = ActionType(req.action_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action_type '{req.action_type}'. Must be one of: {[a.value for a in ActionType]}",
        )

    action = Action(
        action_type=action_type,
        target=req.target,
        parameters=req.parameters,
    )
    obs = _env.step(action)
    return obs.model_dump()


@app.get("/state")
def get_state():
    return _env.state.model_dump()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    import os
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("server.app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
