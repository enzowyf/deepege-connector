[English](README.md) | 简体中文

# Claude Code

状态：**已核实**（Anthropic 官方文档）

把连接器添加为 Streamable HTTP 服务器。官方文档使用 `--transport http`，JSON 中为 `"type": "http"`（别名 `streamable-http`）。

## 命令行（已核实）

```bash
export DEEPEGE_API_KEY=sk-test-alice
claude mcp add --transport http deepege http://127.0.0.1:8081/mcp \
  --header "Authorization: Bearer $DEEPEGE_API_KEY"
```

## 项目或用户 JSON（已核实）

将 [`mcp.json`](mcp.json) 中的模板合并进 `.mcp.json`（项目级）或 `~/.claude.json`（用户级）。这些文件中的 `${DEEPEGE_API_KEY}` 展开已有文档说明。

```json
{
  "mcpServers": {
    "deepege": {
      "type": "http",
      "url": "http://127.0.0.1:8081/mcp",
      "headers": {
        "Authorization": "Bearer ${DEEPEGE_API_KEY}"
      }
    }
  }
}
```

资料来源：[Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp)。
