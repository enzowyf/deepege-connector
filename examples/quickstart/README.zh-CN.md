[English](README.md) | 简体中文

# 快速试用

默认对进程内 mock 走一遍「创建 → 轮询 → 展示方案 → 确认 → 交付」，调用的是 MCP 工具。

```bash
python examples/quickstart/run.py --yes
```

`--yes` 会在不问的情况下确认方案。该参数仅用于本演示和 CI。[用法技能](../../skills/deepege-video/SKILL.zh-CN.md)要求由人工批准消耗；代理不要自动确认。

若不加 `--yes`，脚本会打印 `estimated_credits`、`max_credits`、`charges_before_confirm` 和 `credit_balance`，然后等待输入 `y` / `yes`。

若要对已启动的 Open API 而不是 mock 运行（请先启动 mock 或真实服务）：

```bash
export DEEPEGE_API_KEY=sk-test-alice
python examples/quickstart/run.py --yes --api-base-url http://127.0.0.1:8080
```

进程内 mock 会在两次 GET 或约 200ms 后推进状态，因此脚本在 mock 模式下把轮询等待上限设为 250ms。使用 `--api-base-url` 连接真实服务时，会按返回的 `poll_after_ms` 等待。
