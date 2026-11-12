English | [简体中文](README.zh-CN.md)

# Deepege connector

The Deepege connector is an open-source service for MCP clients (Python, official MCP Python SDK 2.x, Streamable HTTP). It talks to the main service through the versioned Deepege Open API (`/open/v1`) and provides capabilities such as creating a video from a single prompt. This repository currently delivers work package W2: shared types, the OpenAPI contract, an in-memory mock of the main service, and an MCP server that can run against the mock (or a real Open API). It also includes MCP client setup guides, a usage skill, and a mock quickstart.

## Local development

Python 3.11+ is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Validate the contract, run the tests, and check code style:

```bash
python -c "from openapi_spec_validator import validate; import yaml; validate(yaml.safe_load(open('openapi/open-v1.yaml')))"
pytest
ruff check .
ruff format --check .
```

The private keyword scan is skipped when no list is configured:

```bash
python scripts/private_keyword_scan.py
# 或
PRIVATE_KEYWORD_LIST_PATH=/path/to/keywords.txt python scripts/private_keyword_scan.py
```

## Start the mock main service

```bash
python -m tests.mock_core --host 127.0.0.1 --port 8080
```

You can also use the environment variables `DEEPEGE_MOCK_HOST` and `DEEPEGE_MOCK_PORT`. The service keeps state in memory only; it is cleared when the process exits. The following tokens are for local development and are not real secrets.

| Bearer token | Description |
| --- | --- |
| `sk-test-alice` | Balance 1000, full scopes |
| `sk-test-bob` | Another tenant, used to verify that cross-tenant access returns `not_found` |
| `sk-test-broke` | Balance 10; confirming a plan returns `credits_insufficient` |
| `sk-test-readonly` | Read-only scopes; creating a job returns `insufficient_scope` |
| `sk-test-disabled` | A disabled key; every request returns 401 `unauthorized` |
| `sk-test-limited` | Every request returns 429 `rate_limited` with a `Retry-After` header |
| `atok_alice` | A user-facing OAuth access token, used for introspection / token-exchange |

Service credentials (only for `/oauth/introspect` and `/oauth/token`): HTTP Basic `test-mcp-client` / `test-mcp-secret`.

Walk through “create → poll until awaiting confirmation → confirm → poll until succeeded” (the mock returns `poll_after_ms` as specified by the contract, but for local development it advances after two GETs or about 200ms, so you do not have to wait 3–15 seconds):

```bash
BASE=http://127.0.0.1:8080
AUTH='Authorization: Bearer sk-test-alice'

JOB=$(curl -sS -X POST "$BASE/open/v1/video-requests" \
  -H "$AUTH" -H "Idempotency-Key: demo-1" -H "Content-Type: application/json" \
  -d '{"prompt":"A sunrise over the sea","preferences":{"aspect_ratio":"16:9","duration_seconds":15}}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')

# 轮询到 awaiting_confirmation
for i in 1 2 3 4; do
  BODY=$(curl -sS "$BASE/open/v1/jobs/$JOB" -H "$AUTH")
  echo "$BODY"
  echo "$BODY" | python -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin)["status"]=="awaiting_confirmation" else 1)' && break
done

PLAN=$(echo "$BODY" | python -c 'import json,sys; print(json.load(sys.stdin)["plan"]["plan_id"])')

curl -sS -X POST "$BASE/open/v1/video-requests/$JOB/plan-decisions" \
  -H "$AUTH" -H "Idempotency-Key: demo-1-confirm" -H "Content-Type: application/json" \
  -d "{\"plan_id\":\"$PLAN\",\"action\":\"confirm\"}"

# 轮询到 succeeded
for i in 1 2 3 4; do
  BODY=$(curl -sS "$BASE/open/v1/jobs/$JOB" -H "$AUTH")
  echo "$BODY"
  echo "$BODY" | python -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin)["status"]=="succeeded" else 1)' && break
done
```

The `prompt` used at creation may include flags that only the mock recognizes (they are not part of the public contract): `[ask]` enters `awaiting_input` after confirm; `[fail]` or `[unrecoverable]` fails with `retryable=true` (meaning you may start a new job; the same job is not recoverable); `[quote-stale]` makes confirm return `quote_stale`; `[planning-charge]` puts credits already consumed before confirm on the plan; `[actual-round]` makes the settled credits differ from the estimate; `[no-cover]` and `[unknown-duration]` leave the cover or duration null; `[no-max]` leaves `max_credits` null (no cap). A disabled partner key is `sk-test-disabled` and returns 401 `unauthorized`.

## Start the MCP server (against the mock)

Start the mock on port 8080 first, then start the connector in another terminal (it listens on `127.0.0.1:8080` by default, so change the port for local use to avoid colliding with the mock):

```bash
export DEEPEGE_API_BASE_URL=http://127.0.0.1:8080
export DEEPEGE_MCP_HOST=127.0.0.1
export DEEPEGE_MCP_PORT=8081
# 可选：当 MCP 请求没有 Authorization 头时使用的默认用户 API key
export DEEPEGE_API_KEY=sk-test-alice

deepege-connector
# 或：python -m deepege_connector
```

