# Security

Research Radar is designed for one researcher on a private machine. Treat it as a private service, not a public web app.

## Do Not Expose Directly

The default bind address is `127.0.0.1`. Keep it that way unless you put the app behind a secure access layer.

Recommended options:

- Tailscale
- WireGuard
- SSH tunnel
- Caddy or another reverse proxy with HTTPS and additional authentication

If you bind to `0.0.0.0`, use TLS, a firewall, and an access control layer. The built-in password login is useful, but it should not be the only protection for a public IP.

## Secrets

Never commit:

- `.env`
- API keys
- Notion tokens
- SMTP passwords
- database files
- logs
- local model files
- virtual environments

The `.gitignore` excludes these local files. Keep Codex prompts, shell history, and screenshots free of secrets as well.

## Rotate Secrets

To rotate the session secret:

```bash
openssl rand -hex 32
```

Put the new value in `APP_SECRET_KEY` and restart the web app. Existing sessions will be invalidated.

To rotate the admin password:

```bash
research-radar hash-password
```

Put the printed value in `ADMIN_PASSWORD_HASH` and restart the web app.

Rotate Notion, SMTP, OpenAI-compatible, Semantic Scholar, and OpenAlex credentials from their provider dashboards, then update `.env`.

## Cookies and CSRF

Research Radar uses signed session cookies and CSRF tokens for state-changing form posts. Set:

```bash
SESSION_HTTPS_ONLY=true
```

when serving through HTTPS. Leave it `false` only for local HTTP development.

## Local LLMs and GPU Use

The web server does not load a local model at startup. LLM providers are called only by scheduled digest jobs or explicit manual actions. If you run Ollama, vLLM, or another model server, secure that service separately and avoid binding it publicly.

## Deployment Checklist

- Keep `APP_HOST=127.0.0.1` unless protected by VPN or reverse proxy.
- Replace the example `APP_SECRET_KEY`.
- Replace the example admin password hash.
- Store `.env` outside git.
- Use HTTPS for remote access.
- Back up the SQLite database if the digest history matters.
- Review logs before sharing bug reports.
