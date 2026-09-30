"""Update independent profile lines only when their service returns valid data."""

import re
import subprocess
import sys
from pathlib import Path


def fetch(module: str, command: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", f"app.{module}", command], capture_output=True, text=True, timeout=120
    )
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode:
        raise RuntimeError(f"{command} failed; preserving existing profile data")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def replace_line(text: str, prefix: str, replacement: str) -> str:
    lines = text.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching profile line")
    original = lines[matches[0]]
    lines[matches[0]] = replacement + ("\n" if original.endswith("\n") else "")
    return "".join(lines)


def mark_unavailable(text: str, prefix: str) -> str:
    note = " <sub>Update unavailable; previous data shown</sub>"
    for line in text.splitlines():
        if line.startswith(prefix):
            line = line.replace("Today I have walked ", "Last recorded: I walked ")
            if not line.endswith(note):
                line += note
            return replace_line(text, prefix, line)
    return text


def update_profile(path: Path) -> int:
    text = path.read_text()
    failed = False
    try:
        steps = fetch("fitbit", "fitbit-steps")
        sleep = fetch("fitbit", "fitbit-sleep")
        if len(steps) != 1 or len(sleep) != 1 or not steps[0].isdigit() or not re.fullmatch(r"\d+h \d+m", sleep[0]):
            raise ValueError("Unexpected Fitbit output")
        text = replace_line(
            text,
            "- <samp> 🚶🏼‍♂️ ",
            f"- <samp> 🚶🏼‍♂️ Today I have walked **{steps[0]}** steps and slept for **{sleep[0]}** </samp><br>",
        )
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Fitbit update failed: {error}", file=sys.stderr)
        failed = True
        text = mark_unavailable(text, "- <samp> 🚶🏼‍♂️ ")
    try:
        workout = fetch("strava", "strava-latest-workout")
        if len(workout) != 2 or not re.fullmatch(r"(?:\d+h )?\d+m", workout[1]):
            raise ValueError("Unexpected Strava output")
        text = replace_line(
            text,
            "- <samp> 🏋🏼‍♂️ My last workout was ",
            f"- <samp> 🏋🏼‍♂️ My last workout was **{workout[0]}** for **{workout[1]}** </samp><br>",
        )
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Strava update failed: {error}", file=sys.stderr)
        failed = True
        text = mark_unavailable(text, "- <samp> 🏋🏼‍♂️ ")
    path.write_text(text)
    return int(failed)


if __name__ == "__main__":
    sys.exit(update_profile(Path("README.md")))
