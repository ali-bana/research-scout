# Research Radar

Research Radar is a self-hosted AI research assistant for one researcher. It collects recent AI/ML papers and research signals, ranks them against your current interests, generates a daily digest of at most 10 papers, supports weekly discovery for missed papers, and folds in a Notion watchlist where you keep active research ideas.

The MVP is deliberately simple: Python, SQLite, FastAPI, Jinja2, scheduled CLI jobs, and a deterministic mock LLM provider that works without any model or API key.

## What It Does

- Ingests recent arXiv papers from configurable categories.
- Ingests RSS/news feeds from `config/rss_feeds.yaml`.
- Optionally reads Notion pages/databases into `notion_snapshots`.
- Ranks papers using transparent scoring signals before any LLM is required.
- Generates daily and weekly digests with stored score breakdowns and one-line selection reasons.
- Sends digest email through SMTP when configured, and skips email cleanly when not configured.
- Provides a private web UI for digests, papers, RSS items, Notion snapshots, feedback, profile editing, and job logs.
- Runs without Notion, SMTP, X/Twitter, Ollama, OpenAI-compatible endpoints, Semantic Scholar, or OpenAlex configured.

## Architecture

The app is split into small modules:

- `research_radar/config.py` loads environment variables from `.env`.
- `research_radar/models.py` defines SQLite tables with SQLAlchemy.
- `research_radar/ingest/` contains arXiv, RSS, Notion, Semantic Scholar, OpenAlex, and X placeholder connectors.
- `research_radar/ranking/` loads `config/profile.yaml` and scores papers with transparent signals.
- `research_radar/llm/` defines a provider interface plus mock, Ollama, and OpenAI-compatible providers.
- `research_radar/digest/` generates daily/weekly digests and email.
- `research_radar/web/` serves the FastAPI/Jinja UI.
- `research_radar/cli.py` exposes scheduled and manual commands.

SQLite is used for the MVP. The models avoid SQLite-specific assumptions so the project can later move to PostgreSQL plus pgvector for embeddings.

## Setup With uv

From a fresh clone:

```bash
uv venv ./env
source ./env/bin/activate
uv sync
cp .env.example .env
research-radar init-db
research-radar ingest
research-radar generate-daily
research-radar web
```

Open `http://127.0.0.1:8000`.

The example login password is `research-radar`. Replace it before real use:

```bash
research-radar hash-password
```

Put the printed value in `ADMIN_PASSWORD_HASH`.

## Why `./env`

This repo intentionally uses `./env` instead of a global environment, Conda environment, or hidden `.venv`. The target machine is expected to be a single-user DGX Spark-style workstation, and keeping the environment inside the project makes scheduled commands and systemd units explicit and reproducible. `./env` is ignored by git.

The repository includes a `.venv` symlink to `env` so `uv sync` still targets `./env` on uv versions that otherwise prefer a project-local `.venv` path.

## Configuration

Copy `.env.example` to `.env` and edit values:

- `APP_HOST=127.0.0.1` binds locally by default.
- `APP_SECRET_KEY` signs session cookies. Generate a random value before real use.
- `ADMIN_PASSWORD_HASH` stores the admin password hash.
- `DATABASE_URL=sqlite:///./data/research_radar.db` stores the MVP database locally.
- `ARXIV_CATEGORIES`, `ARXIV_MAX_RESULTS`, and `ARXIV_DAYS_BACK` control arXiv ingestion.
- `DAILY_MAX_PAPERS` caps daily digest length.
- `WEEKLY_DISCOVERY_WINDOW_DAYS` controls weekly discovery lookback.

The interest profile lives in `config/profile.yaml` and can also be edited in the web UI.

## Notion Setup

Create a Notion internal integration, copy its token, and share the target page or database with that integration.

Set one or both:

```bash
NOTION_TOKEN=secret_...
NOTION_PAGE_IDS=page-id-1,page-id-2
NOTION_DATABASE_ID=database-id
```

The MVP extracts plain text from block children where possible and stores snapshots in `notion_snapshots`. If Notion is not configured, ingestion and the UI continue to work and show `Notion not configured`.

