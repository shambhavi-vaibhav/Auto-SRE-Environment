---
title: Incident Response Env
emoji: 🚨
colorFrom: red
colorTo: yellow
sdk: docker
pinned: false
---

# Incident Response Environment (OpenEnv)

An RL environment where an LLM agent plays the role of a **Site Reliability Engineer (SRE)** responding to infrastructure incidents. Built to the [OpenEnv](https://github.com/meta-pytorch/OpenEnv) spec for agentic RL training.

## What Does This Do?

The environment simulates a production system with multiple services (web frontend, API backend, database, cache, etc.). Things break — services go down, configs get corrupted, bad deployments cause memory leaks. The agent must:

1. **Triage** — check which services are affected
2. **Diagnose** — read logs and metrics to find the root cause
3. **Fix** — apply the right action (restart, rollback, config update)
4. **Verify** — confirm the fix worked

The agent gets **rewards** for good diagnostic steps and correct fixes, and **penalties** for repeating actions or applying wrong fixes.

## The 3 Tasks

| Level | Name | What Happens | What the Agent Must Do |
|-------|------|-------------|----------------------|
| **L1** | `service_outage` | Web frontend is OOM-killed, returning 502s | Check status, read logs, restart the service |
| **L2** | `db_connection_exhaustion` | Someone pushed a bad config (pool_size: 20 → 2), API is timing out | Trace the latency to the config change, update the config back |
| **L3** | `cascading_failure` | A deployment introduced a memory leak in order-service, causing payment + notification + redis to degrade | Find the real root cause among 6 services, rollback the deployment, scale up |

## How to Run It

### Prerequisites

- Python 3.10+
- `make` (pre-installed on Mac/Linux)

### One Command Setup

```bash
# 1. Clone the repo
git clone https://huggingface.co/spaces/Shambhavi0811/incident-response-env
cd incident-response-env

# 2. Add your HuggingFace token (one-liner)
sed -i '' 's/your-token-here/PUT_YOUR_HF_TOKEN_HERE/' .env.example

# 3. Run everything
make run
```

`make run` will:
1. Install all Python dependencies
2. Copy `.env.example` to `.env` (if `.env` doesn't exist)
3. Start the environment server in the background
4. Run the LLM agent against all 3 tasks
5. Print the results and shut down the server

The project uses the free **HuggingFace Inference API** with Llama 3.1 — no OpenAI key needed. You just need a HuggingFace token (free at https://huggingface.co/settings/tokens).

### Other Make Commands

| Command | What It Does |
|---------|-------------|
| `make run` | Full setup + run everything (start here) |
| `make test` | Run all 80 unit + integration tests |
| `make setup` | Just install dependencies |
| `make server` | Start only the env server (for manual testing) |
| `make inference` | Run only the inference script (server must be running) |
| `make docker` | Build and run via Docker |
| `make clean` | Remove Python cache files |

### Manual Steps (if you prefer)

```bash
pip install -r requirements.txt         # Install deps
python -m server.app &                  # Start server (background)
python inference.py                     # Run the agent
```

### Output

You'll see structured logs like:

```
[START] task=service_outage env=incident_response_env model=meta-llama/Llama-3.1-8B-Instruct
[STEP] step=1 action=check_service:web-frontend reward=0.32 done=false error=null
[STEP] step=2 action=check_logs:web-frontend reward=0.22 done=false error=null
[STEP] step=3 action=restart_service:web-frontend reward=0.50 done=true error=null
[END] success=true steps=3 score=1.00 rewards=0.32,0.22,0.50
```

### Using Docker Instead

```bash
docker build -t incident-response-env .
docker run -p 7860:7860 incident-response-env
# In another terminal:
docker run --network host incident-response-env python inference.py
```

## How It Works (Architecture)

```
inference.py                    server/
  │                               ├── app.py      ← FastAPI server (HTTP endpoints)
  │  POST /reset ────────────→    ├── env.py      ← Core environment logic
  │  POST /step  ────────────→    ├── types.py    ← Pydantic models (Action, Observation, State)
  │  GET  /state ────────────→    ├── tasks.py    ← Task definitions (L1/L2/L3 scenarios)
  │                               ├── grader.py   ← Deterministic scoring (partial credit)
  │  LLM (HuggingFace API)        └── rewards.py  ← Shaped reward function
  │  ↕ OpenAI client
  └── Reads alert → asks LLM for action → sends to env → gets reward → repeats
```

**Flow:**
1. `inference.py` calls `/reset` with a task name → gets the incident alert
2. It sends the alert to an LLM and asks "what action should I take?"
3. The LLM responds with a JSON action (e.g., `{"action_type": "check_logs", "target": "web-frontend"}`)
4. `inference.py` sends that action to `/step` → gets observation + reward
5. Repeat until `done=true` or max steps reached

## Available Actions

| Action | What It Does | Example |
|--------|-------------|---------|
| `check_service` | Returns service status (healthy/degraded/down) | `{"action_type": "check_service", "target": "web-frontend"}` |
| `check_logs` | Returns recent log lines | `{"action_type": "check_logs", "target": "api-backend"}` |
| `check_metrics` | Returns CPU, memory, error rate, etc. | `{"action_type": "check_metrics", "target": "postgres-primary"}` |
| `restart_service` | Restarts the service | `{"action_type": "restart_service", "target": "web-frontend"}` |
| `scale_service` | Adds replicas | `{"action_type": "scale_service", "target": "order-service", "parameters": {"replicas": 3}}` |
| `rollback_deploy` | Rolls back to previous version | `{"action_type": "rollback_deploy", "target": "order-service"}` |
| `update_config` | Changes a config value | `{"action_type": "update_config", "target": "api-backend", "parameters": {"key": "max_pool_size", "value": 20}}` |
| `send_notification` | Sends a message to a channel | `{"action_type": "send_notification", "target": "team", "parameters": {"message": "Fixed!"}}` |

## Reward Design

- **Progress rewards**: Score increases as the agent checks the right services, reads logs, and applies fixes
- **Exploration bonus**: +0.02 for first-time checks on relevant services
- **Loop penalty**: -0.1 for repeating the exact same action twice in a row
- **Wrong-fix penalty**: -0.05 for applying a fix to the wrong service
- **Timeout penalty**: -0.3 for running out of steps without resolving

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_BASE_URL` | `https://router.huggingface.co/v1` | LLM API endpoint |
| `MODEL_NAME` | `meta-llama/Llama-3.1-8B-Instruct` | Which model to use |
| `HF_TOKEN` | *(in .env file)* | API key for the LLM |
| `ENV_URL` | `http://localhost:7860` | Where the env server is running |
| `PORT` | `7860` | Port for the env server |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Returns `{"status": "healthy"}` |
| `/metadata` | GET | Environment name, description, available tasks |
| `/schema` | GET | JSON schemas for Action, Observation, State |
| `/reset` | POST | Start a new episode. Body: `{"task_name": "service_outage"}` |
| `/step` | POST | Take an action. Body: `{"action_type": "...", "target": "...", "parameters": {...}}` |
| `/state` | GET | Current episode state (step count, score, services) |

## STDOUT Log Format (for Automated Grading)

The inference script outputs these exact log lines:

```
[START] task=<name> env=incident_response_env model=<model>
[STEP] step=<n> action=<type:target> reward=<0.00> done=<true|false> error=<msg|null>
[END] success=<true|false> steps=<n> score=<0.00> rewards=<r1,r2,...>
```

## File Structure

```
├── .env                 ← Pre-filled config (API key included)
├── .env.example         ← Template for reference
├── Dockerfile           ← One-click Docker/HF Spaces deployment
├── README.md            ← This file
├── inference.py         ← Baseline LLM agent script
├── openenv.yaml         ← OpenEnv manifest
├── pyproject.toml       ← Python package config
├── requirements.txt     ← pip dependencies
├── uv.lock              ← Locked dependency versions
└── server/
    ├── __init__.py
    ├── app.py           ← FastAPI HTTP server
    ├── env.py           ← Environment core (reset/step/state)
    ├── types.py         ← Pydantic models
    ├── tasks.py         ← L1/L2/L3 task definitions
    ├── grader.py        ← Deterministic grading logic
    └── rewards.py       ← Shaped reward computation
```
