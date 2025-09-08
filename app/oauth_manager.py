"""
Simplified OAuth Manager for fitness APIs.
"""

import base64
import json
import os
import sys
import time
from typing import Optional
import requests
from dotenv import load_dotenv

class OAuthManager:
    """Simplified OAuth manager with service-specific handling."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        load_dotenv()
        self._load_config()

    def _load_config(self) -> None:
        """Load service-specific configuration."""
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
        service_display = self.service_name.capitalize()  # Fitbit -> Fitbit, strava -> Strava
        print(f"\n🔗 Go to this URL to authorize {service_display}:")
        # URL-encode parameters properly for Strava
        from urllib.parse import quote
        client_id_clean = self.client_id.strip('"\'')  # Remove any quotes
        redirect_uri_clean = self.redirect_uri.strip('"\'')

        auth_url = (
            f"{self.auth_uri}?response_type=code"
            f"&client_id={client_id_clean}"
            f"&redirect_uri={quote(redirect_uri_clean)}"
            f"&scope={self.scope}"
        )
        print(auth_url)

        auth_code = input("\n📝 Enter the authorization code: ").strip()

        # Prepare token request
        data = {
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri_clean,
            "code": auth_code
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        if self.use_basic_auth:
            # Fitbit: Use Basic auth
            auth_str = f"{self.client_id}:{self.client_secret}"
            auth_b64 = base64.b64encode(auth_str.encode()).decode()
            headers["Authorization"] = f"Basic {auth_b64}"
        else:
            # Strava: Include credentials in data
            data.update({
                "client_id": self.client_id,
                "client_secret": self.client_secret
            })

        response = requests.post(self.token_uri, headers=headers, data=data)

        if response.status_code == 200:
            token_data = response.json()
            self._save_tokens(token_data)
            print(f"✅ {service_display} authentication successful!")
        else:
            print(f"❌ {service_display} authentication failed:")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            sys.exit(1)

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