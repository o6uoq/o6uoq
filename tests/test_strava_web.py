import pytest

from app.strava_web import StravaWebsiteError, workout_from_training


def test_training_uses_elapsed_seconds_and_normalises_name():
    payload = {
        "page": 1,
        "models": [
            {"name": "Lunch\nWorkout", "elapsed_time_raw": 3202, "moving_time_raw": 2000, "start_date_local_raw": 100}
        ],
        "total": 1,
    }
    assert workout_from_training(payload) == ("Lunch Workout", 3202)


def test_training_empty_is_success_only_when_total_is_zero():
    assert workout_from_training({"page": 1, "models": [], "total": 0}) == ("No Activity", 0)
    with pytest.raises(StravaWebsiteError):
        workout_from_training({"page": 1, "models": [], "total": 4})


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"models": None},
        {"models": [{"name": "Ride", "start_date_local_raw": 100}]},
        {"models": [{"name": "Ride", "start_date_local_raw": 100, "elapsed_time_raw": -1}]},
        {"models": [{"name": "Ride", "start_date_local_raw": 100, "elapsed_time_raw": True}]},
        {"models": [{"name": "", "elapsed_time_raw": 300, "start_date_local_raw": 100}]},
    ],
)
def test_invalid_training_data_fails_without_fabricating_workouts(payload):
    with pytest.raises(StravaWebsiteError):
        workout_from_training({"page": 1, **payload})


def test_browser_errors_never_expose_password(monkeypatch):
    from playwright.sync_api import Error as BrowserError

    from app import strava_web

    monkeypatch.setattr(strava_web, "load_dotenv", lambda: None)
    monkeypatch.setenv("STRAVA_LOGIN", "test@example.invalid")
    monkeypatch.setenv("STRAVA_PASSWORD", "private-test-password")

    def fail(**kwargs):
        raise BrowserError("Call log: private-test-password")

    monkeypatch.setattr(strava_web, "Camoufox", fail)
    with pytest.raises(StravaWebsiteError, match="browser startup") as error:
        strava_web.latest_workout()
    assert "private-test-password" not in str(error.value)


def test_cli_workout_uses_website_without_oauth(monkeypatch, capsys):
    from app import strava

    monkeypatch.setattr(strava, "latest_workout", lambda: ("Lunch Workout", 3202))

    def fail():
        raise AssertionError("OAuth must not be required for website workouts")

    monkeypatch.setattr(strava, "create_strava_client", fail)
    monkeypatch.setattr("sys.argv", ["strava", "strava-latest-workout"])
    strava.main()
    assert capsys.readouterr().out == "Lunch Workout\n53m\n"


@pytest.mark.parametrize("page,dates", [(2, [200, 100]), (1, [100, 200])])
def test_activity_pagination_or_sort_changes_do_not_publish_an_old_workout(page, dates):
    models = [{"name": "Ride", "elapsed_time_raw": 300, "start_date_local_raw": date} for date in dates]
    with pytest.raises(StravaWebsiteError):
        workout_from_training({"page": page, "models": models, "total": 2})


@pytest.mark.parametrize("elapsed,duration", [(3202, "53m"), (3722, "1h 02m")])
def test_website_preserves_original_api_and_profile_format(monkeypatch, capsys, tmp_path, elapsed, duration):
    from unittest.mock import Mock

    from app import profile, strava
    from app.strava_client import StravaClient

    response = Mock()
    response.json.return_value = [{"name": "Lunch Workout", "elapsed_time": elapsed}]
    monkeypatch.setattr("requests.get", Mock(return_value=response))
    StravaClient(Mock()).get_latest_workout()
    original_output = capsys.readouterr().out
    monkeypatch.setattr(strava, "latest_workout", lambda: ("Lunch Workout", elapsed))
    monkeypatch.setattr("sys.argv", ["strava", "strava-latest-workout"])
    strava.main()
    assert capsys.readouterr().out == original_output == f"Lunch Workout\n{duration}\n"
    monkeypatch.setattr(
        profile,
        "fetch",
        lambda module, command: {
            "fitbit-steps": ["282"],
            "fitbit-sleep": ["4h 53m"],
            "strava-latest-workout": original_output.splitlines(),
        }[command],
    )
    readme = tmp_path / "README.md"
    fitbit_line = "- <samp> 🚶🏼‍♂️ Today I have walked **282** steps and slept for **4h 53m** </samp><br>\n"
    readme.write_text(fitbit_line + "- <samp> 🏋🏼‍♂️ Workouts unavailable. </samp><br>\n")
    assert profile.update_profile(readme) == 0
    assert readme.read_text() == (
        fitbit_line + f"- <samp> 🏋🏼‍♂️ My last workout was **Lunch Workout** for **{duration}** </samp><br>\n"
    )


