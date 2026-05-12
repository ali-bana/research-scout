# Security and Secrets

## Secrets

Never commit:

- `.env`
- API keys
- Notion tokens
- SMTP passwords
- Semantic Scholar keys
- OpenAlex tokens
- database files
- logs containing secrets

Use `.env.example` with empty placeholders.

## Web App Exposure

The app must bind to `127.0.0.1` by default.

If exposed remotely, recommend one of:

- Tailscale
- WireGuard
- SSH tunnel
- Caddy or Nginx with HTTPS and additional auth

Do not recommend direct public exposure of the FastAPI server.

## Authentication

- Require login.
- Store password hashes, not plaintext passwords.
- Use `APP_SECRET_KEY`.
- Provide a helper command to generate password hashes.