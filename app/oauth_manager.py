"""
OAuth Manager for fitness APIs - matches original fitbit.py functionality.
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
    """OAuth manager matching original fitbit.py functionality."""

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

        # Load environment variables (global vars for compatibility)
        self.client_id = os.environ.get(f"{prefix}_CLIENT_ID")
        self.client_secret = os.environ.get(f"{prefix}_CLIENT_SECRET")
        self.redirect_uri = os.environ.get(f"{prefix}_REDIRECT_URI")
        self.access_token = os.environ.get(f"{prefix}_ACCESS_TOKEN")
        self.refresh_token_value = os.environ.get(f"{prefix}_REFRESH_TOKEN")
        self.expires_at = os.environ.get(f"{prefix}_EXPIRES_AT")

        # Validate required variables (only for auth, tokens can be empty initially)
        required = [self.client_id, self.client_secret, self.redirect_uri]
        if not all(required):
            missing = []
            if not self.client_id: missing.append(f"{prefix}_CLIENT_ID")
            if not self.client_secret: missing.append(f"{prefix}_CLIENT_SECRET")
            if not self.redirect_uri: missing.append(f"{prefix}_REDIRECT_URI")
            print(f"Error: Missing {self.service_name} environment variables: {', '.join(missing)}")
            sys.exit(1)

    def authenticate(self) -> None:
        """Handle OAuth authentication flow - matches original fitbit_auth."""
        print("\n🔗 Please go to the following URL to authorize the application and get the code:")

        # Ensure there are no quotes around client_id and redirect_uri
        auth_url = f"{self.auth_uri}?response_type=code&client_id={self.client_id}&redirect_uri={self.redirect_uri}&scope={self.scope}"
        print(auth_url)

        auth_code = input("\n📝 Enter the authorization code: ")

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
            # Update the environment variables and .env file
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

            print("\n✅ Updated tokens and expiration time in the .env file.")
        else:
            print("\n❌ Failed to authenticate. Response from API:")
            print(response)
            sys.exit(1)

    def _update_env_file(self, new_values: Dict[str, str]) -> None:
        """Update the .env file with new token values while preserving comments and appending expiration time."""
        updated_lines = []
        found_keys = set(new_values.keys())

        # Read the current contents of the .env file and update values
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
                            found_keys.remove(key)
                            continue

                    updated_lines.append(line)
        except FileNotFoundError:
            # .env file doesn't exist, create it
            pass

        # Add any new key-value pairs that weren't in the original file
        for key in found_keys:
            updated_lines.append(f"{key}={new_values[key]}\n")

        # Write the updated contents back to the .env file
        with open('.env', 'w') as file:
            file.writelines(updated_lines)

        # Calculate and append the expiration time as a comment with timezone
        if f"{self.service_name.upper()}_EXPIRES_AT" in new_values:
            expiration_time = datetime.fromtimestamp(int(new_values[f"{self.service_name.upper()}_EXPIRES_AT"]), timezone.utc)
            expiration_time_str = expiration_time.strftime('%Y-%m-%d %H:%M:%S %Z')
            with open('.env', 'a') as file:
                file.write(f"\n# Tokens expire on {expiration_time_str}\n")

    def manage_tokens(self) -> None:
        """Check if token is expired and refresh if necessary, then write JSON file."""
        if self.is_token_expired():
            self.refresh_token()

        # Always write the current token data to JSON file for GitHub Actions
        self._create_token_json_file()

    def _create_token_json_file(self) -> None:
        """Write current token data to JSON file - matches original update_token_data."""
        # Update environment variables (ensure they're current)
        prefix = self.service_name.upper()
        os.environ[f"{prefix}_ACCESS_TOKEN"] = self.access_token or ""
        os.environ[f"{prefix}_REFRESH_TOKEN"] = self.refresh_token_value or ""
        os.environ[f"{prefix}_EXPIRES_AT"] = self.expires_at or ""

        # Write token data to JSON file
        token_data = {
            f"{prefix}_ACCESS_TOKEN": self.access_token or "",
            f"{prefix}_REFRESH_TOKEN": self.refresh_token_value or "",
            f"{prefix}_EXPIRES_AT": self.expires_at or ""
        }

        json_filename = f"{self.service_name.lower()}_tokens.json"
        with open(json_filename, 'w') as file:
            json.dump(token_data, file, indent=4)
            file.write('\n')  # Add newline at end

        print(f"✅ Created {json_filename} for GitHub Actions artifacts")

    def refresh_token(self) -> None:
        """Refresh the access token using the refresh token."""
        if not self.refresh_token_value:
            print(f"\n❌ No refresh token available for {self.service_name.capitalize()}")
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

            # Update the token data
            self._create_token_json_file()
        else:
            print(f"\n❌ Failed to refresh {self.service_name} token:")
            print(response.text)
            print()
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

    def _save_tokens(self, token_data: dict) -> None:
        """Save tokens to environment and files."""
        prefix = self.service_name.upper()
        expires_in = token_data.get('expires_in', 21600)  # Default 6 hours

        new_tokens = {
            f"{prefix}_ACCESS_TOKEN": token_data['access_token'],
            f"{prefix}_REFRESH_TOKEN": token_data.get('refresh_token', ''),
            f"{prefix}_EXPIRES_AT": str(int(time.time()) + expires_in)
        }

        # Update environment
        os.environ.update(new_tokens)

        # Save to .env file
        self._update_env_file(new_tokens)

        # Update instance variables
        self.access_token = new_tokens[f"{prefix}_ACCESS_TOKEN"]
        self.refresh_token_value = new_tokens[f"{prefix}_REFRESH_TOKEN"]
        self.expires_at = new_tokens[f"{prefix}_EXPIRES_AT"]

    def _update_env_file(self, new_values: dict) -> None:
        """Update .env file with new values."""
        env_path = os.path.join(os.getcwd(), '.env')

        try:
            with open(env_path, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        # Update existing values
        updated_lines = []
        found_keys = set()

        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                key = line.split('=', 1)[0]
                if key in new_values:
                    updated_lines.append(f"{key}={new_values[key]}\n")
                    found_keys.add(key)
                    continue
            updated_lines.append(line)

        # Add new values
        for key, value in new_values.items():
            if key not in found_keys:
                updated_lines.append(f"{key}={value}\n")

        with open(env_path, 'w') as f:
            f.writelines(updated_lines)

        print(f"✅ Updated {env_path} with new tokens")

        # Reload environment variables from the updated .env file
        load_dotenv(override=True)

    def refresh_token(self) -> None:
        """Refresh the access token."""
        service_display = self.service_name.capitalize()
        if not self.refresh_token_value:
            print(f"❌ No refresh token available for {service_display}")
            return

        data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token_value}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        if self.use_basic_auth:
            auth_str = f"{self.client_id}:{self.client_secret}"
            auth_b64 = base64.b64encode(auth_str.encode()).decode()
            headers["Authorization"] = f"Basic {auth_b64}"
        else:
            data.update({
                "client_id": self.client_id,
                "client_secret": self.client_secret
            })

        response = requests.post(self.token_uri, headers=headers, data=data)

        if response.status_code == 200:
            token_data = response.json()
            self._save_tokens(token_data)
            print(f"🔄 {service_display} token refreshed!")
        else:
            print(f"❌ Failed to refresh {service_display} token:")
            print(response.text)
            sys.exit(1)

    def is_token_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expires_at:
            return True
        current_time = int(time.time())
        expires_at = int(self.expires_at) if self.expires_at.isdigit() else 0
        return current_time >= expires_at

    def ensure_valid_token(self) -> None:
        """Ensure we have a valid token."""
        if self.is_token_expired():
            self.refresh_token()

    def manage_tokens(self) -> None:
        """Check and refresh tokens if needed."""
        if self.is_token_expired():
            self.refresh_token()
        self._update_env_file({
            f"{self.service_name.upper()}_ACCESS_TOKEN": self.access_token,
            f"{self.service_name.upper()}_REFRESH_TOKEN": self.refresh_token_value,
            f"{self.service_name.upper()}_EXPIRES_AT": self.expires_at
        })


def create_oauth_manager(service_name: str) -> Optional[OAuthManager]:
    """Create OAuth manager for specified service."""
    try:
        return OAuthManager(service_name)
    except ValueError:
        return None