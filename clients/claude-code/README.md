English | [简体中文](README.zh-CN.md)

# Claude Code

Status: **verified** (official Anthropic docs)

Add the connector as a Streamable HTTP server. Official docs use `--transport http` and JSON `"type": "http"` (alias `streamable-http`).

## CLI (verified)

```bash
export DEEPEGE_API_KEY=sk-test-alice
claude mcp add --transport http deepege http://127.0.0.1:8081/mcp \
  --header "Authorization: Bearer $DEEPEGE_API_KEY"
```

## Project or user JSON (verified)

Merge the template in [`mcp.json`](mcp.json) into `.mcp.json` (project) or `~/.claude.json` (user). `${DEEPEGE_API_KEY}` expansion is documented for these files.

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

Source: [Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp).
