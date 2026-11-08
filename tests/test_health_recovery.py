import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from app.oauth_manager import OAuthManager
from app.strava_client import StravaClient


@pytest.fixture
def oauth():
    return SimpleNamespace(access_token="test-access", ensure_valid_token=Mock())


def test_api_failure_propagates_without_fabricated_data(monkeypatch, capsys, oauth):
    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.Timeout("timed out")))
    with pytest.raises(requests.RequestException):
        StravaClient(oauth).get_latest_workout()
    assert capsys.readouterr().out == ""


def test_strava_empty_is_success(monkeypatch, capsys, oauth):
    response = Mock()
    response.json.return_value = []
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    StravaClient(oauth).get_latest_workout()
    assert capsys.readouterr().out == "No Activity\n0m\n"
    assert get.call_args.kwargs["timeout"] == 30
    assert get.call_args.kwargs["params"] == {"per_page": 1}


@pytest.fixture
def manager(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key, value in {
        "CLIENT_ID": "id",
        "CLIENT_SECRET": "secret",
        "REDIRECT_URI": "https://localhost",
        "REFRESH_TOKEN": "refresh-secret",
    }.items():
        monkeypatch.setenv(f"STRAVA_{key}", value)
    return OAuthManager("strava")


def test_refresh_failure_does_not_log_credentials_or_write_artifact(monkeypatch, capsys, tmp_path, manager):
    response = Mock(status_code=400, text="refresh-secret")
    response.json.return_value = {"errors": [{"errorType": "invalid_grant", "message": "refresh-secret"}]}
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    assert manager.manage_tokens() is False
    assert not (tmp_path / "strava_tokens.json").exists()
    output = capsys.readouterr()
    assert "refresh-secret" not in output.out + output.err
    assert "invalid_grant" in output.err


def test_failed_refresh_stops_data_request(monkeypatch, manager):
    manager.expires_at = "0"
    monkeypatch.setattr(manager, "refresh_token", lambda: False)
    with pytest.raises(RuntimeError):
        manager.ensure_valid_token()


def test_refresh_success_retains_rotated_tokens(monkeypatch, tmp_path, manager):
    response = Mock(status_code=200)
    response.json.return_value = {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    assert manager.manage_tokens()
    assert "new-refresh" in (tmp_path / "strava_tokens.json").read_text()
    assert post.call_args.kwargs["timeout"] == 30


def test_strava_cli_refresh_failure_is_nonzero(monkeypatch):
    from app import strava

    monkeypatch.setattr(
        strava,
        "create_strava_client",
        lambda: SimpleNamespace(
            oauth=SimpleNamespace(
                manage_tokens=lambda: False,
                access_token="access",
                refresh_token_value="refresh",
                expires_at="0",
                is_token_expired=lambda: True,
            )
        ),
    )
    monkeypatch.setattr("sys.argv", ["strava", "strava-tokens"])
    with pytest.raises(SystemExit) as error:
        strava.main()
    assert error.value.code == 1


def test_profile_preserves_failed_service_and_fetches_workout_once(monkeypatch, tmp_path, capsys):
    failed_command = "google-health-summary"
    from app.profile import update_profile

    readme = tmp_path / "README.md"
    readme.write_text(
        "- <samp> 🚶🏼‍♂️ Today I have walked **old** steps and slept for **old** </samp><br>\n"
        "- <samp> 🏋🏼‍♂️ My last workout was **old** for **old** </samp><br>\nOther text\n"
    )
    calls = []

    def run(command, **kwargs):
        calls.append(command[-1])
        if command[-1] == failed_command:
            return subprocess.CompletedProcess(command, 1, "", "unavailable")
        data = {
            "google-health-summary": "123\n7h 12m\n",
            "strava-latest-workout": "Ride & | \\ trail\n1h 02m\n",
        }
        return subprocess.CompletedProcess(command, 0, data[command[-1]], "")

    monkeypatch.setattr(subprocess, "run", run)
    assert update_profile(readme) == 1
    result = readme.read_text()
    assert "**old** steps" in result
    assert "Last recorded: I walked **old** steps" in result
    assert "unavailable" not in result
    assert "Google Health update failed" in capsys.readouterr().err
    assert "Ride & | \\ trail" in result
    assert result.endswith("Other text\n")
    assert calls.count("strava-latest-workout") == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_strava_http_errors_propagate(monkeypatch, oauth, capsys, status):
    response = Mock(status_code=status)
    response.raise_for_status.side_effect = requests.HTTPError(response=response)
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    with pytest.raises(requests.HTTPError):
        StravaClient(oauth).get_latest_workout()
    assert capsys.readouterr().out == ""


def test_workout_name_newline_stays_on_one_line(monkeypatch, oauth, capsys):
    response = Mock()
    response.json.return_value = [{"name": "Ride\n& trail", "elapsed_time": 3720}]
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    StravaClient(oauth).get_latest_workout()
    assert capsys.readouterr().out == "Ride & trail\n1h 02m\n"


def test_profile_preserves_strava_and_recovers_stale_health(monkeypatch, tmp_path, capsys):
    from app.profile import update_profile

    path = tmp_path / "README.md"
    path.write_text(
        "- <samp> 🚶🏼‍♂️ Last recorded: I walked **old** steps and slept for **old** </samp><br>"
        " <sub>Update unavailable; previous data shown</sub>\n"
        "- <samp> 🏋🏼‍♂️ My last workout was **Ride** for **1h 02m** </samp><br>\n"
    )

    def run(command, **kwargs):
        data = {"google-health-summary": "123\n7h 12m\n"}
        cmd = command[-1]
        return subprocess.CompletedProcess(command, 0 if cmd in data else 1, data.get(cmd, ""), "")

    monkeypatch.setattr(subprocess, "run", run)
    assert update_profile(path) == 1
    assert "**123** steps" in path.read_text()
    assert "**Ride** for **1h 02m**" in path.read_text()
    assert "unavailable" not in path.read_text()
    assert "Strava update failed" in capsys.readouterr().err
    assert update_profile(path) == 1
    assert "unavailable" not in path.read_text()
    assert "Strava update failed" in capsys.readouterr().err


def test_unexpected_data_preserves_profile(monkeypatch, tmp_path):
    from app.profile import update_profile

    path = tmp_path / "README.md"
    path.write_text(
        "- <samp> 🚶🏼‍♂️ Today I have walked **99** steps and slept for **7h 0m** </samp><br>\n"
        "- <samp> 🏋🏼‍♂️ My last workout was **Ride** for **1h 02m** </samp><br>\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda command, **kw: subprocess.CompletedProcess(command, 0, "bad\n", ""))
    assert update_profile(path) == 1
    assert "**99** steps" in path.read_text()
    assert "**Ride** for **1h 02m**" in path.read_text()


def test_authentication_error_redacts_code(monkeypatch, capsys, manager):
    response = Mock(status_code=400)
    response.json.return_value = {"errors": [{"errorType": "invalid_grant", "message": "sensitive-code"}]}
    monkeypatch.setattr("app.oauth_manager.getpass", lambda _: "sensitive-code")
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    with pytest.raises(SystemExit):
        manager.authenticate()
    output = capsys.readouterr()
    assert "sensitive-code" not in output.out + output.err
    assert "invalid_grant" in output.err


@pytest.mark.parametrize("old_workout", ["My last workout was **No Activity** for **0m**", "No workouts yet."])
def test_workout_failure_preserves_recording_and_recovers(monkeypatch, tmp_path, old_workout):
    from app.profile import update_profile

    path = tmp_path / "README.md"
    path.write_text(
        "- <samp> 🚶🏼‍♂️ Today I have walked **1** steps and slept for **7h 0m** </samp><br>\n"
        f"- <samp> 🏋🏼‍♂️ {old_workout} </samp><br>\n"
    )
    failed = True

    def run(command, **kwargs):
        data = {"google-health-summary": "2\n7h 0m\n", "strava-latest-workout": "Ride\n45m\n"}
        error = failed and command[-1] == "strava-latest-workout"
        return subprocess.CompletedProcess(command, int(error), "" if error else data[command[-1]], "")

    monkeypatch.setattr(subprocess, "run", run)
    assert update_profile(path) == 1
    assert f"- <samp> 🏋🏼‍♂️ {old_workout} </samp><br>\n" in path.read_text()
    assert "unavailable" not in path.read_text()
    assert update_profile(path) == 1
    assert f"- <samp> 🏋🏼‍♂️ {old_workout} </samp><br>\n" in path.read_text()
    assert "unavailable" not in path.read_text()
    failed = False
    assert update_profile(path) == 0
    assert "**Ride** for **45m**" in path.read_text()
    assert "unavailable" not in path.read_text()


def test_empty_workout_profile_is_friendly(monkeypatch, tmp_path):
    from app.profile import update_profile

    path = tmp_path / "README.md"
    path.write_text(
        "- <samp> 🚶🏼‍♂️ Today I have walked **1** steps and slept for **7h 0m** </samp><br>\n"
        "- <samp> 🏋🏼‍♂️ Workouts unavailable. </samp><br>\n"
    )
    data = {"google-health-summary": "2\n7h 0m\n", "strava-latest-workout": "No Activity\n0m\n"}
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, data[cmd[-1]], ""))
    assert update_profile(path) == 0
    assert "No workouts yet." in path.read_text()
    assert "unavailable" not in path.read_text()
