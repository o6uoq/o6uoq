"""
Strava CLI tool for retrieving fitness data.
"""

import sys

from .oauth_manager import create_oauth_manager
from .strava_client import create_strava_client


def main() -> None:
    """Main entry point for Strava CLI commands."""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'strava-auth':
            oauth_manager = create_oauth_manager('strava')
            if oauth_manager:
                oauth_manager.authenticate()
            else:
                sys.exit(1)

        elif command in ('strava-latest-workout', 'strava-tokens', 'strava-tokens-refresh'):
            client = create_strava_client()
            if not client:
                sys.exit(1)

            if command == 'strava-latest-workout':
                client.get_latest_workout()
            elif command == 'strava-tokens':
                print("🔍 Strava Token Status:")
                print()
                print(f"Access Token: {'✅ Valid' if client.oauth.access_token else '❌ Missing'}")
                print(f"Refresh Token: {'✅ Available' if client.oauth.refresh_token_value else '❌ Missing'}")
                print(f"Expires: {client.oauth.expires_at}")
                print(f"Token Expired: {'❌ Yes' if client.oauth.is_token_expired() else '✅ No'}")
                client.oauth.manage_tokens()
                print("🔄 Tokens refreshed and saved!")
            elif command == 'strava-tokens-refresh':
                print("🔄 Refreshing Strava tokens...")
                try:
                    client.oauth.refresh_token()
                    print("✅ Strava tokens refreshed!")
                except SystemExit:
                    print("❌ Refresh token invalid. Please re-authenticate:")
                    print("Run: python -m app.strava strava-auth")

        else:
            print("\nInvalid command. Use 'strava-auth', 'strava-latest-workout', 'strava-tokens', or 'strava-tokens-refresh'.")
    else:
        print("\nUsage: python -m app.strava {strava-auth|strava-latest-workout|strava-tokens|strava-tokens-refresh}")

    print()


if __name__ == "__main__":
    main()