@pytest.mark.parametrize(
    "failure_stage,error_kind,requested,status",
    [
        ("password form submission", "timeout", False, None),
        ("login response", "timeout", True, None),
        ("login response", "browser error", True, 503),
    ],
)
def test_login_failures_report_safe_stage_and_network_metadata(
    monkeypatch, failure_stage, error_kind, requested, status
):
    from unittest.mock import MagicMock, Mock

    from playwright.sync_api import Error as BrowserError
    from playwright.sync_api import TimeoutError as BrowserTimeout

    from app import strava_web

    monkeypatch.setattr(strava_web, "load_dotenv", lambda: None)
    monkeypatch.setenv("STRAVA_LOGIN", "private-login@example.invalid")
    monkeypatch.setenv("STRAVA_PASSWORD", "private-test-password")
    clock = iter([100.0, 100.0, 112.5])
    monkeypatch.setattr(strava_web.time, "monotonic", lambda: next(clock))
    page = MagicMock()
    page.evaluate.return_value = True
    callbacks = {}
    page.on.side_effect = lambda event, callback: callbacks.update({event: callback})
    browser = MagicMock()
    browser.__enter__.return_value.new_page.return_value = page
    monkeypatch.setattr(strava_web, "Camoufox", lambda **kwargs: browser)
    failure = (BrowserTimeout if error_kind == "timeout" else BrowserError)(
        "Call log: private-login@example.invalid private-test-password"
    )

    def click():
        if requested:
            callbacks["request"](Mock(method="POST", url="https://www.strava.com/session?private-test-password"))
        if status is not None:
            callbacks["response"](
                Mock(request=Mock(method="POST", url="https://www.strava.com/session"), status=status)
            )
        if failure_stage == "password form submission":
            raise failure

    button = page.locator.return_value.locator.return_value.locator.return_value
    button.count.return_value = 1
    button.is_visible.return_value = True
    button.is_enabled.return_value = False
    button.click.side_effect = click
    if failure_stage == "login response":
        page.expect_response.return_value.__exit__.side_effect = failure
    with pytest.raises(StravaWebsiteError) as caught:
        strava_web.latest_workout()
    message = str(caught.value)
    assert f"{error_kind} during {failure_stage}" in message
    assert "after 12.5s" in message
    assert f"session requested: {'yes' if requested else 'no'}" in message
    assert f"session HTTP: {status if status is not None else 'none'}" in message
    assert "private-test-password" not in message
    assert "private-login" not in message
    assert caught.value.__suppress_context__
    assert f"submit: {'disabled' if failure_stage == 'password form submission' else 'unknown'}" in message


@pytest.mark.parametrize("login_status", [200, 403])
def test_website_fetch_preserves_success_and_reports_rejection(monkeypatch, login_status):
    from unittest.mock import MagicMock, Mock

    from app import strava_web

    monkeypatch.setattr(strava_web, "load_dotenv", lambda: None)
    monkeypatch.setenv("STRAVA_LOGIN", "test@example.invalid")
    monkeypatch.setenv("STRAVA_PASSWORD", "private-test-password")
    page = MagicMock()
    page.evaluate.return_value = True
    browser = MagicMock()
    browser.__enter__.return_value.new_page.return_value = page
    monkeypatch.setattr(strava_web, "Camoufox", lambda **kwargs: browser)
    login = Mock(status=login_status)
    login.header_value.return_value = "application/json"
    login.body.return_value = b'{"details":{"msg":"auth005"},"private":"private-test-password"}'
    login.json.return_value = {"success": True}
    activities = Mock(status=200)
    activities.json.return_value = {
        "page": 1,
        "models": [{"name": "Morning Workout", "elapsed_time_raw": 2880, "start_date_local_raw": 100}],
        "total": 1,
    }
    responses = []
    for response in (login, activities):
        context = MagicMock()
        context.__enter__.return_value.value = response
        responses.append(context)
    page.expect_response.side_effect = responses
    if login_status == 200:
        assert strava_web.latest_workout() == ("Morning Workout", 2880)
    else:
        with pytest.raises(StravaWebsiteError) as caught:
            strava_web.latest_workout()
        assert str(caught.value) == "Strava login returned HTTP 403 (response: json; reason: trust)"
        assert "private-test-password" not in str(caught.value)
        page.goto.assert_called_once()


