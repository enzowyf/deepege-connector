# Deepege connector

Deepege 连接器是面向 MCP 客户端的开源服务（Python，官方 MCP Python SDK，Streamable HTTP）。它通过版本化的 Deepege Open API（`/open/v1`）调用主服务，提供一句话出片等能力。本仓库目前交付的是工作包 W0：共享类型、OpenAPI 契约 v0，以及一个内存版 mock 主服务，供连接器在主服务就绪前联调。MCP tool 将在后续工作包实现。

## 本地开发

需要 Python 3.11+。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

校验契约、运行测试、检查代码风格：

```bash
python -c "from openapi_spec_validator import validate; import yaml; validate(yaml.safe_load(open('openapi/open-v1.yaml')))"
pytest
ruff check .
ruff format --check .
```

私有关键词扫描在未配置清单时会跳过：

```bash
python scripts/private_keyword_scan.py
# 或
PRIVATE_KEYWORD_LIST_PATH=/path/to/keywords.txt python scripts/private_keyword_scan.py
```

## 启动 mock 主服务

```bash
python -m tests.mock_core --host 127.0.0.1 --port 8080
```

也可用环境变量 `DEEPEGE_MOCK_HOST`、`DEEPEGE_MOCK_PORT`。服务只在内存中保存状态，进程退出即清空。以下为本地联调用的测试令牌，不是真实密钥。

| Bearer 令牌 | 说明 |
| --- | --- |
| `sk-test-alice` | 余额 1000，完整 scope |
| `sk-test-bob` | 另一租户，用来验证跨租户返回 `not_found` |
| `sk-test-broke` | 余额 10，确认方案时返回 `credits_insufficient` |
| `sk-test-readonly` | 只有读权限，创建任务返回 `insufficient_scope` |
| `sk-test-disabled` | 已停用的 key，任何请求返回 401 `unauthorized` |
| `atok_alice` | 用户侧 OAuth access token，用于 introspection / token-exchange |

服务凭证（仅 `/oauth/introspect` 与 `/oauth/token`）：HTTP Basic `test-mcp-client` / `test-mcp-secret`。

走通「创建 → 轮询到待确认 → 确认 → 轮询到成功」（mock 按契约返回 `poll_after_ms`，但为了便于本地联调，两次查询或约 200ms 后就会推进状态，不必真的等待 3–15 秒）：

```bash
BASE=http://127.0.0.1:8080
AUTH='Authorization: Bearer sk-test-alice'

JOB=$(curl -sS -X POST "$BASE/open/v1/video-requests"   -H "$AUTH" -H "Idempotency-Key: demo-1" -H "Content-Type: application/json"   -d '{"prompt":"A sunrise over the sea","preferences":{"aspect_ratio":"16:9","duration_seconds":15}}'   | python -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')

# 轮询到 awaiting_confirmation
for i in 1 2 3 4; do
  BODY=$(curl -sS "$BASE/open/v1/jobs/$JOB" -H "$AUTH")
  echo "$BODY"
  echo "$BODY" | python -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin)["status"]=="awaiting_confirmation" else 1)' && break
done

PLAN=$(echo "$BODY" | python -c 'import json,sys; print(json.load(sys.stdin)["plan"]["plan_id"])')

curl -sS -X POST "$BASE/open/v1/video-requests/$JOB/plan-decisions"   -H "$AUTH" -H "Idempotency-Key: demo-1-confirm" -H "Content-Type: application/json"   -d "{"plan_id":"$PLAN","action":"confirm"}"

# 轮询到 succeeded
for i in 1 2 3 4; do
  BODY=$(curl -sS "$BASE/open/v1/jobs/$JOB" -H "$AUTH")
  echo "$BODY"
  echo "$BODY" | python -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin)["status"]=="succeeded" else 1)' && break
done
```

创建时的 `prompt` 里可加入仅 mock 识别的标记（不属于公开契约）：`[ask]` 会在确认后进入 `awaiting_input`，`[fail]` 或 `[unrecoverable]` 会失败且 `retryable=true`（表示可新建任务，同一 job 不可恢复），`[quote-stale]` 使确认返回 `quote_stale`，`[planning-charge]` 让方案带上确认前已消耗积分，`[actual-round]` 让实扣积分与预计不同，`[no-cover]` 与 `[unknown-duration]` 让封面或时长为 null，`[no-max]` 让 `max_credits` 为 null（无上限）。停用的合作方 key 使用 `sk-test-disabled`，返回 401 `unauthorized`。

## 配置（后续 MCP 服务）

MCP 服务尚未实现。将来运行时所有地址与凭证都从环境变量注入，仓库里不会写入真实地址或密钥：

- `DEEPEGE_API_BASE_URL`：主服务 Open API 的公开 origin
- `DEEPEGE_MCP_HOST` / `DEEPEGE_MCP_PORT`：MCP 监听地址
- `DEEPEGE_CLIENT_ID` / `DEEPEGE_CLIENT_SECRET`：官方托管实例的服务凭证（自建实例不使用，改为透传用户 API key）

## 许可证

[MIT](LICENSE)，版权所有 Deepege。
