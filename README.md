# SunPower Scraper

```
   _____              ____                                  
  / ___/__  ______   / __ \____ _      _____  _____         
  \__ \/ / / / __ \ / /_/ / __ \ | /| / / _ \/ ___/         
 ___/ / /_/ / / / // ____/ /_/ / |/ |/ /  __/ /             
/____/\__,_/_/ /_/_/    / .___/|__/|__/\___/_/              
                       /_/         Scraper                 
```

Lightweight poller for the SunStrong (MySunPower) mobile API. It fetches **current power** every N minutes and can:
- write rows to **GCS** (daily CSV),
- write rows to **Postgres**,
- send **Graphite metrics** to Grafana Cloud.

This repo does **not** include any secrets, tokens, or site identifiers. All configuration is via environment variables or CLI flags.

## Why this tool exists (data continuity)
If a vendor goes through restructuring, bankruptcy, or product transitions, app availability and data access can become inconsistent. This tool helps you export **your own live power data** to storage you control, so you can keep running dashboards and analyses even if the official app changes or goes offline.

## Requirements
- Python 3.10+
- `uv` (https://astral.sh/uv)

## Setup (uv)
Create a virtual environment and install deps:

```bash
uv venv
uv sync
```

Optional dependencies:
- GCS output: `uv sync --extra gcs`
- Postgres output: `uv sync --extra postgres`

## How the data works
The API returns **instantaneous power** values (typically in kW):
- `production` = solar generation power
- `consumption` = site load power
- `grid` = grid import/export power (sign varies by system)
- `storage` = battery power (if present)

To estimate energy (kWh) from power samples:
```
energy_kwh ≈ sum(power_kw * poll_interval_seconds / 3600)
```
Example for 5-minute polling: `power_kw * 5/60` per sample.

## Getting credentials (high level)
You need:
- **SUNSTRONG_TOKEN**: an access token from the app’s API requests.
- **SUNSTRONG_SITE_KEY**: the site key used in API queries.

Common approach is to capture the app’s GraphQL request headers and copy the Bearer token + site key. Do **not** commit these values to git.

## Configuration (env vars)
Required:
- `SUNSTRONG_TOKEN`
- `SUNSTRONG_SITE_KEY`

Optional (token refresh):
- `SUNSTRONG_USERNAME`
- `SUNSTRONG_PASSWORD`
- `SUNSTRONG_AUTH_URL` (default is in code)

Output mode:
- `OUTPUT_MODE` = `gcs` | `postgres` | `none` (default: `none`)
- `POLL_SECONDS` = poll interval in seconds (default: `300`)

GCS:
- `GCS_BUCKET`
- `GCS_PREFIX` (optional)
- `GOOGLE_APPLICATION_CREDENTIALS` or `GCP_SA_JSON`

Postgres:
- `PG_DSN` or `DATABASE_URL`

Grafana Graphite (optional):
- `GRAFANA_GRAPHITE_URL`
- `GRAFANA_USER`
- `GRAFANA_API_KEY`
- `GRAFANA_PREFIX` (default: `sunstrong.current_power`)
- `GRAFANA_USE_POLL_TIME` = `true` to stamp metrics with poll time

## Run
From the `oss` folder:

```bash
uv run python sunstrong_cli.py \
  --site-key "$SUNSTRONG_SITE_KEY" \
  --token "$SUNSTRONG_TOKEN" \
  --output gcs
```

Postgres:
```bash
uv run python sunstrong_cli.py \
  --output postgres \
  --pg-dsn "postgres://user:pass@host:5432/db"
```

Grafana metrics only:
```bash
uv run python sunstrong_cli.py \
  --output none \
  --grafana-url "https://<stack>.grafana.net/graphite/metrics" \
  --grafana-user "<instance_id>" \
  --grafana-api-key "<metrics_write_token>"
```

## Grafana dashboard
Import `grafana_sunstrong_dashboard.json` into Grafana:
1. Dashboards → New → Import
2. Upload the JSON
3. Select your Graphite data source

For kWh charts, the template uses `0.0833333333` (5 minutes) as the conversion factor. If you change the poll interval, update the scale factor to `POLL_SECONDS / 3600`.

## Security
- Never commit tokens, passwords, or site keys.
- Use env vars or secret managers for credentials.

## License
See the root repository license.
