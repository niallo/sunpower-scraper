# Repository Guidelines

## Project Structure & Module Organization
- `sunstrong_scraper.py` implements the SunStrong API client and current-power fetch logic.
- `sunstrong_cli.py` is the CLI entrypoint that polls, writes outputs, and emits metrics.
- `grafana_sunstrong_dashboard.json` is a Grafana dashboard template for Graphite.
- `pyproject.toml` and `requirements.txt` define dependencies and optional extras.
- `tests/` contains the pytest suite for core client behavior.
- `data/` is created at runtime to stage daily CSVs before upload.

## Build, Test, and Development Commands
- `uv venv` and `uv sync` create a virtualenv and install dependencies.
- `uv sync --extra gcs` or `uv sync --extra postgres` installs optional output backends.
- `uv sync --extra test` installs pytest for the test suite.
- `uv run python sunstrong_cli.py --site-key "$SUNSTRONG_SITE_KEY" --token "$SUNSTRONG_TOKEN" --output none --once` runs a single fetch for a smoke test.
- `uv run pytest` executes the test suite.
- If you are not using `uv`, install with `pip install -r requirements.txt` and run with `python sunstrong_cli.py`.

## Coding Style & Naming Conventions
- Python 3.10+ with 4-space indentation and standard PEP 8 formatting.
- Use type hints (matching existing modules) and `snake_case` for functions/vars.
- Keep constants in `UPPER_SNAKE_CASE` and avoid inline secrets or tokens.
- CLI concerns live in `sunstrong_cli.py`; reusable logic stays in `sunstrong_scraper.py`.
- No formatter or linter is configured; keep changes small and readable.

## Testing Guidelines
- Tests live in `tests/` and use `pytest`; name files `test_*.py`.
- Run `uv run pytest` before submitting changes that touch API parsing or output logic.
- Manual check: run the CLI with `--once` and `--output none` to verify API access and parsing.

## Commit & Pull Request Guidelines
- The history is minimal with no strict convention; use short, imperative summaries (e.g., "Add GCS upload retry").
- PRs should describe the change, list any new env vars, and include a manual test command with results.
- Never include credentials in commits, diffs, or PR screenshots.

## Security & Configuration Tips
- Required secrets (`SUNSTRONG_TOKEN`, `SUNSTRONG_SITE_KEY`) must come from env vars or CLI flags.
- Optional outputs rely on `GCS_BUCKET`, `PG_DSN`/`DATABASE_URL`, and Grafana credentials; keep them out of version control.
