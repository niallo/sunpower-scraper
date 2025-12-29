import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

DEFAULT_AUTH_URL = "https://edp-api.edp.sunstrongmonitoring.com/v1/auth/okta/signin"
DEFAULT_GRAPHQL_URL = "https://edp-api-graphql.mysunstrong.com/graphql"
DEFAULT_USER_AGENT = "SunStrongConnect/10825 CFNetwork/3860.200.71 Darwin/25.1.0"


@dataclass
class SunstrongClientConfig:
    site_key: str
    token: str
    username: str | None = None
    password: str | None = None
    auth_url: str = DEFAULT_AUTH_URL
    graphql_url: str = DEFAULT_GRAPHQL_URL
    user_agent: str = DEFAULT_USER_AGENT


class SunstrongClient:
    def __init__(self, config: SunstrongClientConfig):
        self.config = config
        self._token_expiry = self._jwt_expiry(config.token)

    @staticmethod
    def _jwt_expiry(token: str) -> int | None:
        # Decode JWT exp without verification to check when it expires.
        try:
            parts = token.split(".")
            if len(parts) < 2:
                return None
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
            return int(data.get("exp")) if "exp" in data else None
        except Exception:
            return None

    def refresh_access_token(self) -> None:
        if not self.config.username or not self.config.password:
            raise RuntimeError("Missing username/password for token refresh.")

        headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Authorization": "Bearer undefined",
            "Content-Type": "application/json; charset=utf-8",
            "Host": "edp-api.edp.sunstrongmonitoring.com",
            "User-Agent": self.config.user_agent,
        }
        payload = {
            "remember": "true",
            "username": self.config.username,
            "password": self.config.password,
        }

        resp = requests.post(self.config.auth_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError(f"Auth response missing access_token: {data}")

        self.config.token = access_token
        self._token_expiry = self._jwt_expiry(access_token)

    def ensure_token_valid(self) -> None:
        if not self.config.token:
            self.refresh_access_token()
            return
        if self._token_expiry:
            now = int(time.time())
            if now >= self._token_expiry - 60:
                self.refresh_access_token()

    def _headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "accept": "*/*",
            "originatingfrom": "MOBILE",
            "apollographql-client-version": "1.1.2",
            "apollographql-client-name": "SunStrongConnectMobile",
            "user-agent": self.config.user_agent,
            "authorization": f"Bearer {self.config.token}",
        }

    def fetch_current_power(self) -> dict[str, str | float]:
        for attempt in range(2):
            self.ensure_token_valid()

            query = {
                "operationName": "FetchCurrentPower",
                "variables": {"siteKey": self.config.site_key},
                "query": (
                    "query FetchCurrentPower($siteKey: String!) { "
                    "currentPower(siteKey: $siteKey) { "
                    "production consumption storage grid timestamp } }"
                ),
            }

            resp = requests.post(
                self.config.graphql_url, headers=self._headers(), json=query, timeout=30
            )

            if resp.status_code in (401, 403) and attempt == 0:
                self.refresh_access_token()
                continue

            resp.raise_for_status()
            data = resp.json()

            if "errors" in data:
                errors = json.dumps(data["errors"])
                if "UNAUTHENTICATED" in errors or "Unauthorized" in errors:
                    if attempt == 0:
                        self.refresh_access_token()
                        continue
                raise RuntimeError(f"GraphQL errors: {data['errors']}")

            current = data.get("data", {}).get("currentPower")
            if not current:
                raise RuntimeError(f"No currentPower in response: {data}")

            ts_ms = int(current["timestamp"])
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

            return {
                "ts": ts.isoformat(),
                "production": float(current["production"]),
                "consumption": float(current["consumption"]),
                "storage": float(current["storage"]),
                "grid": float(current["grid"]),
            }

        raise RuntimeError("Failed to fetch current power after retry.")
