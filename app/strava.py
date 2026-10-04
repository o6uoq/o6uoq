"""
Strava CLI tool for retrieving fitness data.
"""

import sys

import requests

from .oauth_manager import create_oauth_manager, response_summary
from .strava_client import StravaClient, create_strava_client
from .strava_web import StravaWebsiteError, latest_workout


def main() -> None:
    """Main entry point for Strava CLI commands."""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "strava-auth":
            oauth_manager = create_oauth_manager("strava")
            if oauth_manager:
                oauth_manager.authenticate()
            else:
                sys.exit(1)

        elif command == "strava-latest-workout":
            name, elapsed = latest_workout()
            print(name)
            print(StravaClient.format_elapsed_time(elapsed))
            return

        elif command in ("strava-tokens", "strava-tokens-refresh"):
            client = create_strava_client()
            if not client:
                sys.exit(1)

            if command == "strava-tokens":
                print("🔍 Strava Token Status:")
                print()
                print(f"Access Token: {'✅ Valid' if client.oauth.access_token else '❌ Missing'}")
                print(f"Refresh Token: {'✅ Available' if client.oauth.refresh_token_value else '❌ Missing'}")
                print(f"Expires: {client.oauth.expires_at}")
                print(f"Token Expired: {'❌ Yes' if client.oauth.is_token_expired() else '✅ No'}")
                if not client.oauth.manage_tokens():
                    sys.exit(1)
            elif command == "strava-tokens-refresh":
                print("🔄 Refreshing Strava tokens...")
                if client.oauth.refresh_token():
                    print("✅ Strava tokens refreshed!")
                else:
                    print("❌ Refresh token invalid. Please re-authenticate:")
                    print("Run: python -m app.strava strava-auth")
                    sys.exit(1)

        else:
            print("\nInvalid command. Use 'strava-auth', 'strava-latest-workout',")
            print("'strava-tokens', or 'strava-tokens-refresh'.")
    else:
        print("\nUsage: python -m app.strava")
        print("  {strava-auth|strava-latest-workout|strava-tokens|strava-tokens-refresh}")

    print()


if __name__ == "__main__":
    try:
        main()
    except StravaWebsiteError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as error:
        detail = response_summary(error.response) if error.response is not None else type(error).__name__
        print(f"API request failed: {detail}", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError, KeyError, TypeError) as error:
        print(f"Command failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
