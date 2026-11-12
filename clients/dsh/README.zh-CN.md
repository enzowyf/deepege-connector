[English](README.md) | 简体中文

# DeepSeek Harness（dsh）

状态：**优先核实（测试）**

## 官方包（已核实）

dsh 使用 `@deepseek-ai/dsh-mcp-client`。官方 README 记录的 Streamable HTTP 写法是：

- `transport: streamable-http`
- `url`
- `headers`，其中 Authorization 用 YAML `!!js` 从环境变量取值

[`cordis.patch.yml`](cordis.patch.yml) 按该格式编写：

```yaml
insert:
  mcp:
    $unshift:
      - npm:@deepseek-ai/dsh-mcp-client
        serverName: deepege
        transport: streamable-http
        url: http://127.0.0.1:8081/mcp
        headers:
          Authorization: !!js '`Bearer ${process.env.DEEPEGE_API_KEY}`'
```

启动 dsh 前请先导出 `DEEPEGE_API_KEY`（本地 mock 可用 `sk-test-alice`）。工具会显示为 `mcp__deepege__<工具名>`，例如 `mcp__deepege__deepege_create_video_request`。

## 补丁路径（随版本变化，不能当作唯一标准路径）

补丁文件放在哪里取决于 dsh 版本和启动方式。公开文档和发行说明中出现过：

- `~/.dsh/cordis.patch.yml`
- `<项目目录>/.dsh/cordis.patch.yml`
- `~/.dsh/profiles/<配置名>/cordis.patch.yml`

请将准确路径视为**未核实 / 随版本变化**。先查看 `dsh --help`、已安装版本的官方 README，或当前会话使用的 profile 目录，再把这段 `mcp` 插入合并进该补丁，不要覆盖无关条目。

资料来源：[deepseek-ai/dsh-mcp-client](https://github.com/deepseek-ai/dsh-mcp-client)。
