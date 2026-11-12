English | [简体中文](README.zh-CN.md)

# Client adapters

Short setup guides and config templates for connecting an MCP client to the Deepege connector over Streamable HTTP. Start the connector first (see the repository README), then point the client at `http://127.0.0.1:8081/mcp` for local use, or at your public HTTPS `/mcp` URL for a hosted or remote client.

Do not put real API keys in committed files. Export `DEEPEGE_API_KEY` (or the equivalent the client names) in your environment. Test tokens such as `sk-test-alice` are for the in-repo mock only.

The four **priority-verified (beta)** clients were checked against current public docs and are the first-wave targets. Other listed clients are also documented from public official docs. Formats that could not be confirmed are marked **unverified**.

## Index

| Client | Status | Location |
| --- | --- | --- |
| [WorkBuddy](workbuddy/README.md) | priority-verified (beta) | [`workbuddy/`](workbuddy/) |
| [ChatGPT (incl. Codex)](chatgpt/README.md) | priority-verified (beta) | [`chatgpt/`](chatgpt/) |
| [DeepSeek Harness (dsh)](dsh/README.md) | priority-verified (beta) | [`dsh/`](dsh/) |
| [Grok Bot](grok-bot/README.md) | priority-verified (beta) | [`grok-bot/`](grok-bot/) |
| [Claude Code](claude-code/README.md) | verified | [`claude-code/`](claude-code/) |
| [Claude Desktop](claude-desktop/README.md) | verified (stdio / mcp-remote) | [`claude-desktop/`](claude-desktop/) |
| [Other clients (generic)](generic/README.md) | guidance | [`generic/`](generic/) |

## Generic remote MCP

If your client is not listed, use the [generic remote MCP](generic/README.md) approach: Streamable HTTP to `/mcp` with an `Authorization: Bearer <api_key>` header. Clients that only speak stdio can use the `mcp-remote` bridge shown there.
