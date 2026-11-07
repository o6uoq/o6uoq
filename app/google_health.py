"""Read the current day's reconciled steps and sleep from Google Health."""

import os
import re
import sys
from datetime import UTC, date, datetime, timedelta
from functools import partial

import requests
from dotenv import load_dotenv
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

API = "https://health.googleapis.com/v4/users/me"
SECRET_NAMES = ("GOOGLE_HEALTH_CLIENT_ID", "GOOGLE_HEALTH_CLIENT_SECRET", "GOOGLE_HEALTH_REFRESH_TOKEN")


class GoogleHealthError(RuntimeError):
    """A safe diagnostic that never includes provider bodies or credentials."""


def error_reason(response: requests.Response) -> str:
    """Return only recognised Google error labels; never provider text or metadata."""
    try:
        payload = response.json() if len(response.content) <= 16384 else {}
    except ValueError:
        return "unknown"
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        return "unknown"
    details = error.get("details", [])
    if isinstance(details, list):
        for detail in details:
            reason = detail.get("reason") if isinstance(detail, dict) else None
            if isinstance(reason, str) and reason in {
                "SERVICE_DISABLED",
                "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
                "ACCOUNT_NOT_LINKED",
                "BILLING_DISABLED",
            }:
                return reason
    message = error.get("message", "")
    if isinstance(message, str) and "could not mint ubermint from gaiamint" in message.lower():
        return "ACCOUNT_SIGN_IN_REQUIRED"
    status = error.get("status")
    return (
        status
        if isinstance(status, str)
        and status
        in {
            "PERMISSION_DENIED",
            "UNAUTHENTICATED",
            "FAILED_PRECONDITION",
            "RESOURCE_EXHAUSTED",
        }
        else "unknown"
    )


def nonnegative_integer(value: object) -> int:
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    raise GoogleHealthError("Google Health returned an invalid count")


def civil(day: date) -> dict:
    return {"date": {"year": day.year, "month": day.month, "day": day.day}}


def midnight_matches(value: object, day: date) -> bool:
    if not isinstance(value, dict) or value.get("date") != civil(day)["date"]:
        return False
    time = value.get("time", {})
    return isinstance(time, dict) and not any(time.values())


class GoogleHealthClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        if not all((client_id, client_secret, refresh_token)):
            raise GoogleHealthError("Set all three GOOGLE_HEALTH credentials")
        self.session = requests.Session()
        self.credentials = Credentials(
            token=None,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
        )

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(*(os.environ.get(key, "") for key in SECRET_NAMES))

    def authenticate(self) -> None:
        if not self.credentials.valid:
            try:
                self.credentials.refresh(partial(Request(session=self.session), timeout=30))
            except GoogleAuthError:
                raise GoogleHealthError("Google Health token refresh failed; reauthorise Google access") from None

    def request(self, method: str, path: str, **kwargs) -> dict:
        self.authenticate()
        try:
            result = self.session.request(
                method,
                f"{API}/{path}",
                headers={"Authorization": f"Bearer {self.credentials.token}"},
                timeout=30,
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException as error:
            raise GoogleHealthError(f"Google Health request failed: {type(error).__name__}") from None
        if result.status_code != 200:
            operation = {
                "identity": "identity",
                "dataTypes/steps/dataPoints:dailyRollUp": "steps",
                "dataTypes/sleep/dataPoints:reconcile": "sleep",
            }.get(path, "request")
            raise GoogleHealthError(
                f"Google Health {operation} returned HTTP {result.status_code} (reason: {error_reason(result)})"
            )
        try:
            payload = result.json()
        except ValueError:
            raise GoogleHealthError("Google Health returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise GoogleHealthError("Google Health returned an invalid response")
        return payload

    def summary(self, today: date | None = None) -> tuple[int, str]:
        # Retain the old updater's UTC date label; the API applies the recorded civil times.
        today = today or datetime.now(UTC).date()
        tomorrow = today + timedelta(days=1)
        try:
            payload = self.request(
                "POST",
                "dataTypes/steps/dataPoints:dailyRollUp",
                json={
                    "range": {"start": civil(today), "end": civil(tomorrow)},
                    "windowSizeDays": 1,
                },
            )
            rows = payload.get("rollupDataPoints", [])
            if not isinstance(rows, list) or len(rows) != 1:
                raise GoogleHealthError("Google Health has no daily steps observation")
            row = rows[0]
            if not midnight_matches(row["civilStartTime"], today) or not midnight_matches(
                row["civilEndTime"], tomorrow
            ):
                raise GoogleHealthError("Google Health returned an unexpected steps date range")
            steps = nonnegative_integer(row["steps"]["countSum"])
            parameters = {
                "filter": (
                    f'sleep.interval.civil_end_time >= "{today}" AND sleep.interval.civil_end_time < "{tomorrow}"'
                ),
                "pageSize": 25,
            }
            minutes, sessions = 0, 0
            seen_tokens = set()
            while True:
                payload = self.request("GET", "dataTypes/sleep/dataPoints:reconcile", params=dict(parameters))
                points = payload.get("dataPoints", [])
                if not isinstance(points, list):
                    raise GoogleHealthError("Google Health returned invalid sleep records")
                for point in points:
                    minutes += nonnegative_integer(point["sleep"]["summary"]["minutesAsleep"])
                    sessions += 1
                token = payload.get("nextPageToken", "")
                if not token:
                    break
                if not isinstance(token, str) or token in seen_tokens:
                    raise GoogleHealthError("Google Health returned invalid sleep pagination")
                seen_tokens.add(token)
                parameters["pageToken"] = token
            if not sessions:
                raise GoogleHealthError("Google Health has no sleep sessions ending today; sync your device")
        except KeyError, TypeError:
            raise GoogleHealthError("Google Health response is missing steps or sleep observations") from None
        hours, remainder = divmod(minutes, 60)
        return steps, f"{hours}h {remainder}m"


def main() -> None:
    try:
        steps, sleep = GoogleHealthClient.from_env().summary()
        print(steps)
        print(sleep)
    except GoogleHealthError as error:
        print(error, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
