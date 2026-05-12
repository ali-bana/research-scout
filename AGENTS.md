# Research Radar — Codex Instructions

You are working on Research Radar, a self-hosted AI research assistant for one researcher.

## Project Boundary

- Modify only files inside this repository.
- Do not modify files outside this project directory.
- Do not commit secrets, tokens, passwords, API keys, local databases, logs, caches, virtual environments, or model files.
- Treat this repository as the full project boundary.

## Development Environment

- Use Python.
- Use `uv` for dependency management.
- Create the virtual environment at `./env`.
- Do not use Conda.
- Prefer commands that work from a fresh clone.
- Keep setup reproducible.

Expected setup commands:

```bash
uv venv ./env
source ./env/bin/activate
uv sync
```


Always use the OpenAI developer documentation MCP server if you need to work with the OpenAI API, ChatGPT Apps SDK, Codex, or related OpenAI docs without me having to explicitly ask.