@pytest.mark.parametrize(
    "method,url,expected",
    [
        ("POST", "https://www.strava.com/session", True),
        ("GET", "https://www.strava.com/session", False),
        ("POST", "https://other.invalid/session", False),
        ("POST", "http://www.strava.com/session", False),
        ("POST", "https://www.strava.com/session/other", False),
    ],
)
def test_login_request_matching_is_specific(method, url, expected):
    from unittest.mock import Mock

    from app.strava_web import is_login_request

    assert is_login_request(Mock(method=method, url=url)) is expected


@pytest.mark.parametrize(
    "code,reason",
    [
        ("auth002", "recaptcha_score"),
        ("auth003", "honey_pot"),
        ("auth004", "rate_limiting"),
        ("auth005", "trust"),
        ("auth013", "expired_session"),
        ("auth015", "invalid_credentials"),
        ("auth016", "otp_state_missing"),
    ],
)
def test_login_rejection_reports_only_known_categories(code, reason):
    import json
    from unittest.mock import Mock

    from app.strava_web import login_response_diagnostics

    response = Mock()
    response.header_value.return_value = "application/json; charset=utf-8"
    response.body.return_value = json.dumps({"details": {"msg": code}, "private": "private-password"}).encode()
    assert login_response_diagnostics(response) == f"response: json; reason: {reason}"


@pytest.mark.parametrize(
    "body",
    [
        b'{"details":{"msg":"private-password"}}',
        b'{"details":{"msg":["auth002"]}}',
        b'{"details":"private-password"}',
        b"[]",
        b"null",
        b"not JSON private-password",
        b"\xff",
        b"x" * 16385,
    ],
)
def test_unknown_or_invalid_login_payload_never_exposes_content(body):
    from unittest.mock import Mock

    from app.strava_web import login_response_diagnostics

    response = Mock()
    response.header_value.return_value = "application/json"
    response.body.return_value = body
    assert login_response_diagnostics(response) == "response: json; reason: unknown"


@pytest.mark.parametrize(
    "content_type,format_name",
    [
        ("text/html; charset=utf-8", "html"),
        ("text/plain private-password", "other"),
        (None, "unknown"),
    ],
)
def test_non_json_response_does_not_read_or_label_body_as_bot_block(content_type, format_name):
    from unittest.mock import Mock

    from app.strava_web import login_response_diagnostics

    response = Mock()
    response.header_value.return_value = content_type
    assert login_response_diagnostics(response) == f"response: {format_name}; reason: unknown"
    response.body.assert_not_called()


@pytest.mark.parametrize("failed_read", ["header_value", "body"])
def test_login_response_read_errors_preserve_safe_diagnostics(failed_read):
    from unittest.mock import Mock

    from playwright.sync_api import Error as BrowserError

    from app.strava_web import login_response_diagnostics

    response = Mock()
    response.header_value.return_value = "application/json"
    getattr(response, failed_read).side_effect = BrowserError("private-password")
    expected = "unknown" if failed_read == "header_value" else "json"
    assert login_response_diagnostics(response) == f"response: {expected}; reason: unknown"


@pytest.mark.parametrize(
    "count,visible,enabled,state",
    [
        (0, False, False, "missing"),
        (2, True, True, "ambiguous"),
        (1, False, False, "hidden"),
        (1, True, False, "disabled"),
        (1, True, True, "enabled"),
    ],
)
def test_failed_submit_button_state_uses_fixed_labels(count, visible, enabled, state):
    from unittest.mock import Mock

    from app.strava_web import submit_button_state

    button = Mock()
    button.count.return_value = count
    button.is_visible.return_value = visible
    button.is_enabled.return_value = enabled
    assert submit_button_state(button) == state


def test_submit_button_read_error_is_safe():
    from unittest.mock import Mock

    from playwright.sync_api import Error as BrowserError

    from app.strava_web import submit_button_state

    button = Mock()
    button.count.side_effect = BrowserError("private-password")
    assert submit_button_state(button) == "unknown"
