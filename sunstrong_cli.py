import argparse
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

from sunstrong_scraper import (
    DEFAULT_AUTH_URL,
    DEFAULT_GRAPHQL_URL,
    DEFAULT_USER_AGENT,
    SunstrongClient,
    SunstrongClientConfig,
)


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value is not None else default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll SunStrong current power and write to GCS/Postgres/Grafana."
    )
    parser.add_argument("--site-key", default=env("SUNSTRONG_SITE_KEY"))
    parser.add_argument("--token", default=env("SUNSTRONG_TOKEN"))
    parser.add_argument("--username", default=env("SUNSTRONG_USERNAME"))
    parser.add_argument("--password", default=env("SUNSTRONG_PASSWORD"))
    parser.add_argument("--auth-url", default=env("SUNSTRONG_AUTH_URL"))
    parser.add_argument("--graphql-url", default=env("SUNSTRONG_GRAPHQL_URL"))
    parser.add_argument("--user-agent", default=env("SUNSTRONG_USER_AGENT"))

    parser.add_argument(
        "--output",
        choices=["gcs", "postgres", "none"],
        default=env("OUTPUT_MODE", "none"),
    )
    parser.add_argument("--poll-seconds", type=int, default=int(env("POLL_SECONDS", "300")))
    parser.add_argument("--once", action="store_true", help="Fetch once and exit.")

    parser.add_argument("--gcs-bucket", default=env("GCS_BUCKET"))
    parser.add_argument("--gcs-prefix", default=env("GCS_PREFIX", ""))
    parser.add_argument("--gcp-sa-json", default=env("GCP_SA_JSON"))
    parser.add_argument("--gcp-credentials", default=env("GOOGLE_APPLICATION_CREDENTIALS"))

    parser.add_argument("--pg-dsn", default=env("PG_DSN"))
    parser.add_argument("--database-url", default=env("DATABASE_URL"))

    parser.add_argument("--grafana-url", default=env("GRAFANA_GRAPHITE_URL"))
    parser.add_argument("--grafana-user", default=env("GRAFANA_USER"))
    parser.add_argument("--grafana-api-key", default=env("GRAFANA_API_KEY"))
    parser.add_argument("--grafana-prefix", default=env("GRAFANA_PREFIX", "sunstrong.current_power"))
    parser.add_argument(
        "--grafana-use-poll-time",
        action="store_true",
        default=env("GRAFANA_USE_POLL_TIME", "false").lower() in ("1", "true", "yes"),
    )

    return parser.parse_args()


def get_gcs_client(sa_json: str | None, credentials_path: str | None):
    from google.cloud import storage

    if sa_json:
        info = json.loads(sa_json)
        return storage.Client.from_service_account_info(info)
    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    return storage.Client()


def write_row_to_gcs(row: dict, bucket_name: str, prefix: str, sa_json: str | None, credentials_path: str | None) -> None:
    date_str = row["ts"][:10]
    local_dir = Path("data")
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / f"current_power_{date_str}.csv"

    client = get_gcs_client(sa_json, credentials_path)
    bucket = client.bucket(bucket_name)
    object_name = f"{prefix}/current_power_{date_str}.csv" if prefix else f"current_power_{date_str}.csv"
    blob = bucket.blob(object_name)

    if not local_path.exists() and blob.exists():
        blob.download_to_filename(str(local_path))

    write_header = not local_path.exists() or local_path.stat().st_size == 0
    with local_path.open("a", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["ts", "production", "consumption", "storage", "grid", "site_key"]
        )
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    blob.upload_from_filename(str(local_path))


def pg_connect(pg_dsn: str | None, database_url: str | None):
    dsn = pg_dsn or database_url
    if not dsn:
        raise ValueError("Missing PG_DSN or DATABASE_URL for Postgres output.")
    import psycopg2

    return psycopg2.connect(dsn)


def pg_init(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sunstrong_current_power (
                site_key TEXT NOT NULL,
                ts TIMESTAMPTZ NOT NULL,
                production_kw DOUBLE PRECISION,
                consumption_kw DOUBLE PRECISION,
                storage_kw DOUBLE PRECISION,
                grid_kw DOUBLE PRECISION,
                PRIMARY KEY (site_key, ts)
            );
            """
        )
    conn.commit()


def pg_write_row(conn, row: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sunstrong_current_power (
                site_key, ts, production_kw, consumption_kw, storage_kw, grid_kw
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (site_key, ts) DO NOTHING;
            """,
            (
                row["site_key"],
                row["ts"],
                row["production"],
                row["consumption"],
                row["storage"],
                row["grid"],
            ),
        )
    conn.commit()


def send_graphite_metrics(
    row: dict,
    url: str,
    user: str,
    api_key: str,
    prefix: str,
    use_poll_time: bool,
) -> None:
    ts = int(time.time()) if use_poll_time else int(datetime.fromisoformat(row["ts"]).timestamp())
    payload = [
        {
            "name": f"{prefix}.production",
            "interval": 300,
            "value": row["production"],
            "time": ts,
        },
        {
            "name": f"{prefix}.consumption",
            "interval": 300,
            "value": row["consumption"],
            "time": ts,
        },
        {
            "name": f"{prefix}.storage",
            "interval": 300,
            "value": row["storage"],
            "time": ts,
        },
        {
            "name": f"{prefix}.grid",
            "interval": 300,
            "value": row["grid"],
            "time": ts,
        },
    ]

    resp = requests.post(
        url,
        auth=(user, api_key),
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=15,
    )
    resp.raise_for_status()


def main() -> None:
    args = parse_args()

    if not args.site_key or not args.token:
        raise SystemExit("Missing --site-key/--token (or SUNSTRONG_SITE_KEY/SUNSTRONG_TOKEN).")

    config = SunstrongClientConfig(
        site_key=args.site_key,
        token=args.token,
        username=args.username,
        password=args.password,
        auth_url=args.auth_url or DEFAULT_AUTH_URL,
        graphql_url=args.graphql_url or DEFAULT_GRAPHQL_URL,
        user_agent=args.user_agent or DEFAULT_USER_AGENT,
    )
    client = SunstrongClient(config)

    pg_conn = None
    if args.output == "postgres":
        pg_conn = pg_connect(args.pg_dsn, args.database_url)
        pg_init(pg_conn)

    while True:
        row = client.fetch_current_power()
        row["site_key"] = args.site_key
        print(
            f"{row['ts']} prod={row['production']} cons={row['consumption']} "
            f"grid={row['grid']} storage={row['storage']}"
        )

        if args.output == "gcs":
            if not args.gcs_bucket:
                raise SystemExit("Missing GCS_BUCKET/--gcs-bucket for GCS output.")
            write_row_to_gcs(
                row,
                args.gcs_bucket,
                args.gcs_prefix or "",
                args.gcp_sa_json,
                args.gcp_credentials,
            )
        elif args.output == "postgres":
            pg_write_row(pg_conn, row)

        if args.grafana_url and args.grafana_user and args.grafana_api_key:
            send_graphite_metrics(
                row,
                args.grafana_url,
                args.grafana_user,
                args.grafana_api_key,
                args.grafana_prefix,
                args.grafana_use_poll_time,
            )

        if args.once:
            break

        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
