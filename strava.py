import base64
import json
import os
import requests
import sys
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from .env file if they are not already set
load_dotenv()

# Required environment variables for Strava
required_env_vars = [
    'STRAVA_CLIENT_ID',
    'STRAVA_CLIENT_SECRET',
    'STRAVA_REDIRECT_URI',
    'STRAVA_ACCESS_TOKEN',
    'STRAVA_REFRESH_TOKEN',
    'STRAVA_EXPIRES_AT'
]

# Check if all required environment variables are set
missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    print(f"Error: Missing environment variables - {', '.join(missing_vars)}")
    sys.exit(1)

# Load tokens and credentials from environment variables
STRAVA_CLIENT_ID = os.environ['STRAVA_CLIENT_ID']
STRAVA_CLIENT_SECRET = os.environ['STRAVA_CLIENT_SECRET']
STRAVA_REDIRECT_URI = os.environ['STRAVA_REDIRECT_URI']
STRAVA_ACCESS_TOKEN = os.environ['STRAVA_ACCESS_TOKEN']
STRAVA_REFRESH_TOKEN = os.environ['STRAVA_REFRESH_TOKEN']
STRAVA_EXPIRES_AT = os.environ['STRAVA_EXPIRES_AT']

# Strava OAuth 2.0 endpoints
STRAVA_AUTH_URI = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_REQUEST_URI = "https://www.strava.com/oauth/token"

def update_env_file(new_values):
    """Update the .env file with new token values while preserving comments and appending expiration time."""
    updated_lines = []
    found_keys = set(new_values.keys())

    # Read the current contents of the .env file and update values
    with open('.env', 'r') as file:
        for line in file:
            # Preserve comments and empty lines
            if line.strip().startswith('#') or not line.strip():
                updated_lines.append(line)
                continue
            
            # Update key-value pairs
            if '=' in line:
                key, value = line.strip().split('=', 1)
                if key in new_values:
                    updated_lines.append(f"{key}={new_values[key]}\n")
                    found_keys.remove(key)
                    continue
            
            updated_lines.append(line)

    # Add any new key-value pairs that weren't in the original file
    for key in found_keys:
        updated_lines.append(f"{key}={new_values[key]}\n")

    # Write the updated contents back to the .env file
    with open('.env', 'w') as file:
        file.writelines(updated_lines)

    # Calculate and append the expiration time as a comment with timezone
    if 'STRAVA_EXPIRES_AT' in new_values:
        expiration_time = datetime.fromtimestamp(int(new_values['STRAVA_EXPIRES_AT']), timezone.utc)
        expiration_time_str = expiration_time.strftime('%Y-%m-%d %H:%M:%S %Z')
        with open('.env', 'a') as file:
            file.write(f"\n# Tokens expire on {expiration_time_str}\n")

def strava_auth():
    print("\nPlease go to the following URL to authorize the application:")
    auth_url = f"{STRAVA_AUTH_URI}?client_id={STRAVA_CLIENT_ID}&response_type=code&redirect_uri={STRAVA_REDIRECT_URI}&scope=activity:read"
    print(auth_url)
    auth_code = input("\nEnter the authorization code: ")

    auth_str = f"{STRAVA_CLIENT_ID}:{STRAVA_CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()

    response = requests.post(
        STRAVA_TOKEN_REQUEST_URI,
        headers={"Authorization": f"Basic {auth_b64}"},
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code": auth_code,
            "grant_type": "authorization_code"
        }
    )

    if response.status_code == 200:
        response_json = response.json()
        access_token = response_json['access_token']
        refresh_token = response_json['refresh_token']
        expires_at = str(int(time.time()) + response_json['expires_in'])

        # Update the environment variables and .env file
        new_tokens = {
            'STRAVA_ACCESS_TOKEN': access_token,
            'STRAVA_REFRESH_TOKEN': refresh_token,
            'STRAVA_EXPIRES_AT': expires_at
        }
        os.environ.update(new_tokens)
        update_env_file(new_tokens)

        print("\nUpdated Strava tokens and expiration time in the .env file.")
    else:
        print("\nFailed to authenticate. Response from Strava API:")
        print(response.json())
        sys.exit(1)

