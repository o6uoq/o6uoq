"""
OAuth Manager for fitness APIs.
"""

import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import requests
from dotenv import load_dotenv

# Configure logging - RFC5424 compatible, minimalist
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class OAuthManager:
    """OAuth manager for fitness APIs."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        load_dotenv()
        self._load_config()

    def _load_config(self) -> None:
        """Load service-specific configuration from environment."""
        prefix = self.service_name.upper()

        # Service-specific endpoints and requirements
        if self.service_name == 'fitbit':
            self.auth_uri = "https://www.fitbit.com/oauth2/authorize"
            self.token_uri = "https://api.fitbit.com/oauth2/token"
            self.scope = "activity%20sleep"
            self.use_basic_auth = True
        elif self.service_name == 'strava':
            self.auth_uri = "https://www.strava.com/oauth/authorize"
            self.token_uri = "https://www.strava.com/oauth/token"
            self.scope = "activity:read"
            self.use_basic_auth = False
        else:
            logger.error(f"Unsupported service: {self.service_name}")
            raise ValueError(f"Unsupported service: {self.service_name}")

        # Load environment variables
        self.client_id = os.environ.get(f"{prefix}_CLIENT_ID")
        self.client_secret = os.environ.get(f"{prefix}_CLIENT_SECRET")
        self.redirect_uri = os.environ.get(f"{prefix}_REDIRECT_URI")
        self.access_token = os.environ.get(f"{prefix}_ACCESS_TOKEN")
        self.refresh_token_value = os.environ.get(f"{prefix}_REFRESH_TOKEN")
        self.expires_at = os.environ.get(f"{prefix}_EXPIRES_AT")

        # Validate required variables
        required = [self.client_id, self.client_secret, self.redirect_uri]
        if not all(required):
            missing = []
            if not self.client_id: missing.append(f"{prefix}_CLIENT_ID")
            if not self.client_secret: missing.append(f"{prefix}_CLIENT_SECRET")
            if not self.redirect_uri: missing.append(f"{prefix}_REDIRECT_URI")
            print(f"Error: Missing {self.service_name} environment variables: {', '.join(missing)}")
            sys.exit(1)

    def authenticate(self) -> None:
        """Handle OAuth authentication flow."""
        print("\n🔗 Please go to the following URL to authorize the application and get the code:")

        auth_url = f"{self.auth_uri}?response_type=code&client_id={self.client_id}&redirect_uri={self.redirect_uri}&scope={self.scope}"
        print(auth_url)

        auth_code = input("\n📝 Enter the authorization code: ")
        print()  # Add newline after auth code input

        auth_str = f"{self.client_id}:{self.client_secret}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        response = requests.post(
            self.token_uri,
            headers={"Authorization": f"Basic {auth_b64}", "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
                "code": auth_code
            }
        ).json()

        if 'access_token' in response:
            expires_in = response['expires_in']
            new_tokens = {
                f"{self.service_name.upper()}_ACCESS_TOKEN": response['access_token'],
                f"{self.service_name.upper()}_REFRESH_TOKEN": response['refresh_token'],
                f"{self.service_name.upper()}_EXPIRES_AT": str(int(time.time()) + expires_in)
            }
            os.environ.update(new_tokens)
            self._update_env_file(new_tokens)

            # Update instance variables
            self.access_token = new_tokens[f"{self.service_name.upper()}_ACCESS_TOKEN"]
            self.refresh_token_value = new_tokens[f"{self.service_name.upper()}_REFRESH_TOKEN"]
            self.expires_at = new_tokens[f"{self.service_name.upper()}_EXPIRES_AT"]

            print("✅ Updated tokens and expiration time in the .env file.")
        else:
            print("❌ Failed to authenticate. Response from API:")
            print(response)
            sys.exit(1)

    def _update_env_file(self, new_values: Dict[str, str]) -> None:
        """Update the .env file with new token values."""
        updated_lines = []
        found_keys = set(new_values.keys())

        try:
            with open('.env', 'r') as file:
                for line in file:
                    # Preserve comments and empty lines
                    if line.strip().startswith('#') or not line.strip():
                        updated_lines.append(line)
                        continue

                    # Update key-value pairs
                    if '=' in line:
                        key, _ = line.strip().split('=', 1)
                        if key in new_values:
                            updated_lines.append(f"{key}={new_values[key]}\n")
                            found_keys.discard(key)
                            continue

                    updated_lines.append(line)
        except FileNotFoundError:
            pass

        # Add any new key-value pairs
        for key in found_keys:
            updated_lines.append(f"{key}={new_values[key]}\n")

        with open('.env', 'w') as file:
            file.writelines(updated_lines)

        # Append expiration time as comment
        if f"{self.service_name.upper()}_EXPIRES_AT" in new_values:
            expiration_time = datetime.fromtimestamp(int(new_values[f"{self.service_name.upper()}_EXPIRES_AT"]), timezone.utc)
            expiration_time_str = expiration_time.strftime('%Y-%m-%d %H:%M:%S %Z')
            with open('.env', 'a') as file:
                file.write(f"\n# Tokens expire on {expiration_time_str}\n")

    def manage_tokens(self) -> None:
        """Refresh token if necessary and write JSON file."""
        if self.service_name == 'fitbit' or self.is_token_expired():
            self.refresh_token()

        self._create_token_json_file()

    def _create_token_json_file(self) -> None:
        """Write current token data to JSON file."""
        prefix = self.service_name.upper()
        os.environ[f"{prefix}_ACCESS_TOKEN"] = self.access_token or ""
        os.environ[f"{prefix}_REFRESH_TOKEN"] = self.refresh_token_value or ""
        os.environ[f"{prefix}_EXPIRES_AT"] = self.expires_at or ""

        token_data = {
            f"{prefix}_ACCESS_TOKEN": self.access_token or "",
            f"{prefix}_REFRESH_TOKEN": self.refresh_token_value or "",
            f"{prefix}_EXPIRES_AT": self.expires_at or ""
        }

        json_filename = f"{self.service_name.lower()}_tokens.json"
        with open(json_filename, 'w') as file:
            json.dump(token_data, file, indent=4)
            file.write('\n')

        print(f"✅ Created {json_filename} for GitHub Actions artifacts")

    def refresh_token(self) -> None:
        """Refresh the access token using the refresh token."""
        if not self.refresh_token_value:
            print(f"❌ No refresh token available for {self.service_name.capitalize()}")
            return

        auth_str = f"{self.client_id}:{self.client_secret}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        response = requests.post(
            self.token_uri,
            headers={"Authorization": f"Basic {auth_b64}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token_value}
        )

        if response.status_code == 200:
            response_json = response.json()
            self.access_token = response_json['access_token']
            self.refresh_token_value = response_json['refresh_token']
            self.expires_at = str(int(time.time()) + response_json['expires_in'])

            new_tokens = {
                f"{self.service_name.upper()}_ACCESS_TOKEN": self.access_token,
                f"{self.service_name.upper()}_REFRESH_TOKEN": self.refresh_token_value,
                f"{self.service_name.upper()}_EXPIRES_AT": self.expires_at
            }
            os.environ.update(new_tokens)
            self._update_env_file(new_tokens)

            self._create_token_json_file()
        else:
            print(f"❌ Failed to refresh {self.service_name} token:")
            print(response.text)
            sys.exit(1)

    def is_token_expired(self) -> bool:
        """Check if the current access token is expired."""
        current_time = int(time.time())
        expires_at = int(self.expires_at) if self.expires_at and self.expires_at.isdigit() else 0
        return current_time >= expires_at

    def ensure_valid_token(self) -> None:
        """Ensure we have a valid token, refreshing if necessary."""
        if self.is_token_expired():
            self.refresh_token()


def create_oauth_manager(service_name: str) -> Optional[OAuthManager]:
    """Create OAuth manager for specified service."""
    try:
        return OAuthManager(service_name)
    except ValueError:
        return None