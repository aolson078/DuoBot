import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from getpass import getpass
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException


STORIES_URL = "https://www.duolingo.com/stories"


@dataclass
class BotConfig:
    chrome_user_data_dir: str
    chrome_profile_name: str = "Default"
    headless: bool = False
    story_path: Optional[str] = None  # e.g. "/en/es-juan-1" or full URL
    max_steps: int = 200
    wait_secs: int = 20
    username: Optional[str] = None
    password: Optional[str] = None


def _options_from_config(cfg: BotConfig) -> ChromeOptions:
    options = ChromeOptions()
    # Use installed Chrome and your real profile so you're already logged in
    options.add_argument(f"--user-data-dir={cfg.chrome_user_data_dir}")
    options.add_argument(f"--profile-directory={cfg.chrome_profile_name}")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,1000")
    if cfg.headless:
        options.add_argument("--headless=new")
    return options


def _click_first(driver, selectors: List[str]) -> bool:
    for css in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, css)
            el.click()
            return True
        except Exception:
            continue
    return False


def _click_any_by_text(driver, texts: List[str]) -> bool:
    # Try multiple strategies: data-test buttons, role=button, text match
    xpaths = []
    for t in texts:
        t_norm = t.strip()
        xpaths.extend(
            [
                f"//button[normalize-space()='{t_norm}']",
                f"//button[contains(normalize-space(), '{t_norm}')]",
                f"//*[@role='button' and normalize-space()='{t_norm}']",
                f"//*[@role='button' and contains(normalize-space(), '{t_norm}')]",
            ]
        )
    for xp in xpaths:
        try:
            el = driver.find_element(By.XPATH, xp)
            el.click()
            return True
        except Exception:
            continue
    return False


def _safe_click(driver, element) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        element.click()
        return True
    except ElementClickInterceptedException:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False
    except Exception:
        return False


def _tap_all_tokens(driver) -> bool:
    # Stories often have tap-to-complete sentences; select all tokens
    token_selectors = [
        "[data-test='challenge-tap-token']",
        "[data-test='word-bank'] [role='button']",
        "[data-test*='challenge'] [data-test*='token']",
    ]
    clicked = False
    for sel in token_selectors:
        try:
            tokens = driver.find_elements(By.CSS_SELECTOR, sel)
            if len(tokens) >= 2:
                for token in tokens:
                    _safe_click(driver, token)
                    time.sleep(0.05)
                clicked = True
        except Exception:
            continue
    return clicked


def _answer_multiple_choice(driver) -> bool:
    choice_selectors = [
        "[data-test='challenge-choice']",
        "[data-test='challenge-judge-text']",
        "[data-test*='challenge'] [role='radio']",
        "[data-test*='challenge'] [data-test*='option']",
    ]
    for sel in choice_selectors:
        try:
            choices = driver.find_elements(By.CSS_SELECTOR, sel)
            if choices:
                random.choice(choices).click()
                return True
        except Exception:
            continue
    return False


def _fill_text_input(driver) -> bool:
    input_selectors = [
        "[data-test='challenge-text-input'] textarea",
        "[data-test='challenge-text-input'] input",
        "textarea",
        "input[type='text']",
    ]
    for sel in input_selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            el.clear()
            el.send_keys("a")
            el.send_keys(Keys.ENTER)
            return True
        except Exception:
            continue
    return False


def _find_first(driver, selectors: List[str]):
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el:
                return el
        except Exception:
            continue
    return None


def _has_session_cookie(driver) -> bool:
    try:
        cookie = driver.get_cookie("jwt_token")
        return bool(cookie and cookie.get("value"))
    except Exception:
        return False


def _prompt_for_credentials(cfg: BotConfig) -> Tuple[str, str]:
    username = cfg.username
    password = cfg.password
    if not username:
        username = input("Duolingo username or email: ").strip()
    if not password:
        password = getpass("Duolingo password: ")
    if not username or not password:
        raise RuntimeError("Duolingo credentials are required to log in automatically.")
    return username, password


def _ensure_logged_in(driver, wait, cfg: BotConfig) -> None:
    if _has_session_cookie(driver):
        return

    username, password = _prompt_for_credentials(cfg)

    login_url = "https://www.duolingo.com/log-in"
    driver.get(login_url)

    def _wait_for_form(d):
        return _find_first(
            d,
            [
                "[data-test='email-input'] input",
                "[data-test='email-input']",
                "input[name='identifier']",
                "input[name='login']",
                "input[name='email']",
                "input[name='username']",
                "input[type='email']",
                "input[autocomplete='username']",
            ],
        )

    try:
        email_input = wait.until(_wait_for_form)
    except TimeoutException as exc:
        raise RuntimeError("Could not load Duolingo login form.") from exc

    try:
        password_input = wait.until(
            lambda d: _find_first(
                d,
                [
                    "[data-test='password-input'] input",
                    "[data-test='password-input']",
                    "input[name='password']",
                    "input[type='password']",
                    "input[autocomplete='current-password']",
                ],
            )
        )
    except TimeoutException as exc:
        raise RuntimeError("Could not locate the password input on Duolingo.") from exc

    email_input.clear()
    email_input.send_keys(username)

    password_input.clear()
    password_input.send_keys(password)

    login_clicked = False
    login_selectors = [
        "button[data-test='register-button']",
        "button[data-test='login-button']",
        "button[data-test='have-account']",
        "button[type='submit']",
        "[data-test='confirm-button']",
    ]
    for sel in login_selectors:
        btn = driver.find_elements(By.CSS_SELECTOR, sel)
        if btn:
            if _safe_click(driver, btn[0]):
                login_clicked = True
                break

    if not login_clicked:
        password_input.send_keys(Keys.ENTER)

    try:
        wait.until(lambda d: _has_session_cookie(d))
    except TimeoutException as exc:
        raise RuntimeError("Failed to log into Duolingo automatically.") from exc


