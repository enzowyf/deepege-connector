[English](README.md) | 简体中文

# ChatGPT（含 Codex）

状态：**优先核实（测试）**

当前公开文档里，ChatGPT 与 Codex 共用 MCP 接入说明。ChatGPT 网页版通过插件使用远程 MCP。ChatGPT 桌面应用、Codex CLI 和 IDE 扩展在同一 Codex 宿主上共用一份本地配置。ChatGPT 网页版**不会**读取本地 Codex 配置文件。

资料来源：[Model Context Protocol | ChatGPT Learn](https://learn.chatgpt.com/docs/extend/mcp)。

## ChatGPT 网页版（插件）

1. 打开 **Plugins**。
2. 点击加号，选择 **Add custom MCP server**。
3. 填写名称（例如 `Deepege`），描述可选。
4. 在 **Connection** 中填写连接器的**公开 HTTPS** MCP 地址，以 `/mcp` 结尾。ChatGPT 网页版访问不到 localhost。如果工作区提供 Secure MCP Tunnel，也可以选用隧道。
5. 为服务器配置鉴权。
6. 确认风险提示后创建插件，安装，并在对话里用 `@` 引用。

官方文档为自定义 MCP 服务器列出的鉴权方式是 **OAuth**、**无鉴权**，以及 **混合**（OAuth 或无鉴权）。网页插件表单中的静态 `Authorization: Bearer` 请求头字段**未见记载**，因此**未核实**。若要在 ChatGPT 网页版使用自建 API key，应走已有文档路径（在托管 OAuth 可用时使用它），不要自行发明表单字段。

工作区方案和管理员权限仍然适用。另见 [Connecting custom MCP servers in ChatGPT](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)。

## ChatGPT 桌面应用、Codex CLI 与 IDE（共用配置）

这些界面共用 MCP 配置。官方为 Streamable HTTP 列出的能力包括 Bearer token 鉴权和 OAuth。

### 桌面或 IDE 界面（已核实）

1. 打开 **Settings**（桌面）或齿轮菜单（IDE 扩展），进入 **MCP servers**。
2. 选择 **Add server**。
3. 填写名称，选择 **Streamable HTTP**，并填入服务器 URL（本地为 `http://127.0.0.1:8081/mcp`）。
4. 保存，并按界面提示重启。

列表会标出需要 OAuth 的服务器，需要登录时选择 **Authenticate**。在输入框输入 `/mcp` 可查看已连接的服务器。

官方界面步骤中**没有写出**静态 Bearer token 填在 Add server 表单的哪个位置。Bearer token 在共用的 `config.toml` 中有明确说明（见下）。如果表单没有 token 字段，请改用该文件，或使用 **Authenticate** 走 OAuth。

### `config.toml`（已核实）

ChatGPT 桌面应用、Codex CLI 和 IDE 扩展读取 `~/.codex/config.toml`，或受信任项目下的 `.codex/config.toml`。请将 [`config.toml`](config.toml) 中的片段合并进你的文件。不要把 API key 写进文件，改为在环境中导出。内联 `bearer_token` 字段会被拒绝，应使用 `bearer_token_env_var`。

```toml
[mcp_servers.deepege]
url = "http://127.0.0.1:8081/mcp"
bearer_token_env_var = "DEEPEGE_API_KEY"
```

```bash
export DEEPEGE_API_KEY=sk-test-alice
```

也可以使用 `codex mcp add` / `codex mcp list` / `codex mcp login`。当前可用的命令行参数请以 `codex mcp --help` 为准。MCP 文档页没有单独给出「Streamable HTTP URL + bearer 环境变量」的完整 `add` 示例，因此这里以已核实的 `config.toml` 字段为准。

如果改用 OAuth 而不是 API key，请省略 `bearer_token_env_var`，在托管连接器可用后运行 `codex mcp login deepege`（或在界面中选择 **Authenticate**）。
