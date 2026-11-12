English | [简体中文](README.zh-CN.md)

# Grok Bot

Status: **priority-verified (beta)**

Grok Bot has no committed config file. Official docs describe adding a custom MCP connector in the desktop UI, or asking a Bot to add an MCP server by URL (or by a command that runs on its computer).

## Official UI steps (verified)

1. Open **Connect apps** from the sidebar (in the mobile app: avatar → **Connect apps**).
2. At the bottom, choose **Add a custom connector**.
3. Enter a **Name** (for example `Deepege`).
4. Set **Type** to **Remote HTTPS**.
5. Enter the **Server URL**. Remote HTTPS is reached from the Bot’s cloud, so `http://127.0.0.1:8081/mcp` on your machine is typically unreachable; use a public HTTPS `/mcp` address (or a tunnel). Adding a server on a private network, or one that uses a private certificate authority, asks for your approval first.
6. Optionally add HTTP headers. You can also enter an OAuth Client ID; a Client Secret field appears once you enter a Client ID.
7. Choose **Add plugin** to save.

You can also ask a Bot to add an MCP server that is not in the catalog, by giving it the public URL.

For a self-hosted API key, add an HTTP header:

```
Authorization: Bearer <your API key>
```

Do not paste a production key into a chat transcript if you can enter it in the connector form instead. The exact header-editor layout (one field vs name/value pairs) is **not specified** beyond “optional HTTP headers.”

The official **Command** type starts a process on the Bot’s computer; this connector is a Streamable HTTP server, so use **Remote HTTPS**.

Source: [Use the computer and apps](https://docs.x.ai/grok-bot/computer-and-apps).
