English | [简体中文](README.zh-CN.md)

# Other clients (generic remote MCP)

If your MCP client is not listed in the [client index](../README.md), use one of the two shapes below.

## Native Streamable HTTP (preferred)

Point the client at the connector’s `/mcp` URL and send:

```
Authorization: Bearer <your API key>
```

[`mcp-http.example.json`](mcp-http.example.json) is an illustrative JSON shape, not a standard required by every client. Field names (`type`, `transport`, `url`, `headers`) vary. Map them to whatever your client documents.

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

Local clients can use `http://127.0.0.1:8081/mcp`. Hosted or cloud clients need a public HTTPS URL.

## stdio-only clients: `mcp-remote`

If the client can only start a local stdio process, use `npx -y mcp-remote` as a bridge. Put the bearer value in `env` and pass `--header Authorization:${AUTH_HEADER}` with **no space after the colon** (a known args-escaping workaround). See [`mcp-remote.example.json`](mcp-remote.example.json).

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

Replace `YOUR_DEEPEGE_API_KEY` locally and do not commit it. Restart the client after saving.

Source for the bridge: [geelen/mcp-remote](https://github.com/geelen/mcp-remote).
