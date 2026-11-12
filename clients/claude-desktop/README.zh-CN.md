[English](README.md) | 简体中文

# Claude Desktop

状态：**已核实**（stdio / mcp-remote）

Claude Desktop 官方的远程连接器界面通常走 OAuth，没有记录静态 Bearer 字段。若使用自建 API key，请在 `claude_desktop_config.json` 里通过 `mcp-remote` 把 Streamable HTTP 桥接为 stdio。

## 配置路径（已核实）

| 平台 | 路径 |
| --- | --- |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

把 [`claude_desktop_config.json`](claude_desktop_config.json) 中的 `mcpServers.deepege` 条目合并进已有文件。将 `YOUR_DEEPEGE_API_KEY` 换成本地密钥（mock 可用 `sk-test-alice`），不要提交含密钥的文件。

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

请使用 `--header Authorization:${AUTH_HEADER}`，**冒号后不要加空格**，并把 `Bearer …` 的值放在 `env` 中。这样可以避开已知的 `mcp-remote` 参数转义问题。保存后重启 Claude Desktop。

当托管 OAuth 可用时，也可以在官方界面添加远程连接器并完成登录。

资料来源：[Connect to remote MCP servers from Claude Desktop](https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp) 与 [geelen/mcp-remote](https://github.com/geelen/mcp-remote)。
