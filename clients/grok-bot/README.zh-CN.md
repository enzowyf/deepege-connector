[English](README.md) | 简体中文

# Grok Bot

状态：**优先核实（测试）**

Grok Bot 没有需要提交的配置文件。官方文档说明可在桌面界面添加自定义 MCP 连接器，或让 Bot 按 URL 添加 MCP 服务器（也可以用在其计算机上运行的命令）。

## 官方界面步骤（已核实）

1. 从侧边栏打开 **Connect apps**（移动应用：头像 → **Connect apps**）。
2. 在底部选择 **Add a custom connector**。
3. 填写 **Name**（例如 `Deepege`）。
4. 将 **Type** 设为 **Remote HTTPS**。
5. 填写 **Server URL**。Remote HTTPS 由 Bot 的云端访问，因此你本机上的 `http://127.0.0.1:8081/mcp` 通常不可达；请使用公开的 HTTPS `/mcp` 地址（或隧道）。若服务器位于私有网络，或使用私有证书颁发机构，会先征求你的批准。
6. 可按需添加 HTTP 请求头。也可以填写 OAuth Client ID；一旦填写 Client ID，就会出现 Client Secret 字段。
7. 选择 **Add plugin** 保存。

也可以把公开 URL 发给 Bot，让它添加目录中没有的 MCP 服务器。

若使用自建 API key，请添加 HTTP 请求头：

```
Authorization: Bearer <your API key>
```

如果能在连接器表单里填写密钥，就不要把生产密钥粘到聊天记录里。除了「可选 HTTP 请求头」之外，官方没有写明表单的具体布局（单字段还是名/值对）。

官方的 **Command** 类型会在 Bot 的计算机上启动进程；本连接器是 Streamable HTTP 服务器，因此应使用 **Remote HTTPS**。

资料来源：[Use the computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)。
