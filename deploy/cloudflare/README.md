# Context_For_XHS Cloudflare Tunnel

This project follows the same named-tunnel pattern used in the `DESK` project,
but exposes the new platform through:

- `https://context.panspan.cloud`

## Recommended mapping

- Local Next.js frontend: `http://127.0.0.1:3000`
- Local FastAPI backend: `http://127.0.0.1:8000`
- Cloudflare public hostname: `https://context.panspan.cloud`

The `/platform/*` frontend routes call `/platform/api/*` on the same origin, so
the tunnel only needs to expose the web app port.

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

5. Edit `deploy\cloudflare\config.yml`:

- `tunnel`: your tunnel UUID
- `credentials-file`: the matching JSON file under `%USERPROFILE%\.cloudflared\`

## Start the tunnel

```bat
deploy\cloudflare\start_named_tunnel.bat
```

## Notes

- The old product remains under the original local routes.
- The new platform frontend is now unified under `/platform/*`.
- If you later want the old product to have its own public hostname too, add a second hostname rule in `ingress`.