The server serves MCP over Streamable HTTP at `/mcp`, with no session affinity (`stateless_http=true`). The connector never writes API keys or signed playback / cover URLs to its logs.

### How a client connects

An MCP client should use Streamable HTTP, point at `http://127.0.0.1:8081/mcp`, and send the user API key in the request headers:

```json
{
  "mcpServers": {
    "deepege": {
      "url": "http://127.0.0.1:8081/mcp",
      "headers": {
        "Authorization": "Bearer sk-test-alice"
      }
    }
  }
}
```

Configuration field names may differ slightly across clients, but the transport is always Streamable HTTP, the URL is `/mcp`, and authentication is `Authorization: Bearer <api_key>`. If the client cannot set custom headers yet, set `DEEPEGE_API_KEY` on the process; that default is used only when the request has no Authorization header.

This is self-hosted mode: the connector forwards the user API key unchanged as a Bearer token to `/open/v1`. The official hosted-mode OAuth seam is reserved as a TODO and is not implemented: the main service will issue access tokens bound to the MCP resource (RFC 8707); the connector will introspect them (RFC 7662) and then use token-exchange (RFC 8693) for a short-lived downstream token to call the Open API, and will not pass the user-facing OAuth access token through.


Per-client setup templates and notes (WorkBuddy, ChatGPT including Codex, dsh, Grok Bot, Claude, and a generic Streamable HTTP / `mcp-remote` fallback) are in [`clients/`](clients/README.md). Formats that could not be confirmed against official docs are marked unverified.

A recommended agent workflow — create, poll with `poll_after_ms`, show the plan, and ask a human before confirming any spend — is in [`skills/deepege-video/SKILL.md`](skills/deepege-video/SKILL.md).

To walk through that loop against the in-process mock (no need to start the mock or MCP processes first):

```bash
python examples/quickstart/run.py --yes
```

`--yes` confirms the plan without prompting and is for this demo and CI only. Omit it to review the plan interactively. To use a running Open API instead, pass `--api-base-url http://127.0.0.1:8080` and set `DEEPEGE_API_KEY`.

### Tools

The connector exposes five tools. Calls that require an idempotency key generate one automatically when the caller omits `idempotency_key` (matching the Open API `Idempotency-Key` rules). The Open API error envelope (`code` / `retryable` / `refund`, and so on) is mapped to an MCP tool error; the `Retry-After` value from a `429` (in seconds) appears as `retry_after` in the error payload.

| Tool | Arguments | Description |
| --- | --- | --- |
| `deepege_create_video_request` | `prompt` (required); `aspect_ratio`, `duration_seconds`, `idempotency_key` (optional) | Create a video job from a single prompt. Returns the job, including `job_id` and `poll_after_ms`. |
| `deepege_get_job` | `job_id` (required); `renew_result_links` (optional, default false) | Fetch the job status. While the job is in progress, wait `poll_after_ms` before checking again. |
| `deepege_confirm_plan` | `job_id`, `plan_id`, `action` (`confirm` / `revise` / `reject`); `comment` (required when revising); `idempotency_key` (optional) | Confirm, revise, or reject the current plan. A non-current `plan_id` returns `quote_stale`. |
| `deepege_answer_question` | `job_id`, `question_id`; `option_id` or `text`; `idempotency_key` (optional) | Answer a question while the job is `awaiting_input`. |
| `deepege_cancel_job` | `job_id` | Cancel a job that has not finished. |

There is no separate sixth “renew links” tool after a playback URL expires. The connector renews links inside `deepege_get_job`: when the job has succeeded and `play_url` or `cover_url` has expired, it automatically calls `POST /open/v1/jobs/{job_id}/result-links`; you can also pass `renew_result_links=true` to refresh the links early. That way an agent polling the job does not have to pick another tool, and it matches the contract’s “GET the job again or call result-links after expiry” usage.

A failed job itself is not recoverable. If `error.retryable` is true, start a new `deepege_create_video_request` rather than retrying the same job.

## Configuration

All addresses and credentials are injected from environment variables at runtime; the repository does not contain real addresses or secrets:

- `DEEPEGE_API_BASE_URL`: public origin of the main service Open API (required)
- `DEEPEGE_MCP_HOST` / `DEEPEGE_MCP_PORT`: MCP listen address (default `127.0.0.1:8080`)
- `DEEPEGE_API_KEY`: default user API key for a self-hosted instance (the request header takes precedence)
- `DEEPEGE_CLIENT_ID` / `DEEPEGE_CLIENT_SECRET`: service credentials for the official hosted instance (reserved for hosted-mode introspection / token-exchange; currently unused)

## Docker

```bash
docker build -t deepege-connector .
docker run --rm -p 8081:8080 \
  -e DEEPEGE_API_BASE_URL=http://host.docker.internal:8080 \
  -e DEEPEGE_API_KEY=sk-test-alice \
  deepege-connector
```

Inside the image, the MCP server listens on `0.0.0.0:8080` by default. `DEEPEGE_API_BASE_URL` must point at an Open API origin reachable from the container.

## License

[MIT](LICENSE), copyright Deepege.
