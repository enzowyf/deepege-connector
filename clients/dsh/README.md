English | [简体中文](README.zh-CN.md)

# DeepSeek Harness (dsh)

Status: **priority-verified (beta)**

## Official package (verified)

dsh uses `@deepseek-ai/dsh-mcp-client`. The official README documents Streamable HTTP as:

- `transport: streamable-http`
- `url`
- `headers`, including an Authorization value written with YAML `!!js` so the token is read from the environment

The template in [`cordis.patch.yml`](cordis.patch.yml) follows that shape:

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

Export `DEEPEGE_API_KEY` before starting dsh (for the local mock, `sk-test-alice`). Tools appear as `mcp__deepege__<tool>`, for example `mcp__deepege__deepege_create_video_request`.

## Patch path (version-dependent, unverified as a single canonical path)

Where to put the patch file depends on the dsh version and how you launch it. Public docs and releases have used:

- `~/.dsh/cordis.patch.yml`
- `<project>/.dsh/cordis.patch.yml`
- `~/.dsh/profiles/<profile>/cordis.patch.yml`

Treat the exact path as **unverified / version-dependent**. Check `dsh --help`, the official README for your installed version, or the profile directory your session is using, then merge this `mcp` insert into that patch rather than replacing unrelated entries.

Source: [deepseek-ai/dsh-mcp-client](https://github.com/deepseek-ai/dsh-mcp-client).
