import base64
import json
import time
from datetime import datetime, timezone

import sunstrong_scraper as scraper


def make_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=")
    return f"{header_b64.decode('utf-8')}.{payload_b64.decode('utf-8')}.sig"


def test_jwt_expiry_parses_exp() -> None:
    exp = int(time.time()) + 120
    token = make_jwt({"exp": exp})
    assert scraper.SunstrongClient._jwt_expiry(token) == exp


def test_jwt_expiry_handles_invalid() -> None:
    assert scraper.SunstrongClient._jwt_expiry("not.a.jwt") is None
    assert scraper.SunstrongClient._jwt_expiry("bad") is None


def test_ensure_token_valid_refreshes_when_expired(monkeypatch) -> None:
    exp = int(time.time()) - 10
    token = make_jwt({"exp": exp})
    config = scraper.SunstrongClientConfig(site_key="site", token=token, username="u", password="p")
    client = scraper.SunstrongClient(config)

    refreshed = {"called": False}

    def fake_refresh() -> None:
        refreshed["called"] = True

    monkeypatch.setattr(client, "refresh_access_token", fake_refresh)
    client.ensure_token_valid()

    assert refreshed["called"] is True


def test_fetch_current_power_parses_response(monkeypatch) -> None:
    ts_ms = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": {
                    "currentPower": {
                        "production": 1.2,
                        "consumption": 0.8,
                        "storage": -0.4,
                        "grid": 0.1,
                        "timestamp": ts_ms,
                    }
                }
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(scraper.requests, "post", fake_post)
    config = scraper.SunstrongClientConfig(site_key="site", token="token")
    client = scraper.SunstrongClient(config)

    row = client.fetch_current_power()

    assert row["ts"] == "2024-01-01T00:00:00+00:00"
    assert row["production"] == 1.2
    assert row["consumption"] == 0.8
    assert row["storage"] == -0.4
    assert row["grid"] == 0.1
