"""
╔══════════════════════════════════════════════════════════════╗
║          LeetCode Intelligent Automation System              ║
║          For Educational Purposes Only                       ║
╚══════════════════════════════════════════════════════════════╝

IMPORTANT: This tool is for LEARNING. Always understand the
generated code before submitting. Using this blindly violates
academic integrity and defeats the purpose of LeetCode practice.
"""

import argparse
import sys
from modules.navigator      import LeetCodeNavigator
from modules.extractor      import ProblemExtractor
from modules.gpt_solver     import GPTSolver
from modules.validator      import SolutionValidator
from modules.submitter      import AutoSubmitter
from modules.analytics      import AnalyticsLogger
from config                 import Config
from lc_utils               import banner, colorize, Color


def run_pipeline(question_number: int, language: str = "python3", dry_run: bool = False):
    """
    Main automation pipeline.

    Pipeline stages:
        1. Navigate  → Open LeetCode problem page
        2. Extract   → Scrape problem statement & examples
        3. Solve     → Send to GPT, receive solution
        4. Validate  → Check syntax, formatting, edge cases
        5. Submit    → Auto-submit via Selenium/Playwright
        6. Log       → Store result and update analytics
    """
    banner()
    logger   = AnalyticsLogger()
    config   = Config()

    print(colorize(f"\n🚀 Starting pipeline for Problem #{question_number}", Color.CYAN))
    print(colorize(f"   Language : {language}", Color.WHITE))
    print(colorize(f"   Dry Run  : {dry_run}\n", Color.WHITE))

    # ── Stage 1: Navigate ──────────────────────────────────────────────
    print(colorize("━━━ [1/6] Navigation Module", Color.YELLOW))
    navigator = LeetCodeNavigator(config)
    problem_url = navigator.get_problem_url(question_number)
    print(colorize(f"    ✓ Problem URL resolved: {problem_url}", Color.GREEN))

    # ── Stage 2: Extract ───────────────────────────────────────────────
    print(colorize("━━━ [2/6] Problem Extraction Module", Color.YELLOW))
    extractor = ProblemExtractor(config)
    problem   = extractor.fetch_problem(question_number)
    print(colorize(f"    ✓ Title   : {problem['title']}", Color.GREEN))
    print(colorize(f"    ✓ Difficulty: {problem['difficulty']}", Color.GREEN))
    print(colorize(f"    ✓ Tags    : {', '.join(problem['tags'])}", Color.GREEN))

    # ── Stage 3: Solve ─────────────────────────────────────────────────
    print(colorize("━━━ [3/6] GPT Solution Generation Module", Color.YELLOW))
    solver   = GPTSolver(config)
    solution = solver.generate_solution(problem, language)
    print(colorize("    ✓ Solution generated successfully", Color.GREEN))
    print(colorize(f"    ✓ Tokens used: {solution['tokens_used']}", Color.GREEN))

    # ── Stage 4: Validate ──────────────────────────────────────────────
    print(colorize("━━━ [4/6] Solution Validation Module", Color.YELLOW))
    validator = SolutionValidator()
    validation_result = validator.validate(solution['code'], problem, language)
    if validation_result['passed']:
        print(colorize("    ✓ Syntax check passed", Color.GREEN))
        print(colorize("    ✓ Edge case pre-check passed", Color.GREEN))
    else:
        print(colorize(f"    ✗ Validation failed: {validation_result['error']}", Color.RED))
        logger.log_attempt(question_number, problem, solution, "VALIDATION_FAILED")
        sys.exit(1)

    # ── Stage 5: Submit ────────────────────────────────────────────────
    print(colorize("━━━ [5/6] Auto-Submission Module", Color.YELLOW))
    if dry_run:
        print(colorize("    ⚠  DRY RUN — Skipping actual submission", Color.YELLOW))
        print(colorize("\n    ── Generated Solution Preview ──", Color.CYAN))
        print(solution['code'])
        submission_result = {"status": "DRY_RUN", "runtime": "N/A", "memory": "N/A"}
    else:
        submitter = AutoSubmitter(config, navigator.driver)
        submission_result = submitter.submit(problem_url, solution['code'], language)
        status_color = Color.GREEN if submission_result['status'] == "Accepted" else Color.RED
        print(colorize(f"    ✓ Submission Status : {submission_result['status']}", status_color))
        print(colorize(f"    ✓ Runtime           : {submission_result.get('runtime', 'N/A')}", Color.GREEN))
        print(colorize(f"    ✓ Memory            : {submission_result.get('memory', 'N/A')}", Color.GREEN))

    # ── Stage 6: Log ───────────────────────────────────────────────────
    print(colorize("━━━ [6/6] Analytics & Logging Module", Color.YELLOW))
    logger.log_attempt(question_number, problem, solution, submission_result['status'])
    stats = logger.get_stats()
    print(colorize(f"    ✓ Result logged to database", Color.GREEN))
    print(colorize(f"    ✓ Total solved: {stats['total']} | Accepted: {stats['accepted']} | "
                   f"Rate: {stats['acceptance_rate']}%", Color.GREEN))

    navigator.close()
    print(colorize("\n✅ Pipeline completed successfully!\n", Color.GREEN))
    return submission_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LeetCode Intelligent Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py 1                          # Solve problem #1 (Two Sum)
  python main.py 1 --language python3       # Specify language
  python main.py 1 --dry-run               # Preview solution without submitting
  python main.py --stats                    # View analytics dashboard
  python main.py --export                   # Export results to CSV
        """
    )
    parser.add_argument("question",    type=int,  nargs="?", help="LeetCode question number")
    parser.add_argument("--language",  type=str,  default="python3",
                        choices=["python3", "java", "cpp", "javascript"],
                        help="Programming language (default: python3)")
    parser.add_argument("--dry-run",   action="store_true", help="Generate solution without submitting")
    parser.add_argument("--stats",     action="store_true", help="Show analytics dashboard")
    parser.add_argument("--export",    action="store_true", help="Export logs to CSV")
    parser.add_argument("--solution",  type=int,  metavar="N", help="Print stored solution for problem #N")

    args = parser.parse_args()

    if args.solution:
        logger = AnalyticsLogger()
        logger.print_solution(args.solution)
    elif args.stats:
        logger = AnalyticsLogger()
        logger.print_dashboard()
    elif args.export:
        logger = AnalyticsLogger()
        logger.export_csv()
    elif args.question:
        run_pipeline(args.question, args.language, args.dry_run)
    else:
        parser.print_help()