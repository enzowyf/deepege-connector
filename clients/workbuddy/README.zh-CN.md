[English](README.md) | 简体中文

# WorkBuddy

状态：**优先核实（测试）**

## 官方配置路径（已核实）

WorkBuddy 官方 MCP 指南记录了两级配置：

| 级别 | 路径 |
| --- | --- |
| 用户级 | `~/.workbuddy/mcp.json` |
| 项目级 | `<项目目录>/.workbuddy/mcp.json` |

也可以在界面中添加：侧边栏 **插件** → **MCP 服务器** → **配置 MCP**。保存后状态灯为绿色表示连接成功。

该指南中的官方示例是本地 **stdio** 服务（`command` / `args` / `env`），没有给出 Streamable HTTP 的 JSON 示例。

## 远程 Streamable HTTP 模板（对照官方指南未核实）

[`mcp.json`](mcp.json) 使用 `type`、`url` 和 `headers`。这种写法出现在第三方 WorkBuddy 连接器说明中，但**对照官方 MCP 指南尚未核实**。如果你的版本在界面里提供了 Streamable HTTP 或请求头字段，优先用界面配置。若粘贴 JSON，请把 `deepege` 条目合并进已有的 `mcpServers`，不要整文件覆盖。

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

请先导出 `DEEPEGE_API_KEY`（本地 mock 可用 `sk-test-alice`）。WorkBuddy 是否展开 `${DEEPEGE_API_KEY}` 也**未核实**；如果请求头被原样发送，请在界面或不会提交的本地文件中填写密钥。

资料来源：[WorkBuddy MCP 指南](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)。
