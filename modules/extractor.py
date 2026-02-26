import re
import json
import logging
import requests
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class HTMLToTextParser(HTMLParser):
    """Convert HTML problem description to clean plain text."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip_tags = {"script", "style"}
        self._in_skip   = False

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._in_skip = True
        if tag in ("p", "li", "br", "h4"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._in_skip = False

    def handle_data(self, data):
        if not self._in_skip:
            self.text_parts.append(data)

    def get_text(self):
        raw = "".join(self.text_parts)
        # Collapse multiple blank lines
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


class ProblemExtractor:
    """
    Extracts structured problem data via LeetCode's GraphQL API.

    The GraphQL approach is more reliable than Selenium scraping because:
    - No JavaScript rendering required
    - Structured JSON response
    - Works without a browser session
    - Faster (no page load overhead)
    """

    # ── GraphQL Query ──────────────────────────────────────────────────
    PROBLEM_QUERY = """
    query getProblemDetails($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        questionId
        questionFrontendId
        title
        titleSlug
        difficulty
        content
        exampleTestcaseList
        codeSnippets {
          lang
          langSlug
          code
        }
        topicTags {
          name
          slug
        }
        hints
        stats
        metaData
      }
    }
    """

    # Resolve question number → slug
    SLUG_QUERY = """
    query getSlugByNumber($num: Int!) {
      question: problemsetQuestion(questionFrontendId: $num) {
        titleSlug
      }
    }
    """

    def __init__(self, config):
        self.config  = config
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type":  "application/json",
            "Referer":       "https://leetcode.com",
            "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        if config.leetcode_session:
            self.session.cookies.set("LEETCODE_SESSION", config.leetcode_session)
        if config.leetcode_csrf_token:
            self.session.cookies.set("csrftoken", config.leetcode_csrf_token)
            self.session.headers["X-CSRFToken"] = config.leetcode_csrf_token

    def _graphql(self, query: str, variables: dict) -> dict:
        """Execute a GraphQL query against LeetCode's API."""
        response = self.session.post(
            self.config.leetcode_graphql_url,
            json={"query": query, "variables": variables},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise RuntimeError(f"GraphQL error: {data['errors']}")
        return data["data"]

    def _resolve_slug(self, question_number: int) -> str:
        """Convert question number (e.g., 1) to URL slug (e.g., 'two-sum')."""
        # Alternative: Use the public problem list API
        response = self.session.get(
            f"https://leetcode.com/api/problems/all/",
            timeout=30
        )
        problems = response.json().get("stat_status_pairs", [])
        for p in problems:
            if p["stat"]["frontend_question_id"] == question_number:
                return p["stat"]["question__title_slug"]
        raise ValueError(f"Problem #{question_number} not found")

    def fetch_problem(self, question_number: int) -> dict:
        """
        Fetch complete problem data for a given question number.

        Returns a structured dict with all information needed
        to build an effective GPT prompt.
        """
        logger.info(f"Fetching problem #{question_number} from LeetCode API...")

        # Step 1: Resolve question number → title slug
        slug = self._resolve_slug(question_number)
        logger.info(f"Resolved slug: {slug}")

        # Step 2: Fetch full problem details
        data     = self._graphql(self.PROBLEM_QUERY, {"titleSlug": slug})
        question = data["question"]

        # Step 3: Parse HTML description → plain text
        parser = HTMLToTextParser()
        parser.feed(question.get("content", ""))
        description = parser.get_text()

        # Step 4: Extract starter code for requested languages
        code_snippets = {
            snippet["langSlug"]: snippet["code"]
            for snippet in question.get("codeSnippets", [])
        }

        # Step 5: Parse metadata (function name, parameter types)
        meta = {}
        try:
            meta = json.loads(question.get("metaData", "{}"))
        except json.JSONDecodeError:
            pass

        # Step 6: Parse stats (acceptance rate, total submissions)
        stats = {}
        try:
            stats = json.loads(question.get("stats", "{}"))
        except json.JSONDecodeError:
            pass

        problem = {
            "id":             question["questionFrontendId"],
            "title":          question["title"],
            "slug":           question["titleSlug"],
            "difficulty":     question["difficulty"],
            "description":    description,
            "examples":       question.get("exampleTestcaseList", []),
            "code_snippets":  code_snippets,
            "tags":           [t["name"] for t in question.get("topicTags", [])],
            "hints":          question.get("hints", []),
            "function_name":  meta.get("name", "solution"),
            "params":         meta.get("params", []),
            "stats": {
                "acceptance_rate": stats.get("acRate", "N/A"),
                "total_accepted":  stats.get("totalAccepted", "N/A"),
                "total_submitted": stats.get("totalSubmission", "N/A"),
            },
            "url": f"https://leetcode.com/problems/{slug}/"
        }

        logger.info(f"Extracted: [{problem['difficulty']}] {problem['title']} "
                    f"(Acceptance: {problem['stats']['acceptance_rate']})")
        return problem

    def fetch_problem_batch(self, numbers: list) -> list:
        """Fetch multiple problems for batch processing."""
        return [self.fetch_problem(n) for n in numbers]
