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

# Required environment variables
required_env_vars = [
    'FITBIT_CLIENT_ID',
    'FITBIT_CLIENT_SECRET',
    'FITBIT_REDIRECT_URI',
    'FITBIT_ACCESS_TOKEN',
    'FITBIT_REFRESH_TOKEN',
    'FITBIT_EXPIRES_AT'
]

# Check if all required environment variables are set
missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
if missing_vars:
    print(f"Error: Missing environment variables - {', '.join(missing_vars)}")
    sys.exit(1)

# Load tokens and credentials from environment variables
FITBIT_CLIENT_ID = os.environ['FITBIT_CLIENT_ID']
FITBIT_CLIENT_SECRET = os.environ['FITBIT_CLIENT_SECRET']
FITBIT_REDIRECT_URI = os.environ['FITBIT_REDIRECT_URI']
FITBIT_ACCESS_TOKEN = os.environ['FITBIT_ACCESS_TOKEN']
FITBIT_REFRESH_TOKEN = os.environ['FITBIT_REFRESH_TOKEN']
FITBIT_EXPIRES_AT = os.environ['FITBIT_EXPIRES_AT']

# OAuth 2.0 endpoints
FITBIT_AUTH_URI = "https://www.fitbit.com/oauth2/authorize"
FITBIT_TOKEN_REQUEST_URI = "https://api.fitbit.com/oauth2/token"

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
    if 'FITBIT_EXPIRES_AT' in new_values:
        expiration_time = datetime.fromtimestamp(int(new_values['FITBIT_EXPIRES_AT']), timezone.utc)
        expiration_time_str = expiration_time.strftime('%Y-%m-%d %H:%M:%S %Z')
        with open('.env', 'a') as file:
            file.write(f"\n# Tokens expire on {expiration_time_str}\n")

def fitbit_auth():
    """Handle the manual authentication flow."""
    print("\nPlease go to the following URL to authorize the application and get the code:")
    
    # Ensure there are no quotes around client_id and redirect_uri
    auth_url = f"{FITBIT_AUTH_URI}?response_type=code&client_id={FITBIT_CLIENT_ID}&redirect_uri={FITBIT_REDIRECT_URI}&scope=activity%20sleep"
    
    print(auth_url)
    auth_code = input("\nEnter the authorization code: ")

    auth_str = f"{FITBIT_CLIENT_ID}:{FITBIT_CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()

    response = requests.post(
        FITBIT_TOKEN_REQUEST_URI,
        headers={"Authorization": f"Basic {auth_b64}", "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "redirect_uri": FITBIT_REDIRECT_URI,
            "code": auth_code
        }
    ).json()

    if 'access_token' in response:
        # Update the environment variables and .env file
        expires_in = response['expires_in']  # Get the lifetime of the token
        new_tokens = {
            'FITBIT_ACCESS_TOKEN': response['access_token'],
            'FITBIT_REFRESH_TOKEN': response['refresh_token'],
            'FITBIT_EXPIRES_AT': str(int(time.time()) + expires_in)  # Calculate when the token expires
        }
        os.environ.update(new_tokens)
        update_env_file(new_tokens)

        print("\nUpdated Fitbit tokens and expiration time in the .env file.")
    else:
        print("\nFailed to authenticate. Response from Fitbit API:")
        print(response)
        sys.exit(1)

def update_token_data():
    """Update the environment variables and write the current token data to a JSON file."""
    global FITBIT_ACCESS_TOKEN, FITBIT_REFRESH_TOKEN, FITBIT_EXPIRES_AT

    # Update environment variables
    os.environ['FITBIT_ACCESS_TOKEN'] = FITBIT_ACCESS_TOKEN
    os.environ['FITBIT_REFRESH_TOKEN'] = FITBIT_REFRESH_TOKEN
    os.environ['FITBIT_EXPIRES_AT'] = FITBIT_EXPIRES_AT

    # Write token data to a JSON file
    token_data = {
        'FITBIT_ACCESS_TOKEN': FITBIT_ACCESS_TOKEN,
        'FITBIT_REFRESH_TOKEN': FITBIT_REFRESH_TOKEN,
        'FITBIT_EXPIRES_AT': FITBIT_EXPIRES_AT
    }

    with open('fitbit_tokens.json', 'w') as file:
        json.dump(token_data, file, indent=4)
        file.write('\n')  # Add a newline at the end of the file

def fitbit_tokens():
    """Check if the token is expired and refresh it if necessary. Then write the token data to a file."""
    if is_token_expired():
        refresh_token()

    # Always write the current token data to the JSON file
    update_token_data()

def refresh_token():
    """Refresh the access token using the refresh token."""
    global FITBIT_ACCESS_TOKEN, FITBIT_REFRESH_TOKEN, FITBIT_EXPIRES_AT
    auth_str = f"{FITBIT_CLIENT_ID}:{FITBIT_CLIENT_SECRET}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()

    response = requests.post(
        FITBIT_TOKEN_REQUEST_URI,
        headers={"Authorization": f"Basic {auth_b64}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "refresh_token", "refresh_token": FITBIT_REFRESH_TOKEN}
    )

    if response.status_code == 200:
        response_json = response.json()
        FITBIT_ACCESS_TOKEN = response_json['access_token']
        FITBIT_REFRESH_TOKEN = response_json['refresh_token']
        FITBIT_EXPIRES_AT = str(int(time.time()) + response_json['expires_in'])

        # Update the token data
        update_token_data()
    else:
        print("\nFailed to refresh token. Response from Fitbit API:\n")
        print(response.text)
        print()
        sys.exit(1)

def is_token_expired():
    """Check if the current access token is expired or about to expire."""
    current_time = int(time.time())
    expires_at = int(FITBIT_EXPIRES_AT) if FITBIT_EXPIRES_AT.isdigit() else 0
    return current_time >= expires_at

def fitbit_steps():
    if is_token_expired():
        refresh_token()
    try:
        endpoint = "https://api.fitbit.com/1/user/-/activities/date/today.json"
        response = requests.get(endpoint, headers={"Authorization": f"Bearer {FITBIT_ACCESS_TOKEN}"})
        response.raise_for_status()
        data = response.json()
        steps = data['summary']['steps']
        print("\n" + str(steps))
    except requests.exceptions.RequestException as e:
        print(f"\nError fetching steps: {e}")

def fitbit_sleep():
    if is_token_expired():
        refresh_token()
    try:
        endpoint = "https://api.fitbit.com/1.2/user/-/sleep/date/today.json"
        response = requests.get(endpoint, headers={"Authorization": f"Bearer {FITBIT_ACCESS_TOKEN}"})
        response.raise_for_status()
        data = response.json()
        minutes = data['summary']['totalMinutesAsleep']
        hours, minutes_left = divmod(minutes, 60)
        print(f"\n{hours}h {minutes_left}m")
    except requests.exceptions.RequestException as e:
        print(f"\nError fetching sleep data: {e}")
        
def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'fitbit-auth':
            fitbit_auth()
        elif command == 'fitbit-steps':
            fitbit_steps()
        elif command == 'fitbit-sleep':
            fitbit_sleep()
        elif command == 'fitbit-tokens':
            fitbit_tokens()
        else:
            print("\nInvalid command. Use 'fitbit-auth', 'fitbit-steps', 'fitbit-sleep', or 'fitbit-tokens'.")
    else:
        print("\nUsage: python script-name.py {fitbit-auth|fitbit-steps|fitbit-sleep|fitbit-tokens}")
    print()  # New line added here

if __name__ == "__main__":
    main()