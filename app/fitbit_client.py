"""
Fitbit API client for retrieving fitness data.
"""

import sys
from datetime import datetime, timezone, date
from typing import Optional

import requests

from .oauth_manager import OAuthManager, create_oauth_manager


class FitbitClient:
    """Client for interacting with Fitbit API."""

    def __init__(self, oauth_manager: OAuthManager):
        self.oauth = oauth_manager

    def get_steps(self) -> None:
        """Fetch and display today's step count."""
        self.oauth.ensure_valid_token()

        try:
            current_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            endpoint = f"https://api.fitbit.com/1/user/-/activities/date/{current_date}.json"

            response = requests.get(
                endpoint,
                headers={"Authorization": f"Bearer {self.oauth.access_token}"}
            )
            response.raise_for_status()

            data = response.json()
            steps = data['summary']['steps']
            print(f"\n{steps}")
        except requests.exceptions.RequestException as e:
            print(f"\n0")  # Default to 0 steps on error
            print(f"Error fetching steps: {e}", file=sys.stderr)

    def get_sleep(self) -> None:
        """Fetch and display today's sleep data."""
        self.oauth.ensure_valid_token()

        try:
            today = date.today().strftime("%Y-%m-%d")
            endpoint = f"https://api.fitbit.com/1.2/user/-/sleep/date/{today}.json"

            response = requests.get(
                endpoint,
                headers={"Authorization": f"Bearer {self.oauth.access_token}"}
            )
            response.raise_for_status()

            data = response.json()
            total_minutes = data['summary'].get('totalMinutesAsleep', 0)
            hours, minutes_left = divmod(total_minutes, 60)
            print(f"{hours}h {minutes_left}m")
        except requests.exceptions.RequestException as e:
            print(f"0h 0m")  # Default to 0h 0m on error
            print(f"Error fetching sleep data: {e}", file=sys.stderr)


def create_fitbit_client() -> Optional[FitbitClient]:
    """Factory function to create Fitbit client."""
    oauth_manager = create_oauth_manager('fitbit')
    if oauth_manager:
        return FitbitClient(oauth_manager)
    return None