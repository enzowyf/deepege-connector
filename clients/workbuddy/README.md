English | [简体中文](README.zh-CN.md)

# WorkBuddy

Status: **priority-verified (beta)**

## Official file locations (verified)

WorkBuddy’s official MCP guide documents two config levels:

| Level | Path |
| --- | --- |
| User | `~/.workbuddy/mcp.json` |
| Project | `<project>/.workbuddy/mcp.json` |

You can also add a server from the UI: sidebar **Plugins** → **MCP servers** → **Configure MCP**. After saving, a green status light means the server connected.

Official example in that guide is a local **stdio** server (`command` / `args` / `env`). The official guide does not include a Streamable HTTP JSON example.

## Remote Streamable HTTP template (unverified against the official guide)

The template in [`mcp.json`](mcp.json) uses `type`, `url`, and `headers`. That shape appears in third-party WorkBuddy connector write-ups, but it is **unverified** against the official MCP guide. Prefer the UI if your build exposes Streamable HTTP or header fields. If you paste JSON, merge the `deepege` entry into any existing `mcpServers` map rather than replacing the whole file.

```json
{
  "mcpServers": {
    "deepege": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8081/mcp",
      "headers": {
        "Authorization": "Bearer ${DEEPEGE_API_KEY}"
      }
    }
  }
}
```

Export `DEEPEGE_API_KEY` first (for local mock use, `sk-test-alice`). Whether `${DEEPEGE_API_KEY}` is expanded by WorkBuddy is also **unverified**; if the header is sent literally, paste a local secret in the UI or a private file that you do not commit.

Sources: [WorkBuddy MCP guide](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide).
