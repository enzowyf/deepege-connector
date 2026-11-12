[English](README.md) | 简体中文

# 客户端适配

这里是把 MCP 客户端接到 Deepege 连接器（Streamable HTTP）的简要说明和配置模板。请先按仓库根目录 README 启动连接器，本地联调用 `http://127.0.0.1:8081/mcp`，托管或远程客户端则改用公开的 HTTPS `/mcp` 地址。

不要把真实 API key 写入要提交的文件。在环境中导出 `DEEPEGE_API_KEY`（或客户端要求的同义变量）。`sk-test-alice` 这类令牌只用于仓库内的 mock。

四个 **优先核实（测试）** 客户端已对照当前公开文档核对，是第一批目标。其余列出的客户端同样依据公开官方文档整理。未能确认的格式会标明 **未核实**。

## 目录

| 客户端 | 状态 | 位置 |
| --- | --- | --- |
| [WorkBuddy](workbuddy/README.zh-CN.md) | 优先核实（测试） | [`workbuddy/`](workbuddy/) |
| [ChatGPT（含 Codex）](chatgpt/README.zh-CN.md) | 优先核实（测试） | [`chatgpt/`](chatgpt/) |
| [DeepSeek Harness（dsh）](dsh/README.zh-CN.md) | 优先核实（测试） | [`dsh/`](dsh/) |
| [Grok Bot](grok-bot/README.zh-CN.md) | 优先核实（测试） | [`grok-bot/`](grok-bot/) |
| [其他客户端（通用）](generic/README.zh-CN.md) | 通用说明 | [`generic/`](generic/) |

## 通用远程 MCP

如果客户端不在上表中，请使用[通用远程 MCP](generic/README.zh-CN.md)做法：用 Streamable HTTP 访问 `/mcp`，并带上 `Authorization: Bearer <api_key>` 请求头。只支持 stdio 的客户端可用其中的 `mcp-remote` 桥接。
