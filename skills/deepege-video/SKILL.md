---
name: deepege-video
description: >
  Create and follow a Deepege video job through the MCP connector.
  Always ask a human before confirming a plan that spends credits.
---

English | [简体中文](SKILL.zh-CN.md)

# Deepege video

Use the Deepege MCP tools to turn a prompt into a video. Follow this loop. Do not invent extra tools, and do not confirm spending on your own.

## Tools

- `deepege_create_video_request` — start a job from a prompt (`aspect_ratio` and `duration_seconds` optional).
- `deepege_get_job` — read status; wait `poll_after_ms` before the next check. When playback links have expired, this tool renews them; pass `renew_result_links=true` to refresh early.
- `deepege_confirm_plan` — `confirm`, `revise` (comment required), or `reject` the current plan.
- `deepege_answer_question` — answer a question while the job is `awaiting_input`.
- `deepege_cancel_job` — cancel a job that has not finished, only when the human asks.

## Workflow

1. Call `deepege_create_video_request` with the human’s prompt and any preferences they gave.
2. Call `deepege_get_job` and wait `poll_after_ms` milliseconds before checking again. Keep polling through `planning` and `producing`.
3. When the status is `awaiting_confirmation`, show the plan and **stop**. Include at least `plan_id`, `title`, `estimated_credits`, `max_credits` (null means no cap, never 0), `charges_before_confirm` (credits already consumed, or null if unknown), and `credit_balance`. Ask the human whether to confirm, revise, or reject. **Never auto-confirm a plan that spends credits**, even if the estimate looks small or the human earlier said “just do it.” Wait for an explicit confirmation of this plan.
4. Only after the human agrees, call `deepege_confirm_plan` with the current `plan_id` and `action=confirm`. For a revision, send their comment. For a rejection, use `reject`.
5. When the status is `awaiting_input`, present the question (and options, if any), wait for the human’s answer, then call `deepege_answer_question`.
6. When the status is `succeeded`, deliver `play_url`, `cover_url`, and `actual_credits`. If a link has expired, call `deepege_get_job` again (it renews expired links automatically).
7. When the status is `cancelled`, say so and stop.

## Errors

- `quote_stale` — the plan changed or `plan_id` is no longer current. Fetch the job, show the new plan, and ask the human again. Do not reuse the old `plan_id`.
- `credits_insufficient` — show `recharge_url` from the error if present. Do not confirm again until the human says they have recharged (or they reject / cancel).
- `error.retryable` is true on a **failed** job — the same job cannot be recovered. Offer to start a **new** `deepege_create_video_request`. Do not retry the failed `job_id`.
- Rate limited (`429` / `rate_limited`) — wait `retry_after` seconds (from the tool error) before calling again. Do not tight-loop.
- Other retryable tool errors — back off; if `retry_after` is present, honor it.

## Spending rule

Confirm authorizes spend. Settlement happens during production. `charges_before_confirm` may already be non-zero. Treat any `confirm` as a spend decision that requires a human “yes” for the plan you just showed.