def update_token_data():
    """Update the environment variables and write the current token data to a JSON file."""
    global STRAVA_ACCESS_TOKEN, STRAVA_REFRESH_TOKEN, STRAVA_EXPIRES_AT

    # Update environment variables
    os.environ['STRAVA_ACCESS_TOKEN'] = STRAVA_ACCESS_TOKEN
    os.environ['STRAVA_REFRESH_TOKEN'] = STRAVA_REFRESH_TOKEN
    os.environ['STRAVA_EXPIRES_AT'] = STRAVA_EXPIRES_AT

    # Write token data to a JSON file
    token_data = {
        'STRAVA_ACCESS_TOKEN': STRAVA_ACCESS_TOKEN,
        'STRAVA_REFRESH_TOKEN': STRAVA_REFRESH_TOKEN,
        'STRAVA_EXPIRES_AT': STRAVA_EXPIRES_AT
    }

    with open('strava_tokens.json', 'w') as file:
        json.dump(token_data, file, indent=4)
        file.write('\n')  # Add a newline at the end of the file

def strava_tokens():
    """Check if the token is expired and refresh it if necessary. Then write the token data to a file."""
    if is_token_expired():
        refresh_token()

    # Always write the current token data to the JSON file
    update_token_data()

def refresh_token():
    """Refresh the access token using the refresh token."""
    global STRAVA_ACCESS_TOKEN, STRAVA_REFRESH_TOKEN, STRAVA_EXPIRES_AT

    response = requests.post(
        STRAVA_TOKEN_REQUEST_URI,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": STRAVA_REFRESH_TOKEN
        }
    )

    if response.status_code == 200:
        response_json = response.json()
        STRAVA_ACCESS_TOKEN = response_json['access_token']
        STRAVA_REFRESH_TOKEN = response_json['refresh_token']
        STRAVA_EXPIRES_AT = str(int(time.time()) + response_json['expires_in'])

        # Update the token data
        update_token_data()
    else:
        print("\nFailed to refresh token. Response from Strava API:\n")
        print(response.text)
        print()
        sys.exit(1)

def is_token_expired():
    """Check if the current access token is expired or about to expire."""
    current_time = int(time.time())
    expires_in = int(STRAVA_EXPIRES_AT) if STRAVA_EXPIRES_AT.isdigit() else 0
    return current_time >= expires_in

def format_elapsed_time(seconds):
    """Formats elapsed time in seconds to 'XhYm' format."""
    hours, minutes = divmod(seconds, 3600)
    minutes, _ = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h{minutes}m"
    else:
        return f"{minutes}m"

def strava_latest_workout():
    # Fetch the latest workout data using Strava's API
    if is_token_expired():
        refresh_token()
    try:
        endpoint = "https://www.strava.com/api/v3/athlete/activities"
        response = requests.get(endpoint, headers={"Authorization": f"Bearer {STRAVA_ACCESS_TOKEN}"})
        response.raise_for_status()
        activities = response.json()
        if activities:
            latest_activity = activities[0]
            name = latest_activity.get('name')
            elapsed_time = latest_activity.get('elapsed_time')
            formatted_time = format_elapsed_time(elapsed_time)
            print(name)
            print(formatted_time)
        else:
            print("No recent activities found.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Strava activities: {e}")

def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'strava-auth':
            strava_auth()
        elif command == 'strava-latest-workout':
            strava_latest_workout()
        elif command == 'strava-tokens':
            strava_tokens()
        else:
            print("\\nInvalid command. Use 'strava-auth', 'strava-latest-workout', or 'strava-tokens'.")
    else:
        print("\\nUsage: python script-name.py {strava-auth|strava-latest-workout|strava-tokens}")

if __name__ == "__main__":
    main()