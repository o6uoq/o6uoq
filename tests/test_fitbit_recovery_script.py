"""Exercise recovery wiring without provider calls or real credentials."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def recovery(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "refresh-fitbit-secrets.sh"
    shutil.copy2(Path(__file__).parents[1] / "scripts" / script.name, script)
    (tmp_path / ".env").write_text("FITBIT_ACCESS_TOKEN=old\nFITBIT_REFRESH_TOKEN=old\n")
    commands = tmp_path / "bin"
    commands.mkdir()
    log = tmp_path / "calls.jsonl"
    driver = """import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
secret = sys.stdin.read() if name == "gh" and args[:2] == ["secret", "set"] else ""
with open(os.environ["RECOVERY_CALL_LOG"], "a") as output:
    output.write(json.dumps({"name": name, "args": args, "stdin": secret}) + "\\n")
if name == "uv":
    if os.environ.get("FAIL_AUTH") == "1":
        sys.exit(1)
    Path(".env").write_text("FITBIT_ACCESS_TOKEN=new-access\\nFITBIT_REFRESH_TOKEN=new-refresh\\nFITBIT_EXPIRES_AT=1234567890\\n")
"""
    for name in ("uv", "gh"):
        executable = commands / name
        executable.write_text(f"#!{sys.executable}\n{driver}")
        executable.chmod(0o755)
    env = {**os.environ, "PATH": f"{commands}:{os.environ['PATH']}", "RECOVERY_CALL_LOG": str(log)}

    def run(*args, fail_auth=False):
        result = subprocess.run(
            [str(script), *args],
            cwd=tmp_path,
            env={**env, "FAIL_AUTH": str(int(fail_auth))},
            capture_output=True,
            text=True,
        )
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    return run


def test_recovery_transfers_new_secrets_over_stdin_and_dispatches_main(recovery):
    result, calls = recovery("--dispatch")
    assert result.returncode == 0
    secrets = [call for call in calls if call["args"][:2] == ["secret", "set"]]
    assert {call["args"][2]: call["stdin"] for call in secrets} == {
        "FITBIT_ACCESS_TOKEN": "new-access",
        "FITBIT_REFRESH_TOKEN": "new-refresh",
    }
    assert all("new-access" not in call["args"] and "new-refresh" not in call["args"] for call in calls)
    assert "new-access" not in result.stdout + result.stderr
    assert "new-refresh" not in result.stdout + result.stderr
    assert any(
        call["args"] == ["workflow", "run", "main.yaml", "--ref", "main", "-f", "skip_artifact=true"] for call in calls
    )
    assert next(call for call in calls if call["name"] == "uv")["args"][:2] == ["run", "--frozen"]


def test_failed_consent_never_uploads_or_dispatches(recovery):
    result, calls = recovery("--dispatch", fail_auth=True)
    assert result.returncode != 0
    assert not any(call["args"][:2] in (["secret", "set"], ["workflow", "run"]) for call in calls)


@pytest.mark.parametrize("args,code", [(("--help",), 0), (("--unknown",), 2), (("--dispatch", "extra"), 2)])
def test_help_and_invalid_arguments_never_start_consent(recovery, args, code):
    result, calls = recovery(*args)
    assert result.returncode == code
    assert calls == []
