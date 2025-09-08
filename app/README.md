# Fitness CLI Tools

Command-line tools for Fitbit and Strava APIs.

## Setup

### Prerequisites
- Python 3.13+
- Fitbit/Strava API credentials

### Install
```bash
# Using uv (recommended)
brew install uv
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Or using pip
pip install -r requirements.txt
```

### Environment
Create `.env` file with your API credentials:

```bash
# Fitbit - Required
FITBIT_CLIENT_ID=your_id
FITBIT_CLIENT_SECRET=your_secret
FITBIT_REDIRECT_URI=https://localhost

# Strava - Required
STRAVA_CLIENT_ID=your_id
STRAVA_CLIENT_SECRET=your_secret
STRAVA_REDIRECT_URI=https://localhost
```

**Note:** Additional variables (ACCESS_TOKEN, REFRESH_TOKEN, EXPIRES_AT) are auto-generated during OAuth authentication and don't need to be declared manually.

## Usage

### Fitbit
```bash
# Authenticate
python -m app.fitbit fitbit-auth

# Get data
python -m app.fitbit fitbit-steps
python -m app.fitbit fitbit-sleep

# Token management
python -m app.fitbit fitbit-tokens
python -m app.fitbit fitbit-tokens-refresh
```

### Strava
```bash
# Authenticate
python -m app.strava strava-auth

# Get data
python -m app.strava strava-latest-workout

# Token management
python -m app.strava strava-tokens
python -m app.strava strava-tokens-refresh
```

## Docker

```bash
docker build -t fitness-cli .

# Interactive shell (recommended for auth/token operations)
docker run -it --env-file .env -v $(pwd):/app fitness-cli /bin/sh

# Direct command execution
docker run --env-file .env -v $(pwd):/app fitness-cli python -m app.fitbit fitbit-steps
```

**Note:** The `-v $(pwd):/app` volume mount is required when running commands that update files (like authentication), otherwise changes won't persist to your host machine.

## Files

- `oauth_manager.py` - OAuth handling
- `fitbit_client.py` - Fitbit API
- `strava_client.py` - Strava API
- `fitbit.py` - Fitbit CLI
- `strava.py` - Strava CLI

## Notes

- Tokens auto-refresh when expired
- Use `python -m` for proper module resolution
- Credentials stored securely in environment