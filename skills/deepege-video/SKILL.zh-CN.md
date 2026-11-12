---
name: deepege-video
description: >
  通过 Deepege MCP 连接器创建并跟进视频任务。
  在确认会消耗积分的方案之前，必须询问人工。
---

[English](SKILL.md) | 简体中文

# Deepege 视频

使用 Deepege MCP 工具，把一句话做成视频。请按下面的循环执行。不要发明额外工具，也不要自行确认消耗积分的方案。

## 工具

- `deepege_create_video_request` — 用提示词创建任务（`aspect_ratio`、`duration_seconds` 可选）。
- `deepege_get_job` — 查询状态；下次查询前等待 `poll_after_ms`。播放链接过期时，该工具会续签；传入 `renew_result_links=true` 可提前换新。
- `deepege_confirm_plan` — 对当前方案执行 `confirm`、`revise`（必须带 comment）或 `reject`。
- `deepege_answer_question` — 在任务处于 `awaiting_input` 时回答问题。
- `deepege_cancel_job` — 仅在人工要求时，取消尚未结束的任务。

## 流程

1. 用人工的提示词和他们给出的偏好调用 `deepege_create_video_request`。
2. 调用 `deepege_get_job`，并在下次查询前等待 `poll_after_ms` 毫秒。在 `planning` 和 `producing` 期间持续轮询。
3. 当状态为 `awaiting_confirmation` 时，展示方案并**停下**。至少说明 `plan_id`、`title`、`estimated_credits`、`max_credits`（null 表示不封顶，不会用 0 表示不封顶）、`charges_before_confirm`（确认前已消耗的积分；null 表示未知）和 `credit_balance`。询问人工是确认、修订还是拒绝。**即使估算很小，或人工先前说过「直接做」，也绝不能自动确认会消耗积分的方案。** 必须等到人工明确确认你刚展示的这一份方案。
4. 只有在人工同意后，才用当前 `plan_id` 和 `action=confirm` 调用 `deepege_confirm_plan`。若要修订，附上他们的 comment；若要拒绝，使用 `reject`。
5. 当状态为 `awaiting_input` 时，展示问题（如有选项一并列出），等待人工回答，再调用 `deepege_answer_question`。
6. 当状态为 `succeeded` 时，交付 `play_url`、`cover_url` 和 `actual_credits`。若链接已过期，再次调用 `deepege_get_job`（过期链接会自动续签）。
7. 当状态为 `cancelled` 时，告知结果并结束。

## 错误处理

- `quote_stale` — 方案已变更，或 `plan_id` 已不是当前方案。重新获取任务，展示新方案，并再次询问人工。不要沿用旧的 `plan_id`。
- `credits_insufficient` — 如错误中带有 `recharge_url`，请展示它。在人工表示已充值（或改为拒绝 / 取消）之前，不要再次确认。
- 失败任务上的 `error.retryable` 为 true — 同一任务不可恢复。应提议新建一个 `deepege_create_video_request`，不要重试失败的 `job_id`。
- 触发限流（`429` / `rate_limited`）— 按工具错误中的 `retry_after` 秒等待后再调用，不要密集团环。
- 其他可重试的工具错误 — 做退避；若存在 `retry_after`，必须遵守。

## 消耗规则

确认即授权消耗。结算发生在生产阶段。`charges_before_confirm` 可能已经不是 0。任何一次 `confirm` 都视为消耗决策，必须针对你刚刚展示的方案获得人工的明确同意。