## Semantic Scholar Setup

Semantic Scholar is optional. Set:

```bash
SEMANTIC_SCHOLAR_API_KEY=
```

The connector currently exposes future enrichment methods:

- `get_paper_metadata(...)`
- `get_recommendations(...)`
- `get_citation_context(...)`

When the key is missing, these methods return `not_configured` instead of failing.

## OpenAlex Placeholders

OpenAlex is also optional. Set any values you have:

```bash
OPENALEX_EMAIL=
OPENALEX_API_KEY=
OPENALEX_TOKEN=
```

The connector mirrors the same future enrichment interface as Semantic Scholar and returns `not_configured` when credentials are absent.

## SMTP Setup

Set these to enable email:

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=radar@example.com
DIGEST_TO_EMAIL=you@example.com
```

If SMTP is not configured, `research-radar send-daily` logs `email skipped` and the digest remains available in the web UI. Email includes each paper's one-line selection reason.

## Local LLM Setup

The default provider is deterministic:

```bash
LLM_PROVIDER=mock
```

No GPU is used by the web server. Real providers are only called by explicit jobs:

- `research-radar generate-daily`
- `research-radar discover-weekly`
- manual digest/explanation actions in the web UI

For Ollama:

```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gpt-oss-120b
```

For vLLM or another OpenAI-compatible server:

```bash
LLM_PROVIDER=openai-compatible
OPENAI_BASE_URL=http://127.0.0.1:8001/v1
OPENAI_API_KEY=
OPENAI_MODEL=gpt-oss-120b
```

The OpenAI-compatible provider uses the Chat Completions-style `/chat/completions` endpoint under the configured base URL. It is intentionally initialized lazily and does not load or contact a model at web-server startup.

## Scoring and Selection Reasons

Ranking is transparent before LLM use. Signals include:

- keyword/topic match with `config/profile.yaml`
- Notion watchlist match
- negative-topic penalty
- recency
- author/lab watchlist bonus
- feedback-based boosts and penalties
- diversity penalty for near-duplicate titles
- weekly discovery keyword bonuses

Every selected digest item stores:

- final score
- score breakdown
- deterministic fallback `selection_reason`
- optional `llm_selection_reason`
- short explanation

The UI and email display the LLM reason when available, otherwise the fallback reason.

## Security Recommendations

The web app is private by default and binds to `127.0.0.1`. Do not expose it directly to the internet.

Recommended access patterns:

- Tailscale or WireGuard
- SSH tunnel
- Caddy or another reverse proxy with HTTPS and additional authentication

Before real use:

```bash
openssl rand -hex 32
research-radar hash-password
```

Put those values in `APP_SECRET_KEY` and `ADMIN_PASSWORD_HASH`. See `SECURITY.md` for more detail.

## Scheduling

Install the systemd user timers by copying or linking the files in `scripts/systemd/` to `~/.config/systemd/user/`, then edit the paths if this repository is elsewhere.

```bash
systemctl --user daemon-reload
systemctl --user enable --now research-radar-daily.timer
systemctl --user enable --now research-radar-weekly.timer
```

The daily timer runs `research-radar run-all` at 06:00. The weekly timer runs `research-radar discover-weekly` on Monday at 06:30.

A cron example is in `scripts/cron/research-radar.cron`.

Scheduled commands invoke the CLI and then exit. They do not keep local model services alive, and they only call LLM providers when digest jobs run.

## Development Workflow

```bash
source ./env/bin/activate
uv sync --extra dev
pytest
ruff check .
research-radar init-db
research-radar web
```

Useful commands:

```bash
research-radar ingest
research-radar generate-daily
research-radar discover-weekly
research-radar send-daily
research-radar run-all
```

Network failures are logged and skipped where possible so the local UI remains usable.

## Roadmap

- Add migration management and PostgreSQL support.
- Add embeddings and pgvector for similarity-aware feedback.
- Add Semantic Scholar/OpenAlex enrichment in ranking.
- Add read-only X/Twitter signal ingestion.
- Add richer duplicate detection.
- Add per-topic feedback controls.
- Add digest export formats.
- Add more robust background job progress reporting.
