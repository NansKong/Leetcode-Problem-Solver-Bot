"""
server.py — Flask API + Dashboard Server
─────────────────────────────────────────
Serves the live analytics dashboard and exposes all DB data
as JSON REST endpoints that the HTML dashboard fetches.

Run:
    python server.py

Then open: http://localhost:5000
"""

import json
import webbrowser
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, abort
from flask_cors import CORS

# Import our analytics module
import sys
sys.path.insert(0, str(Path(__file__).parent))
from modules.analytics import AnalyticsLogger

app  = Flask(__name__, static_folder=".")
CORS(app)  # Allow requests from dashboard HTML

db = AnalyticsLogger()


# ── API Routes ──────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    """Overall summary statistics."""
    return jsonify(db.get_stats())


@app.route("/api/difficulty")
def api_difficulty():
    """Accepted/total counts per difficulty."""
    return jsonify(db.get_difficulty_breakdown())


@app.route("/api/recent")
def api_recent():
    """Last 20 submission attempts."""
    rows = db.get_recent_attempts(limit=20)
    return jsonify(rows)


@app.route("/api/attempts")
def api_attempts():
    """All attempts from the DB."""
    with db._connect() as conn:
        rows = conn.execute("""
            SELECT id, question_number, title, difficulty, language,
                   status, runtime, memory, runtime_pct, memory_pct,
                   gpt_model, tokens_used, estimated_cost, is_retry,
                   tags, code_length, timestamp
            FROM attempts ORDER BY id DESC
        """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/solution/<int:question_number>")
def api_solution(question_number):
    """Return the stored solution code for a problem number."""
    result = db.get_solution(question_number)
    if not result:
        abort(404, description=f"No solution found for problem #{question_number}")
    return jsonify(result)


@app.route("/api/tags")
def api_tags():
    """Aggregate tag frequency across all accepted solutions."""
    with db._connect() as conn:
        rows = conn.execute("""
            SELECT tags FROM attempts WHERE status = 'Accepted' AND tags IS NOT NULL
        """).fetchall()
    freq = {}
    for row in rows:
        try:
            for tag in json.loads(row["tags"]):
                freq[tag] = freq.get(tag, 0) + 1
        except Exception:
            pass
    sorted_tags = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return jsonify([{"tag": t, "count": c} for t, c in sorted_tags[:15]])


@app.route("/api/timeline")
def api_timeline():
    """Daily solve counts for the activity chart."""
    with db._connect() as conn:
        rows = conn.execute("""
            SELECT DATE(timestamp) as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='Accepted' THEN 1 ELSE 0 END) as accepted
            FROM attempts
            GROUP BY DATE(timestamp)
            ORDER BY day DESC
            LIMIT 30
        """).fetchall()
    return jsonify([dict(r) for r in rows])


# ── Dashboard Route ─────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    """Serve the live dashboard HTML."""
    return send_from_directory(".", "dashboard.html")


# ── Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n⚡ LeetCode Automator — Dashboard Server")
    print("   URL  : http://localhost:5000")
    print("   DB   : " + db.db_path)
    print("   Press Ctrl+C to stop\n")
    webbrowser.open("http://localhost:5000")
    app.run(debug=False, port=5000, use_reloader=False)