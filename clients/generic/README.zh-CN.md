[English](README.md) | 简体中文

# 其他客户端（通用远程 MCP）

如果 MCP 客户端不在[客户端目录](../README.zh-CN.md)中，可以使用下面两种写法之一。

## 原生 Streamable HTTP（优先）

把客户端指向连接器的 `/mcp` 地址，并发送：

```
Authorization: Bearer <your API key>
```

[`mcp-http.example.json`](mcp-http.example.json) 只是示意性的 JSON，并不是所有客户端都要求这种标准。字段名（`type`、`transport`、`url`、`headers`）因客户端而异，请对照该客户端自己的文档映射。

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

本地客户端可用 `http://127.0.0.1:8081/mcp`。托管或云端客户端需要公开的 HTTPS 地址。

## 仅支持 stdio 的客户端：`mcp-remote`

如果客户端只能启动本地 stdio 进程，可用 `npx -y mcp-remote` 作为桥接。把 Bearer 值放在 `env` 中，并传入 `--header Authorization:${AUTH_HEADER}`，**冒号后不要加空格**（这是已知的参数转义规避方法）。见 [`mcp-remote.example.json`](mcp-remote.example.json)。

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

请在本地替换 `YOUR_DEEPEGE_API_KEY`，不要提交含密钥的文件。保存后重启客户端。

桥接资料来源：[geelen/mcp-remote](https://github.com/geelen/mcp-remote)。
