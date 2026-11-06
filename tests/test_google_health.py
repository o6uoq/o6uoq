import json
from datetime import date
from unittest.mock import Mock

import pytest
import requests

from app.google_health import GoogleHealthClient, GoogleHealthError

DAY = date(2026, 11, 6)


def response(payload, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    result.headers["content-type"] = "application/json"
    return result


def rollup(count="123"):
    return {
        "rollupDataPoints": [
            {
                "civilStartTime": {"date": {"year": 2026, "month": 11, "day": 6}, "time": {}},
                "civilEndTime": {"date": {"year": 2026, "month": 11, "day": 7}, "time": {"hours": 0}},
                "steps": {"countSum": count},
            }
        ]
    }


@pytest.fixture
def client(monkeypatch):
    session = Mock()
    monkeypatch.setattr(requests, "Session", lambda: session)
    instance = GoogleHealthClient("client-id", "client-secret", "refresh-private")
    return instance, session


def replies(session, *payloads):
    session.request.side_effect = [response({"access_token": "access-private", "expires_in": 3600})] + [
        response(payload) for payload in payloads
    ]


def test_daily_rollup_and_paginated_reconciled_sleep(client):
    instance, session = client
    replies(
        session,
        rollup("0"),
        {"dataPoints": [{"sleep": {"summary": {"minutesAsleep": "455"}}}], "nextPageToken": "next"},
        {"dataPoints": [{"sleep": {"summary": {"minutesAsleep": "17"}}}]},
    )
    assert instance.summary(DAY) == (0, "7h 52m")
    calls = session.request.call_args_list
    assert len(calls) == 4
    assert calls[0].args[1] == "https://oauth2.googleapis.com/token"
    assert calls[0].kwargs["timeout"] == 30
    assert calls[1].args == ("POST", "https://health.googleapis.com/v4/users/me/dataTypes/steps/dataPoints:dailyRollUp")
    assert calls[1].kwargs["json"] == {
        "range": {
            "start": {"date": {"year": 2026, "month": 11, "day": 6}},
            "end": {"date": {"year": 2026, "month": 11, "day": 7}},
        },
        "windowSizeDays": 1,
    }
    expected_filter = 'sleep.interval.civil_end_time >= "2026-11-06" AND sleep.interval.civil_end_time < "2026-11-07"'
    assert calls[2].kwargs["params"] == {"filter": expected_filter, "pageSize": 25}
    assert calls[3].kwargs["params"] == {"filter": expected_filter, "pageSize": 25, "pageToken": "next"}
    assert calls[1].kwargs["headers"]["Authorization"] == "Bearer access-private"
    assert calls[1].kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"rollupDataPoints": []},
        {"rollupDataPoints": [{}]},
        rollup("-1"),
        rollup(True),
        rollup("1.5"),
    ],
)
def test_unobserved_or_invalid_steps_do_not_become_zero(client, payload):
    instance, session = client
    replies(session, payload)
    with pytest.raises(GoogleHealthError):
        instance.summary(DAY)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"dataPoints": []},
        {"dataPoints": [{"sleep": {"summary": {}}}]},
    ],
)
def test_missing_sleep_does_not_become_zero(client, payload):
    instance, session = client
    replies(session, rollup(), payload)
    with pytest.raises(GoogleHealthError):
        instance.summary(DAY)


def test_http_error_redacts_provider_body(client):
    instance, session = client
    session.request.side_effect = [
        response({"access_token": "access-private", "expires_in": 3600}),
        response({"error": {"message": "access-private"}}, 403),
    ]
    with pytest.raises(GoogleHealthError, match="HTTP 403") as error:
        instance.summary(DAY)
    assert "access-private" not in str(error.value)


def test_refresh_error_redacts_provider_body(client):
    instance, session = client
    session.request.return_value = response({"error": "invalid_grant", "error_description": "refresh-private"}, 400)
    with pytest.raises(GoogleHealthError, match="token refresh failed") as error:
        instance.summary(DAY)
    assert "refresh-private" not in str(error.value)
    assert session.request.call_count == 1


@pytest.mark.parametrize(
    "observed",
    [
        {"date": {"year": 2026, "month": 11, "day": 5}},
        {"date": {"year": 2026, "month": 11, "day": 6}, "time": {"hours": 1}},
    ],
)
def test_wrong_date_or_partial_day_is_not_published(client, observed):
    instance, session = client
    payload = rollup()
    payload["rollupDataPoints"][0]["civilStartTime"] = observed
    replies(session, payload)
    with pytest.raises(GoogleHealthError, match="date range"):
        instance.summary(DAY)


@pytest.mark.parametrize("unavailable", [False, True])
def test_setup_checks_access_before_setting_secrets(monkeypatch, tmp_path, capsys, unavailable):
    import subprocess

    from scripts import configure_google_health as setup

    registration = tmp_path / "client.json"
    registration.write_text(json.dumps({"web": {"client_id": "client-id", "client_secret": "client-private"}}))
    monkeypatch.setattr("sys.argv", ["setup", str(registration)])
    monkeypatch.setattr(setup, "getpass", lambda prompt: "refresh-private")
    fake_client = Mock()
    fake_client.request.return_value = {"healthUserId": "user-id"}
    fake_client.summary.return_value = (123, "7h 52m")
    if unavailable:
        fake_client.summary.side_effect = GoogleHealthError("Google Health request returned HTTP 403")
    monkeypatch.setattr(setup, "GoogleHealthClient", Mock(return_value=fake_client))
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(subprocess, "run", run)
    if unavailable:
        with pytest.raises(SystemExit) as error:
            setup.main()
        assert error.value.code == 1
        assert run.call_count == 1
    else:
        setup.main()
        calls = run.call_args_list[1:]
        assert [call.kwargs["input"] for call in calls] == ["client-id", "client-private", "refresh-private"]
        assert [call.args[0][3] for call in calls] == [
            "GOOGLE_HEALTH_CLIENT_ID",
            "GOOGLE_HEALTH_CLIENT_SECRET",
            "GOOGLE_HEALTH_REFRESH_TOKEN",
        ]
        assert all("refresh-private" not in call.args[0] for call in calls)
    output = capsys.readouterr()
    assert "refresh-private" not in output.out + output.err
    assert "client-private" not in output.out + output.err


def test_setup_stops_if_hidden_input_is_unavailable(monkeypatch, tmp_path, capsys):
    import warnings
    from getpass import GetPassWarning

    from scripts import configure_google_health as setup

    registration = tmp_path / "client.json"
    registration.write_text(json.dumps({"web": {"client_id": "id", "client_secret": "client-private"}}))
    monkeypatch.setattr("sys.argv", ["setup", str(registration)])
    run = Mock()
    monkeypatch.setattr(setup.subprocess, "run", run)

    def unsafe_prompt(prompt):
        warnings.warn("Cannot disable echo", GetPassWarning)
        pytest.fail("Must stop before falling back to echoed input")

    monkeypatch.setattr(setup, "getpass", unsafe_prompt)
    with pytest.raises(SystemExit) as error:
        setup.main()
    assert error.value.code == 1
    assert run.call_count == 1
    assert "interactive terminal" in capsys.readouterr().err
