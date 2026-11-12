English | [简体中文](README.zh-CN.md)

# Claude Desktop

Status: **verified** (stdio / mcp-remote)

Claude Desktop’s official remote-connector UI is typically OAuth and does not document a static bearer field. For a self-hosted API key, bridge Streamable HTTP through `mcp-remote` in `claude_desktop_config.json`.

## Config paths (verified)

| Platform | Path |
| --- | --- |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Merge the `mcpServers.deepege` entry from [`claude_desktop_config.json`](claude_desktop_config.json) into your existing file. Replace `YOUR_DEEPEGE_API_KEY` with a local secret (for the mock, `sk-test-alice`) and do not commit that file.

```json
{
  "mcpServers": {
    "deepege": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://127.0.0.1:8081/mcp",
        "--header",
        "Authorization:${AUTH_HEADER}"
      ],
      "env": {
        "AUTH_HEADER": "Bearer YOUR_DEEPEGE_API_KEY"
      }
    }
  }
}
```

Use `--header Authorization:${AUTH_HEADER}` with **no space after the colon**, and keep the `Bearer …` value in `env`. That avoids a known `mcp-remote` argument-escaping issue. Restart Claude Desktop after saving.

When hosted OAuth is available, you can instead add a remote connector in the official UI and complete sign-in there.

Sources: [Connect to remote MCP servers from Claude Desktop](https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp) and [geelen/mcp-remote](https://github.com/geelen/mcp-remote).
