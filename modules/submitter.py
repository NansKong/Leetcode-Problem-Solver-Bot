import time
import logging
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

logger = logging.getLogger(__name__)


class AutoSubmitter:
    """
    Submits solutions to LeetCode via Selenium browser automation.

    Two strategies:
    1. API Submission (preferred): POST to LeetCode's internal submit API
    2. Browser Submission (fallback): Selenium fills editor and clicks Submit
    """

    # LeetCode language IDs for API submission
    LANG_ID_MAP = {
        "python3":    71,
        "python":     70,
        "java":       4,
        "cpp":        54,
        "javascript": 63,
        "typescript": 74,
        "go":         22,
        "rust":       73,
        "c":          49,
    }

    def __init__(self, config, driver):
        self.config  = config
        self.driver  = driver
        self.wait    = WebDriverWait(driver, config.browser_timeout)
        self.session = self._build_api_session(config)

    def _build_api_session(self, config) -> requests.Session:
        """Build an authenticated requests session for API calls."""
        s = requests.Session()
        s.headers.update({
            "Content-Type":   "application/json",
            "Referer":        "https://leetcode.com",
            "User-Agent":     "Mozilla/5.0",
            "X-CSRFToken":    config.leetcode_csrf_token,
        })
        if config.leetcode_session:
            s.cookies.set("LEETCODE_SESSION", config.leetcode_session)
            s.cookies.set("csrftoken",        config.leetcode_csrf_token)
        return s

    def submit(self, problem_url: str, code: str, language: str) -> dict:
        """
        Submit solution and return the judge verdict.

        Tries API submission first; falls back to browser if it fails.
        """
        slug = self._extract_slug(problem_url)

        # Try fast API submission first
        try:
            return self._submit_via_api(slug, code, language)
        except Exception as e:
            logger.warning(f"API submission failed ({e}), falling back to browser...")
            return self._submit_via_browser(problem_url, code, language)

    # ── Strategy 1: API Submission ─────────────────────────────────────

    def _submit_via_api(self, slug: str, code: str, language: str) -> dict:
        """
        Submit via LeetCode's internal REST API.
        This is faster and more reliable than browser automation.
        """
        lang_id = self.LANG_ID_MAP.get(language)
        if lang_id is None:
            raise ValueError(f"Unsupported language: {language}")

        submit_url = f"https://leetcode.com/problems/{slug}/submit/"

        payload = {
            "lang":        language,
            "question_id": self._get_question_id(slug),
            "typed_code":  code,
        }

        logger.info(f"Submitting via API to: {submit_url}")
        response = self.session.post(submit_url, json=payload, timeout=30)
        response.raise_for_status()

        submission_id = response.json().get("submission_id")
        if not submission_id:
            raise RuntimeError("No submission_id in response")

        logger.info(f"Submission ID: {submission_id} — Waiting for judge...")
        return self._poll_result(submission_id)

    def _get_question_id(self, slug: str) -> str:
        """Fetch the internal question ID needed for submission."""
        query = """
        query getQuestionId($titleSlug: String!) {
          question(titleSlug: $titleSlug) { questionId }
        }
        """
        res = self.session.post(
            "https://leetcode.com/graphql",
            json={"query": query, "variables": {"titleSlug": slug}},
            timeout=15
        )
        return res.json()["data"]["question"]["questionId"]

    def _poll_result(self, submission_id: int, max_wait: int = 30) -> dict:
        """
        Poll the judge API until a verdict is returned.
        LeetCode's judge typically responds within 3–10 seconds.
        """
        check_url = f"https://leetcode.com/submissions/detail/{submission_id}/check/"
        start     = time.time()

        while time.time() - start < max_wait:
            time.sleep(2)
            response = self.session.get(check_url, timeout=15)
            data     = response.json()
            state    = data.get("state", "")

            logger.debug(f"Judge state: {state}")

            if state == "SUCCESS":
                return self._parse_verdict(data)
            elif state == "PENDING":
                continue
            else:
                return {"status": state, "runtime": "N/A", "memory": "N/A"}

        return {"status": "TIMEOUT", "runtime": "N/A", "memory": "N/A"}

    def _parse_verdict(self, data: dict) -> dict:
        """Parse the final judge response into a clean result dict."""
        status_code = data.get("status_code", 0)
        status_map  = {
            10: "Accepted",
            11: "Wrong Answer",
            12: "Memory Limit Exceeded",
            13: "Output Limit Exceeded",
            14: "Time Limit Exceeded",
            15: "Runtime Error",
            16: "Internal Error",
            20: "Compile Error",
        }
        status = status_map.get(status_code, f"Unknown ({status_code})")

        result = {
            "status":        status,
            "runtime":       data.get("status_runtime", "N/A"),
            "memory":        data.get("status_memory", "N/A"),
            "runtime_pct":   data.get("runtime_percentile", "N/A"),
            "memory_pct":    data.get("memory_percentile", "N/A"),
            "total_correct": data.get("total_correct", 0),
            "total_testcases": data.get("total_testcases", 0),
        }

        if status != "Accepted":
            result["last_testcase"]   = data.get("input_formatted", "N/A")
            result["expected_output"] = data.get("expected_output", "N/A")
            result["actual_output"]   = data.get("code_output", "N/A")
            result["error_message"]   = data.get("runtime_error", "")

        return result

    # ── Strategy 2: Browser Submission ────────────────────────────────

    def _submit_via_browser(self, problem_url: str, code: str, language: str) -> dict:
        """
        Submit using Selenium browser automation.
        Used as fallback when API submission is unavailable.
        """
        logger.info("Submitting via browser automation...")
        self.driver.get(problem_url)
        time.sleep(3)

        # Select language from dropdown
        self._select_language(language)

        # Clear existing code and inject our solution
        self._inject_code(code)

        # Click Submit button
        self._click_submit()

        # Wait for and parse result
        return self._wait_for_browser_result()

    def _select_language(self, language: str):
        """Click the language dropdown and select the target language."""
        try:
            # Find language selector button
            lang_btn = self.wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "[data-cy='lang-select'], .ant-select-selector")
            ))
            lang_btn.click()
            time.sleep(1)

            # Click the desired language option
            lang_option = self.wait.until(EC.element_to_be_clickable(
                (By.XPATH, f"//div[contains(@class,'ant-select-item') and text()='{language}']")
            ))
            lang_option.click()
            time.sleep(1)
            logger.debug(f"Language set to: {language}")
        except Exception as e:
            logger.warning(f"Language selection failed: {e}")

    def _inject_code(self, code: str):
        """Clear Monaco editor and insert the solution code."""
        try:
            editor = self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".monaco-editor .view-lines")
            ))
            # Select all and delete
            ActionChains(self.driver)\
                .click(editor)\
                .key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL)\
                .send_keys(Keys.DELETE)\
                .perform()
            time.sleep(0.5)

            # Type the solution (Monaco accepts keyboard input)
            ActionChains(self.driver)\
                .click(editor)\
                .send_keys(code)\
                .perform()
            time.sleep(1)
            logger.debug("Code injected into editor")
        except Exception as e:
            raise RuntimeError(f"Failed to inject code into editor: {e}")

    def _click_submit(self):
        """Find and click the Submit button."""
        try:
            submit_btn = self.wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "[data-cy='submit-code-btn'], button[data-e2e-locator='console-submit-button']")
            ))
            submit_btn.click()
            logger.info("Submit button clicked")
        except Exception as e:
            raise RuntimeError(f"Could not click Submit button: {e}")

    def _wait_for_browser_result(self) -> dict:
        """Wait for submission result to appear in browser."""
        try:
            result_el = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-e2e-locator='submission-result']")
                )
            )
            result_text = result_el.text
            logger.info(f"Browser result: {result_text}")
            return {"status": result_text, "runtime": "N/A", "memory": "N/A"}
        except Exception:
            return {"status": "UNKNOWN", "runtime": "N/A", "memory": "N/A"}

    @staticmethod
    def _extract_slug(url: str) -> str:
        """Extract problem slug from URL."""
        parts = url.rstrip("/").split("/")
        return parts[-1]
