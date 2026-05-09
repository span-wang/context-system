# Context_For_XHS Cloudflare Tunnel

This project follows the same named-tunnel pattern used in the `DESK` project,
and exposes the unified web app through:

- `https://context.panspan.cloud`

## Recommended mapping

- Local Next.js frontend: `http://127.0.0.1:3000`
- Local FastAPI backend: `http://127.0.0.1:8000`
- Cloudflare public hostname: `https://context.panspan.cloud`

The frontend routes call `/platform/api/*` on the same origin, so
the tunnel only needs to expose the web app port.

When `deploy\cloudflare\config.yml` exists, `scripts\start.ps1` now auto-detects
the `hostname` entries and:

- passes them into Next.js `allowedDevOrigins`
- writes the public URL into `data/run/ports.json`
- shows the public URL in the startup output and platform settings page

## First-time setup

1. Login once:

```bat
deploy\cloudflare\cloudflared.exe tunnel login
```

2. Reuse your existing named tunnel if you already have one, or create a new one:

```bat
deploy\cloudflare\cloudflared.exe tunnel create context
```

3. Create DNS routing:

```bat
deploy\cloudflare\cloudflared.exe tunnel route dns context context.panspan.cloud
```

4. Copy the template:

```bat
copy deploy\cloudflare\config.named.example.yml deploy\cloudflare\config.yml
```

or generate it directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\cloudflare\configure_named_tunnel.ps1 `
  -TunnelId YOUR_TUNNEL_UUID `
  -Hostname context.panspan.cloud
```

5. Edit `deploy\cloudflare\config.yml`:

- `tunnel`: your tunnel UUID
- `credentials-file`: the matching JSON file under `%USERPROFILE%\.cloudflared\`

## Start the tunnel

```bat
deploy\cloudflare\start_named_tunnel.bat
```

## Notes

- Web 入口统一使用一个公网域名。
- 兼容保留 `/platform/*`，但建议直接使用主导航中的旧页面路径。
