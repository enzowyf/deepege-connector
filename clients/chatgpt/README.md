English | [简体中文](README.zh-CN.md)

# ChatGPT (including Codex)

Status: **priority-verified (beta)**

ChatGPT and Codex share MCP setup in current public docs. ChatGPT web uses remote MCP through plugins. The ChatGPT desktop app, Codex CLI, and IDE extension share one local configuration for the same Codex host. ChatGPT web does **not** read local Codex configuration files.

Source: [Model Context Protocol | ChatGPT Learn](https://learn.chatgpt.com/docs/extend/mcp).

## ChatGPT web (plugins)

1. Open **Plugins**.
2. Select the plus button, then **Add custom MCP server**.
3. Enter a name (for example `Deepege`) and, optionally, a description.
4. Under **Connection**, enter the connector’s **public HTTPS** MCP URL, ending in `/mcp`. Localhost is not reachable from ChatGPT web. You can also choose a Secure MCP Tunnel if your workspace provides one.
5. Configure authentication for the server.
6. Review the risk warning, create the plugin, then install it and use `@` to attach it in a conversation.

Official docs describe authentication options for custom MCP servers as **OAuth**, **no authentication**, and **mixed** (OAuth or no authentication). A static `Authorization: Bearer` header field in the web plugin form is **not documented** there and is **unverified**. For a self-hosted API key against ChatGPT web, prefer a documented path (hosted OAuth when available) rather than inventing a header field.

Workspace plan and admin permissions apply. See also [Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt).

## ChatGPT desktop, Codex CLI, and IDE (shared config)

These surfaces share MCP configuration. Official Streamable HTTP features include bearer token authentication and OAuth.

### Desktop or IDE UI (verified)

1. Open **Settings** (desktop) or the gear menu (IDE extension), then **MCP servers**.
2. Select **Add server**.
3. Enter a name, choose **Streamable HTTP**, and provide the server URL (local: `http://127.0.0.1:8081/mcp`).
4. Save, then restart as the UI prompts.

The list shows which servers need OAuth; choose **Authenticate** when sign-in is required. Type `/mcp` in the composer to see connected servers.

Where to enter a static bearer token in that Add-server form is **not shown** in the official UI steps. Bearer tokens are documented for the shared `config.toml` (below). If the form has no token field, use that file, or use **Authenticate** for OAuth.

### `config.toml` (verified)

The ChatGPT desktop app, Codex CLI, and IDE extension read `~/.codex/config.toml`, or a project-scoped `.codex/config.toml` on a trusted project. Merge the snippet in [`config.toml`](config.toml) into your file. Do not put the API key in the file; export it in the environment. An inline `bearer_token` field is rejected; use `bearer_token_env_var`.

```toml
[mcp_servers.deepege]
url = "http://127.0.0.1:8081/mcp"
bearer_token_env_var = "DEEPEGE_API_KEY"
```

```bash
export DEEPEGE_API_KEY=sk-test-alice
```

You can also run `codex mcp add` / `codex mcp list` / `codex mcp login`. For current flags, use `codex mcp --help`. The exact `add` flags for a Streamable HTTP URL plus bearer env var are not copied here from a single command example on the MCP page; the `config.toml` fields above are the verified form.

For OAuth instead of an API key, omit `bearer_token_env_var` and run `codex mcp login deepege` (or **Authenticate** in the UI) after the hosted connector is available.