def run_story(cfg: BotConfig) -> None:
    options = _options_from_config(cfg)
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, cfg.wait_secs)

    try:
        # Load Duolingo homepage to establish a session/login first
        driver.get("https://www.duolingo.com/")
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except TimeoutException:
            raise RuntimeError("Duolingo homepage failed to load")

        _ensure_logged_in(driver, wait, cfg)

        target_url = (
            cfg.story_path
            if (cfg.story_path and cfg.story_path.startswith("http"))
            else (STORIES_URL + cfg.story_path if cfg.story_path else STORIES_URL)
        )
        driver.get(target_url)

        # Ensure we're logged in (assumes profile is logged in)
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except TimeoutException:
            raise RuntimeError("Page failed to load")

        # If on stories grid, open the first available story card
        if STORIES_URL in driver.current_url and not cfg.story_path:
            # Click first story card
            story_card_selectors = [
                "[data-test='story-card']",
                "a[href*='/stories/']",
                "[data-test*='story']",
            ]
            opened = False
            for sel in story_card_selectors:
                try:
                    cards = wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, sel))
                    if cards:
                        _safe_click(driver, cards[0])
                        opened = True
                        break
                except Exception:
                    continue
            if not opened:
                raise RuntimeError("Could not find a story to open")

        # In story player: loop actions until finished or step cap
        steps = 0
        while steps < cfg.max_steps:
            steps += 1
            time.sleep(0.5)

            # Common continue/next/check buttons
            button_clicked = _click_first(
                driver,
                [
                    "[data-test='stories-player-continue']",
                    "[data-test='stories-player-cta']",
                    "[data-test='player-continue']",
                    "button[data-test*='continue']",
                    "button[data-test*='check']",
                ],
            )
            if not button_clicked:
                button_clicked = _click_any_by_text(
                    driver,
                    [
                        "Start",
                        "Continue",
                        "Next",
                        "Check",
                        "Skip",
                        "Got it",
                        "Keep going",
                        "Done",
                    ],
                )

            if button_clicked:
                continue

            # Try answering question types
            acted = False
            acted = _tap_all_tokens(driver) or acted
            acted = _answer_multiple_choice(driver) or acted
            acted = _fill_text_input(driver) or acted

            if acted:
                # After acting, try to click check/continue
                _click_first(
                    driver,
                    [
                        "button[data-test*='check']",
                        "[data-test='stories-player-continue']",
                        "button[type='submit']",
                    ],
                )
                continue

            # Detect end of story or celebration modal
            try:
                celebration = driver.find_elements(By.CSS_SELECTOR, "[data-test*='streak']")
                finished = driver.find_elements(By.CSS_SELECTOR, "[data-test*='finished']")
                if celebration or finished:
                    break
            except Exception:
                pass

            # If nothing matched, try a generic next
            _click_any_by_text(driver, ["Continue", "Next", "Done"]) or time.sleep(0.5)

        # Small cooldown before exit
        time.sleep(1.5)
    finally:
        driver.quit()


def parse_args() -> BotConfig:
    parser = argparse.ArgumentParser(description="Auto-complete a Duolingo story to keep streak alive.")
    parser.add_argument(
        "--chrome-user-data-dir",
        required=False,
        default=os.path.expandvars(r"%LOCALAPPDATA%\\Google\\Chrome\\User Data"),
        help="Path to Chrome user data dir (so your session cookies are used)",
    )
    parser.add_argument(
        "--chrome-profile-name",
        required=False,
        default="Default",
        help="Chrome profile directory name (e.g. 'Default', 'Profile 1')",
    )
    parser.add_argument(
        "--story-path",
        required=False,
        default=None,
        help="Optional stories path or full URL (e.g. '/en/es-juan-1' or full URL)",
    )
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--wait-secs", type=int, default=20)
    parser.add_argument("--username", required=False, default=None, help="Duolingo username or email")
    parser.add_argument(
        "--password",
        required=False,
        default=None,
        help="Duolingo password (leave empty to be prompted securely)",
    )
    parser.add_argument(
        "--config",
        help="Path to JSON config with the same keys as CLI flags",
        required=False,
    )

    args = parser.parse_args()

    cfg = {}
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    def pick(key, default):
        return cfg.get(key, getattr(args, key.replace("-", "_"), default))

    return BotConfig(
        chrome_user_data_dir=pick("chrome_user_data_dir", os.path.expandvars(r"%LOCALAPPDATA%\\Google\\Chrome\\User Data")),
        chrome_profile_name=pick("chrome_profile_name", "Default"),
        headless=bool(pick("headless", False)),
        story_path=pick("story_path", None),
        max_steps=int(pick("max_steps", 200)),
        wait_secs=int(pick("wait_secs", 20)),
        username=pick("username", None),
        password=pick("password", None),
    )


def main() -> int:
    cfg = parse_args()
    run_story(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())


