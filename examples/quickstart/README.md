English | [简体中文](README.zh-CN.md)

# Quickstart

Runs a create → poll → show plan → confirm → deliver loop through the MCP tools, against the in-process mock by default.

```bash
python examples/quickstart/run.py --yes
```

`--yes` confirms the plan without asking. That flag is for this demo and CI only. The [usage skill](../../skills/deepege-video/SKILL.md) requires a human to approve spend; do not auto-confirm in an agent.

Without `--yes`, the script prints `estimated_credits`, `max_credits`, `charges_before_confirm`, and `credit_balance`, then waits for `y` / `yes`.

To use a running Open API instead of the mock (start the mock or a real service first):

```bash
export DEEPEGE_API_KEY=sk-test-alice
python examples/quickstart/run.py --yes --api-base-url http://127.0.0.1:8080
```

The in-process mock advances after two GETs or about 200ms, so the script caps poll waits at 250ms in mock mode. A live `--api-base-url` honors `poll_after_ms` as returned.
