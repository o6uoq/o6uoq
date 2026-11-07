"""Validate Google Health access, then set GitHub secrets without logging credentials."""

import argparse
import json
import os
import subprocess
import warnings
from getpass import GetPassWarning, getpass
from pathlib import Path

from dotenv import dotenv_values, set_key

from app.google_health import SECRET_NAMES, GoogleHealthClient, GoogleHealthError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_json", nargs="?", type=Path, help="Downloaded Google OAuth client JSON (initial setup)")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="Private local credential file")
    parser.add_argument("--reauthorize", action="store_true", help="Prompt for a replacement refresh token")
    args = parser.parse_args()
    try:
        subprocess.run(["gh", "auth", "status"], check=True, capture_output=True)
        env_file = args.env_file.expanduser()
        existing = dotenv_values(env_file)
        if args.client_json:
            registration = json.loads(args.client_json.expanduser().read_text())["web"]
            client_id, client_secret = registration["client_id"], registration["client_secret"]
        else:
            client_id, client_secret = (existing.get(key) for key in SECRET_NAMES[:2])
        if not client_id or not client_secret:
            raise GoogleHealthError("Google client credentials missing; supply the downloaded client JSON or .env")
        refresh_token = existing.get("GOOGLE_HEALTH_REFRESH_TOKEN")
        if args.reauthorize or not refresh_token:
            with warnings.catch_warnings(action="error", category=GetPassWarning):
                refresh_token = getpass("Google refresh token (hidden): ").strip()
        values = (client_id, client_secret, refresh_token)
        client = GoogleHealthClient(*values)
        client.authenticate()
        if env_file.is_symlink():
            raise GoogleHealthError("Refusing to write credentials through a symlink")
        descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(descriptor)
        env_file.chmod(0o600)
        for key, value in zip(SECRET_NAMES, values, strict=True):
            set_key(str(env_file), key, value)
        print("Google OAuth accepted; credentials saved privately.")
        identity = client.request("GET", "identity")
        if not identity.get("healthUserId"):
            raise GoogleHealthError("Google Health account identity could not be verified")
        steps, sleep = client.summary()
        print(f"Google Health access verified: {steps} steps; {sleep} sleep today.")
        for key, value in zip(SECRET_NAMES, values, strict=True):
            subprocess.run(["gh", "secret", "set", key, "--repo", "o6uoq/o6uoq"], input=value, text=True, check=True)
        print(f"Credentials saved privately in {env_file}; three Google Health repository secrets updated.")
    except GetPassWarning:
        parser.exit(1, "Hidden input is unavailable; run this command in an interactive terminal.\n")
    except GoogleHealthError as error:
        parser.exit(1, f"{error}\n")
    except OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError:
        parser.exit(1, "Setup failed; check the client JSON, GitHub login and repository access.\n")


if __name__ == "__main__":
    main()
