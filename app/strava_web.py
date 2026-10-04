"""Read the signed-in athlete's newest workout through Strava's website."""

import os
import time
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from camoufox.sync_api import Camoufox
from dotenv import load_dotenv
from playwright.sync_api import Error as BrowserError
from playwright.sync_api import TimeoutError as BrowserTimeout


class StravaWebsiteError(RuntimeError):
    """Safe website diagnostics without browser call logs or credentials."""


def workout_from_training(payload: dict) -> tuple[str, int]:
    if not isinstance(payload, dict) or type(payload.get("page")) is not int or payload["page"] != 1:
        raise StravaWebsiteError("Strava did not return the first activity page")
    models = payload.get("models")
    if not isinstance(models, list):
        raise StravaWebsiteError("Strava returned an invalid activity list")
    if not models:
        if payload.get("total") == 0:
            return "No Activity", 0
        raise StravaWebsiteError("Strava returned an incomplete activity list")
    dates: list[int] = []
    for model in models:
        date = model.get("start_date_local_raw") if isinstance(model, dict) else None
        if isinstance(date, bool) or not isinstance(date, int):
            raise StravaWebsiteError("Strava activity is missing its date")
        dates.append(date)
    if dates != sorted(dates, reverse=True):
        raise StravaWebsiteError("Strava activities are not ordered newest first")
    latest = models[0]
    if not isinstance(latest, dict):
        raise StravaWebsiteError("Strava returned an invalid activity")
    name, elapsed = latest.get("name"), latest.get("elapsed_time_raw")
    if not isinstance(name, str) or not name.strip():
        raise StravaWebsiteError("Strava activity is missing its name")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0:
        raise StravaWebsiteError("Strava activity is missing elapsed seconds")
    if isinstance(elapsed, float) and not elapsed.is_integer():
        raise StravaWebsiteError("Strava activity has invalid elapsed seconds")
    return " ".join(name.splitlines()).strip(), int(elapsed)


def latest_workout() -> tuple[str, int]:
    load_dotenv()
    login, password = os.environ.get("STRAVA_LOGIN"), os.environ.get("STRAVA_PASSWORD")
    if not login or not password:
        raise StravaWebsiteError("Set STRAVA_LOGIN and STRAVA_PASSWORD")
    stage = "browser startup"
    try:
        with (
            TemporaryDirectory(prefix="strava-") as profile,
            Camoufox(
                browser="156.0.1-beta.34",
                headless="virtual",
                humanize=True,
                os="linux",
                locale="en-GB",
                timezone_id="Europe/London",
                main_world_eval=True,
                persistent_context=True,
                user_data_dir=profile,
            ) as context,
        ):
            page = context.new_page()
            page.set_default_timeout(25000)
            stage = "login page"
            page.goto("https://www.strava.com/login", wait_until="domcontentloaded", timeout=60000)
            try:
                page.get_by_role("button", name="Reject Non-Essential", exact=True).click(timeout=10000)
            except BrowserTimeout:
                pass
            stage = "login readiness"
            deadline = time.monotonic() + 25
            while not page.evaluate("mw:() => !!window.grecaptcha?.enterprise?.execute"):
                if time.monotonic() > deadline:
                    raise StravaWebsiteError("Strava reCAPTCHA did not initialise")
                page.wait_for_timeout(100)
            page.wait_for_function(
                '() => !!document.head.querySelector("meta[name=csrf],meta[name=csrf-token]")?.content'
            )
            stage = "password form"
            page.locator("input[type=email]:visible").press_sequentially(login, delay=90)
            # Select the site's bundled password form without sending an email-code request.
            # Camoufox requires main-world execution to access the React provider.
            switched = page.evaluate("""mw:() => {
                const el = document.querySelector('#desktop-email');
                let f = el?.[Object.keys(el).find(k => k.startsWith('__reactFiber$'))];
                while (f) {
                    const value = f.memoizedProps?.value;
                    if (value?.state?.emailFormData && typeof value.dispatch === 'function') {
                        value.dispatch({type:'UPDATE_EMAIL_FORM_DATA',payload:{usePassword:true}});
                        value.dispatch({type:'UPDATE_ACCESS_CONTEXT',payload:{accessContext:'needs_auth_password_login'}});
                        value.dispatch({type:'UPDATE_STEP',payload:{step:1}});
                        return true;
                    }
                    f = f.return;
                }
                return false;
            }""")
            if not switched:
                raise StravaWebsiteError("Strava login layout changed")
            field = page.locator("input[type=password]:visible")
            field.press_sequentially(password, delay=90)
            stage = "password submission"
            with page.expect_response(lambda r: urlsplit(r.url).path == "/session") as submitted:
                field.locator("xpath=ancestor::form").locator("button[type=submit]").click()
            response = submitted.value
            if response.status != 200:
                raise StravaWebsiteError(f"Strava login returned HTTP {response.status}")
            accepted = response.json()
            if not isinstance(accepted, dict) or accepted.get("success") is not True:
                raise StravaWebsiteError("Strava did not accept the login")
            stage = "own activities"
            page.locator('a[href="/athlete/training"]').first.wait_for(state="attached")
            with page.expect_response(lambda r: urlsplit(r.url).path == "/athlete/training_activities") as loaded:
                page.goto("https://www.strava.com/athlete/training", wait_until="domcontentloaded")
            activities = loaded.value
            if activities.status != 200:
                raise StravaWebsiteError(f"Strava activities returned HTTP {activities.status}")
            return workout_from_training(activities.json())
    except BrowserError:
        # Playwright exceptions can include the values entered into form fields.
        raise StravaWebsiteError(f"Strava website failed during {stage}") from None
