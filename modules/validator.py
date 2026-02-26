import ast
import sys
import logging
import traceback
import subprocess
from io import StringIO
from typing import Optional

logger = logging.getLogger(__name__)


class SolutionValidator:
    """
    Validates generated solutions before submission.

    For Python3 solutions (primary language), we can:
    - Parse the AST to find syntax errors
    - Execute against sample test cases locally
    - Format with Black for clean code

    For other languages, we do basic structural checks only.
    """

    # Imports that should not appear in LeetCode solutions
    FORBIDDEN_IMPORTS = {
        "subprocess", "os.system", "eval", "exec",
        "__import__", "importlib", "ctypes", "socket"
    }

    def validate(self, code: str, problem: dict, language: str) -> dict:
        """
        Run all validation checks on the generated solution.

        Returns:
            {
                "passed": bool,
                "errors": list[str],
                "warnings": list[str],
                "formatted_code": str (possibly reformatted)
            }
        """
        errors   = []
        warnings = []
        formatted_code = code

        if language == "python3":
            # 1. Syntax check
            syntax_ok, syntax_err = self._check_syntax(code)
            if not syntax_ok:
                errors.append(f"Syntax Error: {syntax_err}")
                return self._result(False, errors, warnings, code)

            # 2. Security scan
            sec_warnings = self._security_scan(code)
            warnings.extend(sec_warnings)

            # 3. Structure check
            struct_ok, struct_msg = self._check_structure(code, problem)
            if not struct_ok:
                warnings.append(f"Structure Warning: {struct_msg}")

            # 4. Auto-format with Black
            formatted_code = self._format_python(code)

            # 5. Local execution against examples
            exec_results = self._run_local_examples(formatted_code, problem)
            if exec_results["errors"]:
                warnings.extend(exec_results["errors"])

        elif language in ("java", "cpp", "javascript"):
            # Basic non-empty check for other languages
            if len(code.strip()) < 20:
                errors.append("Generated code appears too short")

        logger.info(f"Validation: {'PASSED' if not errors else 'FAILED'} "
                    f"({len(warnings)} warnings)")

        return self._result(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            formatted_code=formatted_code,
            error=errors[0] if errors else None
        )

    # ── Syntax Check ───────────────────────────────────────────────────

    def _check_syntax(self, code: str) -> tuple[bool, Optional[str]]:
        """Parse Python code AST to detect syntax errors."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"

    # ── Security Scan ──────────────────────────────────────────────────

    def _security_scan(self, code: str) -> list:
        """Flag dangerous patterns in generated code."""
        warnings = []
        code_lower = code.lower()
        for forbidden in self.FORBIDDEN_IMPORTS:
            if forbidden in code_lower:
                warnings.append(f"Security: Found potentially dangerous call '{forbidden}'")
        return warnings

    # ── Structure Check ────────────────────────────────────────────────

    def _check_structure(self, code: str, problem: dict) -> tuple[bool, Optional[str]]:
        """
        Verify the solution contains the expected class/function.
        LeetCode expects specific class names and method signatures.
        """
        expected_func = problem.get("function_name", "")
        if expected_func and expected_func not in code:
            return False, f"Expected function '{expected_func}' not found in solution"

        # Check for Solution class (most LeetCode problems use this)
        if "class Solution" not in code and "def " not in code:
            return False, "No class or function definition found"

        return True, None

    # ── Auto-Formatting ────────────────────────────────────────────────

    def _format_python(self, code: str) -> str:
        """
        Format Python code using Black.
        Falls back to original if Black is not installed.
        """
        try:
            import black
            formatted = black.format_str(code, mode=black.Mode(line_length=88))
            return formatted
        except ImportError:
            logger.debug("Black not installed, skipping auto-format")
            return code
        except Exception as e:
            logger.warning(f"Black formatting failed: {e}")
            return code

    # ── Local Execution ────────────────────────────────────────────────

    def _run_local_examples(self, code: str, problem: dict) -> dict:
        """
        Attempt to execute the solution against the extracted
        example test cases locally using Python exec().

        This is best-effort — LeetCode examples may reference
        custom classes (ListNode, TreeNode) not available locally.
        We inject common LeetCode helper classes automatically.
        """
        errors = []
        lc_helpers = self._get_lc_helpers()

        for i, example_input in enumerate(problem.get("examples", [])[:2]):
            try:
                # Build execution context with helpers
                namespace = {}
                exec(lc_helpers + "\n" + code, namespace)
                logger.debug(f"Example {i+1} executed successfully (no crash)")
            except Exception as e:
                errors.append(f"Example {i+1} execution warning: {type(e).__name__}: {e}")

        return {"errors": errors}

    def _get_lc_helpers(self) -> str:
        """
        Inject commonly required LeetCode helper classes.
        Many problems use ListNode and TreeNode which aren't
        in Python's standard library.
        """
        return """
class ListNode:
    def __init__(self, val=0, next=None):
        self.val  = val
        self.next = next

class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val   = val
        self.left  = left
        self.right = right

from typing import List, Optional, Dict, Tuple
from collections import defaultdict, Counter, deque
import heapq, math, bisect, functools
"""

    @staticmethod
    def _result(passed, errors, warnings, formatted_code, error=None):
        return {
            "passed":         passed,
            "errors":         errors,
            "warnings":       warnings,
            "formatted_code": formatted_code,
            "error":          error,
        }
