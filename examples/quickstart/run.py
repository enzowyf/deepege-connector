"""Create, poll, confirm, and deliver a video job against the mock or a live API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from mcp import Client

from deepege_connector.api import OpenAPIClient
from deepege_connector.config import Settings
from deepege_connector.server import create_server

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PROMPT = "A sunrise over the sea"
DEFAULT_MOCK_KEY = "sk-test-alice"
# The in-repo mock advances after two GETs or about 200ms, so cap the wait.
MOCK_POLL_CAP_S = 0.25


def _tool_text(result: Any) -> str:
    parts: list[str] = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def tool_payload(result: Any) -> dict[str, Any]:
    if result.structured_content is not None and isinstance(result.structured_content, dict):
        return result.structured_content
    text = _tool_text(result)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end >= start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError(f"tool result is not an object: {text}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Deepege video job through the MCP connector."
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--duration-seconds", type=int, default=15)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the plan without prompting. Agents must not use this by default.",
    )
    parser.add_argument(
        "--api-base-url",
        default=None,
        help="Live Open API origin. Default: in-process mock.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="User API key. Defaults to DEEPEGE_API_KEY, or sk-test-alice for the mock.",
    )
    return parser.parse_args(argv)


def _api_key(args: argparse.Namespace) -> str:
    if args.api_key:
        return args.api_key
    env = os.environ.get("DEEPEGE_API_KEY")
    if env and env.strip():
        return env.strip()
    if args.api_base_url:
        raise SystemExit("set --api-key or DEEPEGE_API_KEY when using --api-base-url")
    return DEFAULT_MOCK_KEY


def _print_error(payload: dict[str, Any]) -> None:
    error = payload.get("error", payload)
    print("Tool error:")
    print(json.dumps(error, ensure_ascii=False, indent=2))
    if isinstance(error, dict):
        if error.get("code") == "quote_stale":
            print("The plan is no longer current. Fetch the job and ask again before confirming.")
        elif error.get("code") == "credits_insufficient":
            recharge = error.get("recharge_url")
            if recharge:
                print(f"Credits are insufficient. Recharge: {recharge}")
            else:
                print("Credits are insufficient.")
        elif error.get("retryable") is True:
            print("This job cannot be recovered. Start a new request if you want to retry.")
        retry_after = payload.get("retry_after")
        if retry_after is None and isinstance(error, dict):
            retry_after = error.get("retry_after")
        if retry_after is not None:
            print(f"Wait {retry_after} seconds before calling again.")


def _print_plan(job: dict[str, Any]) -> None:
    plan = job.get("plan") or {}
    print("Plan (ask a human before confirming spend):")
    for key in (
        "plan_id",
        "title",
        "duration_seconds",
        "style",
        "estimated_credits",
        "max_credits",
        "charges_before_confirm",
        "credit_balance",
    ):
        print(f"  {key}: {plan.get(key)}")


def _confirm(yes: bool, input_fn: Callable[[str], str]) -> bool:
    if yes:
        print("Confirming the plan because --yes was passed.")
        return True
    answer = input_fn("Confirm this plan and spend credits? [y/N] ")
    return answer.strip().lower() in {"y", "yes"}


async def _call(client: Client, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await client.call_tool(name, arguments)
    payload = tool_payload(result)
    if result.is_error is True:
        _print_error(payload)
        raise SystemExit(1)
    return payload


async def _poll_until(
    client: Client,
    job_id: str,
    *,
    mock_mode: bool,
    attempts: int = 12,
) -> dict[str, Any]:
    last: dict[str, Any] | None = None
    terminal = {"awaiting_confirmation", "awaiting_input", "succeeded", "failed", "cancelled"}
    for _ in range(attempts):
        last = await _call(client, "deepege_get_job", {"job_id": job_id})
        status = last.get("status")
        print(f"  status={status}")
        if status in terminal:
            return last
        wait_ms = last.get("poll_after_ms") or 0
        delay = wait_ms / 1000.0
        if mock_mode:
            delay = min(delay, MOCK_POLL_CAP_S)
        if delay > 0:
            await asyncio.sleep(delay)
    raise SystemExit(f"job {job_id} did not leave an in-progress state: {last}")


async def run_quickstart(
    args: argparse.Namespace,
    *,
    input_fn: Callable[[str], str] | None = None,
) -> int:
    prompt_fn = input_fn or input
    api_key = _api_key(args)
    mock_mode = args.api_base_url is None

    if mock_mode:
        from tests.mock_core.app import create_app
        from tests.mock_core.store import Store

        store = Store()
        transport = httpx.ASGITransport(app=create_app(store))
        http = httpx.AsyncClient(transport=transport, base_url="http://mock.local")
        api_client = OpenAPIClient("http://mock.local", http_client=http)
        settings = Settings(
            api_base_url="http://mock.local",
            mcp_host="127.0.0.1",
            mcp_port=8080,
            client_id=None,
            client_secret=None,
            api_key=api_key,
        )
        print("Using the in-process mock Open API.")
    else:
        http = httpx.AsyncClient(base_url=args.api_base_url)
        api_client = OpenAPIClient(args.api_base_url, http_client=http)
        settings = Settings(
            api_base_url=args.api_base_url,
            mcp_host="127.0.0.1",
            mcp_port=8080,
            client_id=None,
            client_secret=None,
            api_key=api_key,
        )
        print(f"Using live Open API at {args.api_base_url}")

    server = create_server(settings, api_client=api_client)
    async with Client(server) as client:
        created = await _call(
            client,
            "deepege_create_video_request",
            {
                "prompt": args.prompt,
                "aspect_ratio": args.aspect_ratio,
                "duration_seconds": args.duration_seconds,
            },
        )
        job_id = created["job_id"]
        print(f"Created job {job_id} (status={created.get('status')})")

        job = created
        if job.get("status") not in {
            "awaiting_confirmation",
            "awaiting_input",
            "succeeded",
            "failed",
            "cancelled",
        }:
            job = await _poll_until(client, job_id, mock_mode=mock_mode)

        if job["status"] == "awaiting_input":
            question = job.get("question") or {}
            print("The job is waiting for input. This quickstart stops here:")
            print(json.dumps(question, ensure_ascii=False, indent=2))
            return 2

        if job["status"] == "awaiting_confirmation":
            _print_plan(job)
            if not _confirm(args.yes, prompt_fn):
                print("Not confirmed. Exiting without spending.")
                return 0
            plan_id = (job.get("plan") or {})["plan_id"]
            job = await _call(
                client,
                "deepege_confirm_plan",
                {"job_id": job_id, "plan_id": plan_id, "action": "confirm"},
            )
            print(f"Confirmed plan {plan_id} (status={job.get('status')})")
            if job.get("status") not in {"succeeded", "failed", "cancelled", "awaiting_input"}:
                job = await _poll_until(client, job_id, mock_mode=mock_mode)

        if job["status"] == "awaiting_input":
            question = job.get("question") or {}
            print("The job is waiting for input after confirm. This quickstart stops here:")
            print(json.dumps(question, ensure_ascii=False, indent=2))
            return 2

        if job["status"] == "succeeded":
            result = job.get("result") or {}
            print("Job succeeded")
            print(f"  actual_credits: {result.get('actual_credits')}")
            print(f"  play_url: {result.get('play_url')}")
            print(f"  cover_url: {result.get('cover_url')}")
            return 0

        print(f"Job ended with status={job.get('status')}")
        if job.get("error"):
            print(json.dumps(job["error"], ensure_ascii=False, indent=2))
        return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(run_quickstart(args))
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
