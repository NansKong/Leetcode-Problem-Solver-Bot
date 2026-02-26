import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.common.exceptions import TimeoutException, WebDriverException

logger = logging.getLogger(__name__)


class LeetCodeNavigator:
    """
    Manages browser automation for LeetCode.

    Usage:
        navigator = LeetCodeNavigator(config)
        url = navigator.get_problem_url(1)
        navigator.close()
    """

    def __init__(self, config):
        self.config  = config
        self.driver  = self._init_driver()
        self.wait    = WebDriverWait(self.driver, config.browser_timeout)
        self._authenticate()

    # ── Driver Initialization ──────────────────────────────────────────

    def _init_driver(self) -> webdriver.Chrome:
        """Initialize Chrome/Firefox WebDriver with optimal settings."""
        if self.config.browser == "chrome":
            return self._init_chrome()
        elif self.config.browser == "firefox":
            return self._init_firefox()
        else:
            raise ValueError(f"Unsupported browser: {self.config.browser}")

    def _init_chrome(self) -> webdriver.Chrome:
        opts = ChromeOptions()
        if self.config.headless:
            opts.add_argument("--headless=new")        # New headless mode
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(options=opts)
        # Mask automation flags (anti-bot detection bypass)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return driver

    def _init_firefox(self) -> webdriver.Firefox:
        opts = FirefoxOptions()
        if self.config.headless:
            opts.add_argument("--headless")
        return webdriver.Firefox(options=opts)

    # ── Authentication ─────────────────────────────────────────────────

    def _authenticate(self):
        """
        Authenticate with LeetCode.
        Prefers session cookie injection (faster, more stable) over
        form-based login which can trigger CAPTCHA.
        """
        if self.config.leetcode_session:
            self._login_via_session_cookie()
        elif self.config.leetcode_username:
            self._login_via_form()
        else:
            logger.warning("No credentials provided — proceeding unauthenticated")

    def _login_via_session_cookie(self):
        """
        Inject LEETCODE_SESSION and csrftoken cookies directly.
        This is the recommended approach to avoid bot detection.

        How to get these values:
          1. Log into leetcode.com in your browser
          2. Open DevTools → Application → Cookies → leetcode.com
          3. Copy LEETCODE_SESSION and csrftoken values to .env
        """
        logger.info("Authenticating via session cookie...")
        # Must visit domain before setting cookies
        self.driver.get(self.config.leetcode_base_url)
        time.sleep(2)

        self.driver.add_cookie({
            "name": "LEETCODE_SESSION",
            "value": self.config.leetcode_session,
            "domain": ".leetcode.com"
        })
        if self.config.leetcode_csrf_token:
            self.driver.add_cookie({
                "name": "csrftoken",
                "value": self.config.leetcode_csrf_token,
                "domain": ".leetcode.com"
            })
        self.driver.refresh()
        logger.info("Session cookie authentication complete")

    def _login_via_form(self):
        """
        Form-based login using username and password.
        Note: May trigger CAPTCHA on suspicious activity.
        """
        logger.info("Authenticating via login form...")
        self.driver.get(f"{self.config.leetcode_base_url}/accounts/login/")
        time.sleep(2)

        try:
            username_field = self.wait.until(
                EC.presence_of_element_located((By.ID, "id_login"))
            )
            username_field.send_keys(self.config.leetcode_username)

            password_field = self.driver.find_element(By.ID, "id_password")
            password_field.send_keys(self.config.leetcode_password)

            # Click sign-in button
            self.driver.find_element(By.ID, "signin_btn").click()
            time.sleep(3)

            # Verify login success
            if "login" in self.driver.current_url:
                raise RuntimeError("Login failed — check credentials or CAPTCHA")
            logger.info("Form login successful")

        except TimeoutException:
            raise RuntimeError("Login page did not load — check internet connection")

    # ── Navigation ─────────────────────────────────────────────────────

    def get_problem_url(self, question_number: int) -> str:
        """
        Resolve the full URL for a given LeetCode problem number.
        Uses the public /api/problems/all/ endpoint to map number → slug.
        """
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://leetcode.com",
        }
        if self.config.leetcode_session:
            headers["Cookie"] = (
                f"LEETCODE_SESSION={self.config.leetcode_session}; "
                f"csrftoken={self.config.leetcode_csrf_token}"
            )

        response = requests.get(
            "https://leetcode.com/api/problems/all/",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        problems = response.json().get("stat_status_pairs", [])

        for p in problems:
            if p["stat"]["frontend_question_id"] == question_number:
                slug = p["stat"]["question__title_slug"]
                return f"{self.config.leetcode_problems_url}/{slug}/"

        raise ValueError(f"Problem #{question_number} not found in problem list")

    def navigate_to_problem(self, url: str):
        """Navigate browser to the problem URL and wait for editor to load."""
        logger.info(f"Navigating to: {url}")
        self.driver.get(url)

        # Wait for Monaco code editor to be present
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".monaco-editor, [data-cy='code-area']")
            ))
            time.sleep(2)  # Allow React components to hydrate
        except TimeoutException:
            logger.warning("Editor not detected — page may not have loaded fully")

    def take_screenshot(self, filename: str = "screenshot.png"):
        """Capture screenshot for debugging."""
        path = f"logs/{filename}"
        self.driver.save_screenshot(path)
        logger.info(f"Screenshot saved: {path}")

    def close(self):
        """Safely close the browser."""
        if self.driver:
            self.driver.quit()
            logger.info("Browser closed")