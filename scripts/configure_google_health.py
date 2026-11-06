"""Validate Google Health access, then set GitHub secrets without logging credentials."""

import argparse
import json
import subprocess
import warnings
from getpass import GetPassWarning, getpass
from pathlib import Path

from app.google_health import SECRET_NAMES, GoogleHealthClient, GoogleHealthError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client_json", type=Path, help="Downloaded Google OAuth client JSON")
    args = parser.parse_args()
    try:
        subprocess.run(["gh", "auth", "status"], check=True, capture_output=True)
        registration = json.loads(args.client_json.expanduser().read_text())["web"]
        with warnings.catch_warnings(action="error", category=GetPassWarning):
            refresh_token = getpass("Google refresh token (hidden): ").strip()
        values = (registration["client_id"], registration["client_secret"], refresh_token)
        client = GoogleHealthClient(*values)
        identity = client.request("GET", "identity")
        if not identity.get("healthUserId"):
            raise GoogleHealthError("Google Health account identity could not be verified")
        steps, sleep = client.summary()
        print(f"Google Health access verified: {steps} steps; {sleep} sleep today.")
        for key, value in zip(SECRET_NAMES, values, strict=True):
            subprocess.run(["gh", "secret", "set", key, "--repo", "o6uoq/o6uoq"], input=value, text=True, check=True)
        print("Three Google Health repository secrets saved. No credentials were written to the checkout.")
    except GetPassWarning:
        parser.exit(1, "Hidden input is unavailable; run this command in an interactive terminal.\n")
    except GoogleHealthError as error:
        parser.exit(1, f"{error}\n")
    except OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError:
        parser.exit(1, "Setup failed; check the client JSON, GitHub login and repository access.\n")


if __name__ == "__main__":
    main()
