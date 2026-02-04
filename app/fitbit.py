"""
Fitbit CLI tool for retrieving fitness data.
"""

import sys

from .fitbit_client import create_fitbit_client
from .oauth_manager import create_oauth_manager


def main() -> None:
    """Main entry point for Fitbit CLI commands."""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "fitbit-auth":
            oauth_manager = create_oauth_manager("fitbit")
            if oauth_manager:
                oauth_manager.authenticate()
            else:
                sys.exit(1)

        elif command in ("fitbit-steps", "fitbit-sleep", "fitbit-tokens", "fitbit-tokens-refresh"):
            client = create_fitbit_client()
            if not client:
                sys.exit(1)

            if command == "fitbit-steps":
                client.get_steps()
            elif command == "fitbit-sleep":
                client.get_sleep()
            elif command == "fitbit-tokens":
                print("🔍 Fitbit Token Status:")
                print()
                print(f"Access Token: {'✅ Valid' if client.oauth.access_token else '❌ Missing'}")
                print(f"Refresh Token: {'✅ Available' if client.oauth.refresh_token_value else '❌ Missing'}")
                print(f"Expires: {client.oauth.expires_at}")
                print(f"Token Expired: {'❌ Yes' if client.oauth.is_token_expired() else '✅ No'}")
                if not client.oauth.manage_tokens():
                    sys.exit(1)
            elif command == "fitbit-tokens-refresh":
                print("🔄 Refreshing Fitbit tokens...")
                if client.oauth.refresh_token():
                    print("✅ Fitbit tokens refreshed!")
                else:
                    print("❌ Refresh token invalid. Please re-authenticate:")
                    print("Run: python -m app.fitbit fitbit-auth")

        else:
            print("\nInvalid command. Use 'fitbit-auth', 'fitbit-steps', 'fitbit-sleep',")
            print("'fitbit-tokens', or 'fitbit-tokens-refresh'.")
    else:
        print(
            "\nUsage: python -m app.fitbit {fitbit-auth|fitbit-steps|fitbit-sleep|fitbit-tokens|fitbit-tokens-refresh}"
        )

    print()


if __name__ == "__main__":
    main()
