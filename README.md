# Deepege connector

Deepege 连接器是面向 MCP 客户端的开源服务（Python，官方 MCP Python SDK 2.x，Streamable HTTP）。它通过版本化的 Deepege Open API（`/open/v1`）调用主服务，提供一句话出片等能力。本仓库目前交付到工作包 W2：共享类型、OpenAPI 契约、内存版 mock 主服务，以及可对 mock（或真实 Open API）运行的 MCP 服务。

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
| `sk-test-limited` | 任意请求返回 429 `rate_limited`，并带 `Retry-After` |
| `atok_alice` | 用户侧 OAuth access token，用于 introspection / token-exchange |

服务凭证（仅 `/oauth/introspect` 与 `/oauth/token`）：HTTP Basic `test-mcp-client` / `test-mcp-secret`。

走通「创建 → 轮询到待确认 → 确认 → 轮询到成功」（mock 按契约返回 `poll_after_ms`，但为了便于本地联调，两次查询或约 200ms 后就会推进状态，不必真的等待 3–15 秒）：

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

创建时的 `prompt` 里可加入仅 mock 识别的标记（不属于公开契约）：`[ask]` 会在确认后进入 `awaiting_input`，`[fail]` 或 `[unrecoverable]` 会失败且 `retryable=true`（表示可新建任务，同一 job 不可恢复），`[quote-stale]` 使确认返回 `quote_stale`，`[planning-charge]` 让方案带上确认前已消耗积分，`[actual-round]` 让实扣积分与预计不同，`[no-cover]` 与 `[unknown-duration]` 让封面或时长为 null，`[no-max]` 让 `max_credits` 为 null（无上限）。停用的合作方 key 使用 `sk-test-disabled`，返回 401 `unauthorized`。

## 启动 MCP 服务（对接 mock）

先在 8080 端口启动 mock，再另开一个终端启动连接器（默认监听 `127.0.0.1:8080`，因此本地联调请改端口，避免和 mock 冲突）：

```bash
export DEEPEGE_API_BASE_URL=http://127.0.0.1:8080
export DEEPEGE_MCP_HOST=127.0.0.1
export DEEPEGE_MCP_PORT=8081
# 可选：当 MCP 请求没有 Authorization 头时使用的默认用户 API key
export DEEPEGE_API_KEY=sk-test-alice

deepege-connector
# 或：python -m deepege_connector
```

服务以 Streamable HTTP 提供 MCP，路径为 `/mcp`，无会话粘滞（`stateless_http=true`）。连接器不会在日志里输出 API key 或带签名的播放 / 封面地址。

### 客户端如何连接

MCP 客户端应使用 Streamable HTTP，指向 `http://127.0.0.1:8081/mcp`，并在请求头中带上用户 API key：

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

不同客户端的配置字段可能略有差异，但传输均为 Streamable HTTP，URL 为 `/mcp`，鉴权为 `Authorization: Bearer <api_key>`。若客户端暂时无法自定义请求头，可为进程设置 `DEEPEGE_API_KEY`，该默认值仅在请求未带 Authorization 时使用。

这是自建（self-hosted）模式：连接器把用户 API key 原样作为 Bearer 转发给 `/open/v1`。官方托管模式的 OAuth 缝预留为 TODO，尚未实现：主服务将签发绑定到 MCP 资源的访问令牌（RFC 8707），连接器通过 introspection（RFC 7662）校验后，再用 token-exchange（RFC 8693）换成短时下游令牌调用 Open API，而不会把面向用户的 OAuth 访问令牌直接透传。

### 工具

连接器暴露五个工具。需要幂等键的调用会在调用方未提供 `idempotency_key` 时自动生成（符合 Open API 的 `Idempotency-Key` 规则）。Open API 的错误信封（`code` / `retryable` / `refund` 等）会映射为 MCP tool error；`429` 的 `Retry-After`（秒）会出现在错误载荷的 `retry_after` 字段中。

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `deepege_create_video_request` | `prompt`（必填）；`aspect_ratio`、`duration_seconds`、`idempotency_key`（可选） | 用一句话创建视频任务，返回 job（含 `job_id`、`poll_after_ms`） |
| `deepege_get_job` | `job_id`（必填）；`renew_result_links`（可选，默认 false） | 查询任务状态。进行中请按 `poll_after_ms` 等待后再查 |
| `deepege_confirm_plan` | `job_id`、`plan_id`、`action`（`confirm` / `revise` / `reject`）；`comment`（修订时必填）；`idempotency_key`（可选） | 确认、修订或拒绝当前方案。非当前 `plan_id` 会返回 `quote_stale` |
| `deepege_answer_question` | `job_id`、`question_id`；`option_id` 或 `text`；`idempotency_key`（可选） | 回答 `awaiting_input` 状态下的问题 |
| `deepege_cancel_job` | `job_id` | 取消尚未结束的任务 |

成片播放地址过期后，没有单独的第六个「续签链接」工具。连接器把续签放在 `deepege_get_job` 里：当任务已成功且 `play_url` 或 `cover_url` 过期时自动调用 `POST /open/v1/jobs/{job_id}/result-links`；也可以传 `renew_result_links=true` 提前换新链接。这样代理在轮询时不必再选另一个工具，也与契约「到期后再次 GET job 或调用 result-links」的用法一致。

失败任务本身不可恢复。若 `error.retryable` 为 true，应新建一个 `deepege_create_video_request`，而不是重试同一个 job。

## 配置

运行时所有地址与凭证都从环境变量注入，仓库里不会写入真实地址或密钥：

- `DEEPEGE_API_BASE_URL`：主服务 Open API 的公开 origin（必填）
- `DEEPEGE_MCP_HOST` / `DEEPEGE_MCP_PORT`：MCP 监听地址（默认 `127.0.0.1:8080`）
- `DEEPEGE_API_KEY`：自建实例的默认用户 API key（请求头优先）
- `DEEPEGE_CLIENT_ID` / `DEEPEGE_CLIENT_SECRET`：官方托管实例的服务凭证（预留给托管模式的 introspection / token-exchange，当前未使用）

## Docker

```bash
docker build -t deepege-connector .
docker run --rm -p 8081:8080 \
  -e DEEPEGE_API_BASE_URL=http://host.docker.internal:8080 \
  -e DEEPEGE_API_KEY=sk-test-alice \
  deepege-connector
```

镜像内 MCP 默认监听 `0.0.0.0:8080`。`DEEPEGE_API_BASE_URL` 需指向可从容器访问的 Open API origin。

## 许可证

[MIT](LICENSE)，版权所有 Deepege。
