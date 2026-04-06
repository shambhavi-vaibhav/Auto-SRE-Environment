#!/usr/bin/env python3
"""Baseline inference script for the Incident Response OpenEnv.

Uses the OpenAI client for all LLM calls and emits structured STDOUT logs
in the format required by the automated grader.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
from openai import OpenAI

# ---------------------------------------------------------------------------
# Load .env file if present (no extra dependency needed)
# ---------------------------------------------------------------------------
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# ---------------------------------------------------------------------------
# Configuration from environment variables
# ---------------------------------------------------------------------------
API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
ENV_URL = os.environ.get("ENV_URL", "http://localhost:7860")

if not HF_TOKEN:
    print("ERROR: HF_TOKEN not set. Copy .env.example to .env and add your token.")
    print("       cp .env.example .env")
    sys.exit(1)

client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

BENCHMARK_NAME = "incident_response_env"

SYSTEM_PROMPT = """\
You are an expert Site Reliability Engineer (SRE) responding to an infrastructure incident.

You have access to these actions:
- check_service: Check the status of a service (target=service_name)
- check_logs: View recent logs (target=service_name)
- check_metrics: View metrics (target=service_name)
- restart_service: Restart a service (target=service_name)
- scale_service: Scale replicas (target=service_name, parameters={"replicas": N})
- rollback_deploy: Rollback to previous deployment (target=service_name)
- update_config: Update a config key (target=service_name, parameters={"key": "...", "value": ...})
- send_notification: Notify a channel (target=channel_name, parameters={"message": "..."})

Strategy:
1. First, check the status of all mentioned services to understand scope.
2. Check logs and metrics of services showing errors.
3. Identify the root cause — look for recent deployments, config changes, or OOM kills.
4. Apply the appropriate fix (restart, rollback, config update).
5. Verify the fix by re-checking the service.

Respond with ONLY a JSON object:
{"action_type": "...", "target": "...", "parameters": {...}}
"""


def log_start(task_name: str, model: str) -> None:
    print(f"[START] task={task_name} env={BENCHMARK_NAME} model={model}")


def log_step(step: int, action: str, reward: float, done: bool, error: str | None) -> None:
    err = error if error else "null"
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} "
        f"done={'true' if done else 'false'} error={err}"
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={'true' if success else 'false'} steps={steps} "
        f"score={score:.2f} rewards={rewards_str}"
    )


def env_reset(task_name: str) -> dict:
    resp = requests.post(f"{ENV_URL}/reset", json={"task_name": task_name})
    resp.raise_for_status()
    return resp.json()


def env_step(action_type: str, target: str, parameters: dict | None = None) -> dict:
    payload = {"action_type": action_type, "target": target, "parameters": parameters or {}}
    resp = requests.post(f"{ENV_URL}/step", json=payload)
    resp.raise_for_status()
    return resp.json()


def get_llm_action(messages: list[dict]) -> dict:
    """Call the LLM and parse a JSON action from its response."""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.0,
        max_tokens=256,
    )
    content = response.choices[0].message.content.strip()

    # Try to extract JSON from the response
    if "```" in content:
        # Extract from code block
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Fallback: try to find JSON object in the text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
        raise


def run_task(task_name: str, max_steps: int = 20) -> tuple[bool, float, list[float]]:
    """Run a single task episode. Returns (success, score, rewards)."""

    obs = env_reset(task_name)
    log_start(task_name, MODEL_NAME)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"INCIDENT ALERT:\n{obs['message']}\n\n"
                f"Task: {obs['data'].get('description', '')}\n"
                f"Known services: {obs['data'].get('known_services', [])}\n"
                f"Available actions: {obs['available_actions']}\n\n"
                "Begin your investigation. Respond with a JSON action."
            ),
        },
    ]

    rewards: list[float] = []
    step_num = 0
    done = False
    score = 0.0

    while not done and step_num < max_steps:
        step_num += 1
        error = None

        try:
            action = get_llm_action(messages)
            action_type = action.get("action_type", "check_service")
            target = action.get("target", "")
            parameters = action.get("parameters", {})

            result = env_step(action_type, target, parameters)

            reward = result.get("reward", 0.0) or 0.0
            done = result.get("done", False)
            message = result.get("message", "")
            data = result.get("data", {})
            score = data.get("score_breakdown", {})
            score = sum(score.values()) if isinstance(score, dict) else 0.0
            score = min(1.0, round(score, 2))

            action_str = f"{action_type}:{target}"
            rewards.append(reward)
            log_step(step_num, action_str, reward, done, None)

            # Feed result back to LLM
            messages.append({"role": "assistant", "content": json.dumps(action)})
            messages.append({
                "role": "user",
                "content": (
                    f"Result: {message}\n"
                    f"Data: {json.dumps(data)}\n"
                    f"Reward: {reward:.2f} | Done: {done}\n\n"
                    "What is your next action? Respond with a JSON action."
                    if not done
                    else f"Episode complete. Final result: {message}"
                ),
            })

        except Exception as e:
            error = str(e)
            rewards.append(0.0)
            log_step(step_num, "error", 0.0, False, error)
            # Ask LLM to try again
            messages.append({
                "role": "user",
                "content": f"Error: {error}. Please try a valid JSON action.",
            })

    success = score >= 0.8
    log_end(success, step_num, score, rewards)
    return success, score, rewards


def main():
    tasks = ["service_outage", "db_connection_exhaustion", "cascading_failure"]

    print(f"=" * 60)
    print(f"Incident Response Env — Inference Run")
    print(f"Model: {MODEL_NAME}")
    print(f"API: {API_BASE_URL}")
    print(f"=" * 60)

    results = {}
    for task in tasks:
        print(f"\n{'─' * 40}")
        print(f"Running task: {task}")
        print(f"{'─' * 40}")

        success, score, rewards = run_task(task)
        results[task] = {"success": success, "score": score, "steps": len(rewards)}

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    for task, r in results.items():
        status = "PASS" if r["success"] else "FAIL"
        print(f"  [{status}] {task}: score={r['score']:.2f} steps={r['steps']}")

    avg_score = sum(r["score"] for r in results.values()) / len(results)
    print(f"\n  Average score: {avg_score:.2f}")


if __name__ == "__main__":
    main()
