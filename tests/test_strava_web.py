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
