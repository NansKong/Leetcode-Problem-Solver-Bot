import re
import logging
import openai

logger = logging.getLogger(__name__)


# ── Prompt Templates ────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert competitive programmer with deep knowledge of:
- Data structures: arrays, linked lists, trees, graphs, heaps, tries
- Algorithms: dynamic programming, binary search, sliding window, two pointers,
  BFS/DFS, union-find, segment trees, monotonic stacks
- Complexity analysis: Big-O time and space

When solving LeetCode problems:
1. Analyze the problem carefully and identify the optimal algorithmic approach
2. Implement a clean, well-commented solution
3. Handle edge cases explicitly
4. Aim for the best possible time and space complexity
5. Return ONLY the solution code (no markdown fences, no explanation outside code)
"""

SOLVE_TEMPLATE = """
Solve this LeetCode problem:

## Problem: {title} (#{id}) — {difficulty}
## Tags: {tags}
## Acceptance Rate: {acceptance_rate}

### Problem Statement:
{description}

### Starter Code ({language}):
{starter_code}

### Examples:
{examples}

### Instructions:
- Write a complete, optimized solution in {language}
- Include the class/function exactly as required by the starter code
- Add inline comments explaining your approach
- At the bottom (in comments), state: Time Complexity, Space Complexity, Approach used
- Do NOT include markdown code fences
- Handle all edge cases
"""

RETRY_TEMPLATE = """
Your previous solution for "{title}" produced WRONG ANSWER.

Failed Test Case:
  Input:  {failed_input}
  Expected: {expected_output}
  Got:    {actual_output}

Please analyze the failure, identify the bug, and provide a corrected solution.
Return ONLY the corrected code.
"""

EXPLAIN_TEMPLATE = """
Explain this LeetCode solution for educational purposes:

Problem: {title}
Code:
{code}

Provide:
1. Algorithm/approach name
2. Step-by-step walkthrough
3. Why this approach is optimal
4. Time and space complexity with justification
"""


class GPTSolver:
    """
    Integrates with OpenAI's GPT API to generate LeetCode solutions.

    Features:
    - Structured prompt engineering for each problem
    - Automatic retry with failed test case context
    - Multi-language support
    - Token usage tracking
    - Solution explanation generation (for learning)
    """

    LANGUAGE_LABELS = {
        "python3":    "Python 3",
        "java":       "Java",
        "cpp":        "C++",
        "javascript": "JavaScript",
    }

    def __init__(self, config):
        self.config = config
        # Detect OpenRouter key (sk-or-v1-...) vs standard OpenAI key
        api_key = config.openai_api_key
        if api_key.startswith("sk-or-"):
            self.client = openai.OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://github.com/leetcode-automator",
                    "X-Title": "LeetCode Automator",
                }
            )
        else:
            self.client = openai.OpenAI(api_key=api_key)
        self.conversation_history = []  # For multi-turn correction

    def _call_api(self, messages: list) -> dict:
        """
        Call the GPT API with given message history.
        Returns the response text and usage stats.
        """
        response = self.client.chat.completions.create(
            model=self.config.gpt_model,
            messages=messages,
            temperature=self.config.gpt_temperature,
            max_tokens=self.config.gpt_max_tokens,
        )
        return {
            "text":         response.choices[0].message.content.strip(),
            "tokens_used":  response.usage.total_tokens,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "finish_reason": response.choices[0].finish_reason,
        }

    def _build_solve_prompt(self, problem: dict, language: str) -> str:
        """
        Build a rich, context-aware prompt for the given problem.
        Better context → better solutions.
        """
        lang_label   = self.LANGUAGE_LABELS.get(language, language)
        starter_code = problem["code_snippets"].get(language, "# No starter code available")

        examples_text = "\n".join(
            f"  Input:  {ex}" for ex in problem.get("examples", [])[:3]
        ) or "  See problem description"

        return SOLVE_TEMPLATE.format(
            title         = problem["title"],
            id            = problem["id"],
            difficulty    = problem["difficulty"],
            tags          = ", ".join(problem.get("tags", [])),
            acceptance_rate = problem["stats"].get("acceptance_rate", "N/A"),
            description   = problem["description"][:3000],  # Truncate very long problems
            starter_code  = starter_code,
            examples      = examples_text,
            language      = lang_label,
        )

    def generate_solution(self, problem: dict, language: str = "python3") -> dict:
        """
        Generate an optimized solution for the given problem.

        Args:
            problem:  Structured problem dict from ProblemExtractor
            language: Target programming language slug

        Returns:
            dict with 'code', 'tokens_used', 'approach', and raw 'response'
        """
        logger.info(f"Generating solution for: {problem['title']} ({language})")

        # Build initial prompt
        user_prompt = self._build_solve_prompt(problem, language)

        # Initialize conversation
        self.conversation_history = [
            {"role": "system",  "content": SYSTEM_PROMPT},
            {"role": "user",    "content": user_prompt},
        ]

        # Call GPT
        result = self._call_api(self.conversation_history)
        code   = self._clean_code(result["text"])

        # Add assistant response to history (for potential retry)
        self.conversation_history.append({"role": "assistant", "content": result["text"]})

        logger.info(f"Solution generated. Tokens used: {result['tokens_used']}")
        return {
            "code":               code,
            "raw_response":       result["text"],
            "tokens_used":        result["tokens_used"],
            "prompt_tokens":      result["prompt_tokens"],
            "completion_tokens":  result["completion_tokens"],
            "language":           language,
            "model":              self.config.gpt_model,
        }

    def retry_with_feedback(self, problem: dict, failed_case: dict) -> dict:
        """
        Retry solution generation with failed test case context.
        Uses the same conversation history for better self-correction.

        Args:
            problem:     Original problem dict
            failed_case: Dict with 'input', 'expected', 'actual'
        """
        logger.info(f"Retrying with failed test case feedback...")

        retry_prompt = RETRY_TEMPLATE.format(
            title           = problem["title"],
            failed_input    = failed_case.get("input", "N/A"),
            expected_output = failed_case.get("expected", "N/A"),
            actual_output   = failed_case.get("actual", "N/A"),
        )

        self.conversation_history.append({"role": "user", "content": retry_prompt})

        result = self._call_api(self.conversation_history)
        code   = self._clean_code(result["text"])

        self.conversation_history.append({"role": "assistant", "content": result["text"]})

        return {
            "code":        code,
            "tokens_used": result["tokens_used"],
            "is_retry":    True,
        }

    def explain_solution(self, problem: dict, code: str) -> str:
        """
        Generate a plain-English explanation of a solution.
        Useful for the educational/learning component.
        """
        explain_prompt = EXPLAIN_TEMPLATE.format(
            title=problem["title"],
            code=code
        )
        messages = [
            {"role": "system", "content": "You are an excellent CS educator."},
            {"role": "user",   "content": explain_prompt},
        ]
        result = self._call_api(messages)
        return result["text"]

    @staticmethod
    def _clean_code(raw: str) -> str:
        """
        Remove markdown code fences if GPT accidentally included them.
        GPT sometimes wraps code in ```python ... ``` despite instructions.
        """
        # Remove ```python or ```cpp etc.
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw.strip())
        raw = re.sub(r"\n?```$", "", raw)
        return raw.strip()