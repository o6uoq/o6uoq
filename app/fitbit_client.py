"""Fitbit API client for retrieving fitness data."""

from datetime import UTC, datetime

import requests

from .oauth_manager import OAuthManager, create_oauth_manager


class FitbitClient:
    """Client for interacting with Fitbit API."""

    def __init__(self, oauth_manager: OAuthManager):
        self.oauth = oauth_manager

    def get_steps(self) -> None:
        """Fetch today's step count; propagate errors instead of publishing zero."""
        self.oauth.ensure_valid_token()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        response = requests.get(
            f"https://api.fitbit.com/1/user/-/activities/date/{today}.json",
            headers={"Authorization": f"Bearer {self.oauth.access_token}"},
            timeout=30,
        )
        response.raise_for_status()
        print(response.json()["summary"]["steps"])

    def get_sleep(self) -> None:
        """Fetch today's sleep using the same UTC date as steps."""
        self.oauth.ensure_valid_token()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        response = requests.get(
            f"https://api.fitbit.com/1.2/user/-/sleep/date/{today}.json",
            headers={"Authorization": f"Bearer {self.oauth.access_token}"},
            timeout=30,
        )
        response.raise_for_status()
        total_minutes = response.json()["summary"].get("totalMinutesAsleep", 0)
        hours, minutes = divmod(total_minutes, 60)
        print(f"{hours}h {minutes}m")


def create_fitbit_client() -> FitbitClient | None:
    oauth_manager = create_oauth_manager("fitbit")
    return FitbitClient(oauth_manager) if oauth_manager else None
