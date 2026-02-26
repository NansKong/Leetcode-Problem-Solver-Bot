import csv
import logging
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AnalyticsLogger:
    """
    SQLite-backed logger for all LeetCode automation activity.

    Tracks:
    - Submission outcomes (Accepted, WA, TLE, etc.)
    - GPT token usage and cost estimation
    - Runtime and memory percentiles
    - Daily/weekly solve streaks
    - Difficulty distribution
    """

    OPENAI_COST_PER_1K = {
        "gpt-4o":           {"input": 0.005,  "output": 0.015},
        "gpt-4o-mini":      {"input": 0.00015,"output": 0.0006},
        "gpt-4-turbo":      {"input": 0.01,   "output": 0.03},
        "gpt-3.5-turbo":    {"input": 0.0005, "output": 0.0015},
    }

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Always store DB next to this file, not relative to cwd
            base = Path(__file__).resolve().parent.parent
            db_path = str(base / "results" / "leetcode_results.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create database tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript("""
                -- Submission attempts log
                CREATE TABLE IF NOT EXISTS attempts (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_number   INTEGER NOT NULL,
                    title             TEXT,
                    difficulty        TEXT,
                    language          TEXT,
                    status            TEXT,
                    runtime           TEXT,
                    memory            TEXT,
                    runtime_pct       REAL,
                    memory_pct        REAL,
                    gpt_model         TEXT,
                    tokens_used       INTEGER,
                    estimated_cost    REAL,
                    is_retry          INTEGER DEFAULT 0,
                    tags              TEXT,  -- JSON array
                    code_length       INTEGER,
                    solution_code     TEXT,
                    timestamp         TEXT NOT NULL
                );

                -- Cache of fetched problem metadata
                CREATE TABLE IF NOT EXISTS problems (
                    question_number   INTEGER PRIMARY KEY,
                    title             TEXT,
                    slug              TEXT,
                    difficulty        TEXT,
                    tags              TEXT,
                    acceptance_rate   TEXT,
                    description_len   INTEGER,
                    fetched_at        TEXT
                );

                -- Run session tracking
                CREATE TABLE IF NOT EXISTS sessions (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at        TEXT,
                    ended_at          TEXT,
                    problems_attempted INTEGER DEFAULT 0,
                    problems_accepted  INTEGER DEFAULT 0,
                    total_tokens       INTEGER DEFAULT 0,
                    total_cost         REAL DEFAULT 0.0
                );
            """)
        logger.debug("Database initialized")

    # ── Logging ────────────────────────────────────────────────────────

    def log_attempt(self, question_number: int, problem: dict,
                    solution: dict, status: str) -> int:
        # Add solution_code column if upgrading from older DB
        with self._connect() as conn:
            try:
                conn.execute("ALTER TABLE attempts ADD COLUMN solution_code TEXT")
            except Exception:
                pass  # Column already exists
        """
        Log a submission attempt to the database.
        Returns the inserted row ID.
        """
        tokens    = solution.get("tokens_used", 0)
        model     = solution.get("model", "gpt-4o")
        cost      = self._estimate_cost(model, solution)
        timestamp = datetime.now().isoformat()

        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO attempts (
                    question_number, title, difficulty, language, status,
                    runtime, memory, runtime_pct, memory_pct,
                    gpt_model, tokens_used, estimated_cost, is_retry,
                    tags, code_length, solution_code, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                question_number,
                problem.get("title", "Unknown"),
                problem.get("difficulty", "Unknown"),
                solution.get("language", "python3"),
                status,
                "N/A",  # Runtime filled after submission
                "N/A",
                None, None,
                model,
                tokens,
                cost,
                1 if solution.get("is_retry") else 0,
                json.dumps(problem.get("tags", [])),
                len(solution.get("code", "")),
                solution.get("code", ""),
                timestamp,
            ))
            row_id = cursor.lastrowid

            # Cache problem metadata
            conn.execute("""
                INSERT OR IGNORE INTO problems
                (question_number, title, slug, difficulty, tags, acceptance_rate, description_len, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                question_number,
                problem.get("title"),
                problem.get("slug"),
                problem.get("difficulty"),
                json.dumps(problem.get("tags", [])),
                problem.get("stats", {}).get("acceptance_rate"),
                len(problem.get("description", "")),
                timestamp,
            ))

        logger.info(f"Logged attempt #{row_id}: Q{question_number} → {status}")
        return row_id

    def update_runtime_stats(self, attempt_id: int, result: dict):
        """Update runtime/memory after submission completes."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE attempts
                SET runtime=?, memory=?, runtime_pct=?, memory_pct=?
                WHERE id=?
            """, (
                result.get("runtime"),
                result.get("memory"),
                result.get("runtime_pct"),
                result.get("memory_pct"),
                attempt_id,
            ))

    # ── Analytics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return aggregate statistics."""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*)                                            AS total,
                    SUM(CASE WHEN status='Accepted' THEN 1 ELSE 0 END) AS accepted,
                    SUM(tokens_used)                                    AS total_tokens,
                    ROUND(SUM(estimated_cost), 4)                       AS total_cost,
                    COUNT(DISTINCT question_number)                     AS unique_problems
                FROM attempts
            """).fetchone()

            total    = row["total"]    or 0
            accepted = row["accepted"] or 0
            rate     = round(accepted / total * 100, 1) if total > 0 else 0.0

            return {
                "total":           total,
                "accepted":        accepted,
                "acceptance_rate": rate,
                "total_tokens":    row["total_tokens"]    or 0,
                "total_cost":      row["total_cost"]      or 0.0,
                "unique_problems": row["unique_problems"] or 0,
            }

    def get_difficulty_breakdown(self) -> dict:
        """Count accepted/total per difficulty."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT difficulty,
                       COUNT(*) as total,
                       SUM(CASE WHEN status='Accepted' THEN 1 ELSE 0 END) as accepted
                FROM attempts GROUP BY difficulty
            """).fetchall()
        return {r["difficulty"]: {"total": r["total"], "accepted": r["accepted"]} for r in rows}

    def get_recent_attempts(self, limit: int = 10) -> list:
        """Fetch the most recent submission attempts."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT question_number, title, difficulty, status,
                       runtime, memory, language, timestamp
                FROM attempts ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def print_dashboard(self):
        from lc_utils import colorize, Color

        stats = self.get_stats()
        breakdown = self.get_difficulty_breakdown()
        recent = self.get_recent_attempts(5)

        print(colorize("\n═══════════════════════════════════════", Color.CYAN))
        print(colorize("         LEETCODE AUTOMATOR DASHBOARD  ", Color.CYAN))
        print(colorize("═══════════════════════════════════════", Color.CYAN))

        print(colorize(f"\n  Total Attempts   : {stats['total']}", Color.WHITE))
        print(colorize(f"  Accepted         : {stats['accepted']}", Color.GREEN))
        print(colorize(f"  Acceptance Rate  : {stats['acceptance_rate']}%", Color.GREEN))
        print(colorize(f"  Unique Problems  : {stats['unique_problems']}", Color.WHITE))
        print(colorize(f"  GPT Tokens Used  : {stats['total_tokens']:,}", Color.YELLOW))
        print(colorize(f"  Estimated Cost   : ${stats['total_cost']:.4f}", Color.YELLOW))

        print(colorize("\n  Difficulty Breakdown:", Color.CYAN))
        for diff, counts in breakdown.items():
            bar_len = int(counts['accepted'] / max(counts['total'], 1) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            color = {
                "Easy": Color.GREEN, "Medium": Color.YELLOW, "Hard": Color.RED
            }.get(diff, Color.WHITE)
            print(colorize(
                f"    {diff:<8} [{bar}] {counts['accepted']}/{counts['total']}", color
            ))

        print(colorize("\n  Recent Submissions:", Color.CYAN))
        for r in recent:
            status_color = Color.GREEN if r['status'] == "Accepted" else Color.RED
            print(colorize(
                f"    #{r['question_number']:<5} {r['title'][:25]:<25} "
                f"[{r['difficulty'][:1]}] {r['status']}", status_color
            ))
        print()

    # ── Solution Retrieval ─────────────────────────────────────────────

    def get_solution(self, question_number: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT question_number, title, difficulty, language,
                       solution_code, status, runtime, memory, timestamp
                FROM attempts
                WHERE question_number = ?
                ORDER BY id DESC LIMIT 1
            """, (question_number,)).fetchone()
        if row:
            return dict(row)
        return None

    def print_solution(self, question_number: int):
        """Print the stored solution for a problem to the console."""
        from lc_utils import colorize, Color
        result = self.get_solution(question_number)
        if not result:
            print(colorize(f"No solution found for problem #{question_number}", Color.RED))
            return
        print(colorize(f"\n── Problem #{result['question_number']}: {result['title']} [{result['difficulty']}]", Color.CYAN))
        print(colorize(f"   Status: {result['status']} | Runtime: {result['runtime']} | Saved: {result['timestamp']}", Color.YELLOW))
        print(colorize("\n── Solution Code ──────────────────────────────", Color.CYAN))
        print(result['solution_code'])

    # ── Export ─────────────────────────────────────────────────────────

    def export_csv(self, output_path: str = "results/attempts_export.csv"):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM attempts ORDER BY id DESC").fetchall()

        with open(output_path, "w", newline="") as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows([dict(r) for r in rows])

        print(f"✓ Exported {len(rows)} records to: {output_path}")
        return output_path

    # ── Cost Estimation ────────────────────────────────────────────────

    def _estimate_cost(self, model: str, solution: dict) -> float:
        """Estimate GPT API cost based on token usage."""
        rates = self.OPENAI_COST_PER_1K.get(model, {"input": 0.005, "output": 0.015})
        input_cost  = solution.get("prompt_tokens", 0)     / 1000 * rates["input"]
        output_cost = solution.get("completion_tokens", 0) / 1000 * rates["output"]
        return round(input_cost + output_cost, 6)