"""
Strava API client for retrieving fitness data.
"""

import sys

import requests

from .oauth_manager import OAuthManager, create_oauth_manager


class StravaClient:
    """Client for interacting with Strava API."""

    def __init__(self, oauth_manager: OAuthManager):
        self.oauth = oauth_manager

    @staticmethod
    def format_elapsed_time(seconds: int) -> str:
        """Format elapsed time in seconds to 'Xh Ym' format."""
        hours, remainder = divmod(seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes:02}m"
        else:
            return f"{minutes}m"

    def get_latest_workout(self) -> None:
        """Fetch and display the latest workout data."""
        self.oauth.ensure_valid_token()

        try:
            endpoint = "https://www.strava.com/api/v3/athlete/activities"
            response = requests.get(endpoint, headers={"Authorization": f"Bearer {self.oauth.access_token}"})
            response.raise_for_status()

            activities = response.json()
            if activities:
                latest_activity = activities[0]
                name = latest_activity.get("name", "Unknown Activity")
                elapsed_time = latest_activity.get("elapsed_time", 0)
                formatted_time = self.format_elapsed_time(elapsed_time)
                print(name)
                print(formatted_time)
            else:
                print("No Activity")
                print("0m")
        except requests.exceptions.RequestException as e:
            print("No Activity")  # Default on error
            print("0m")
            print(f"Error fetching Strava activities: {e}", file=sys.stderr)


def create_strava_client() -> StravaClient | None:
    """Factory function to create Strava client."""
    oauth_manager = create_oauth_manager("strava")
    if oauth_manager:
        return StravaClient(oauth_manager)
    return None
