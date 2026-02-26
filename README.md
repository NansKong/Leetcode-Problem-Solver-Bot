# ⚡ LeetCode Intelligent Automation System

> **For Educational Purposes Only.**
> Understanding generated code is mandatory. Blind submission violates the spirit of learning.

---

## Project Structure

```
leetcode_automator/
│
├── main.py                    # Entry point — runs the full pipeline
├── config.py                  # Centralized configuration & credentials
├── utils.py                   # Colors, banner, shared helpers
├── requirements.txt           # All Python dependencies
├── .env.example               # Credential template (copy to .env)
├── dashboard.html             # Analytics dashboard (open in browser)
│
├── modules/
│   ├── navigator.py           # Module 1: Selenium browser automation
│   ├── extractor.py           # Module 2: GraphQL problem fetcher
│   ├── gpt_solver.py          # Module 3: GPT prompt engineering + API
│   ├── validator.py           # Module 4: Syntax check + formatting
│   ├── submitter.py           # Module 5: API + browser submission
│   └── analytics.py          # Module 6: SQLite logging + analytics
│
├── results/
│   └── leetcode_results.db    # SQLite database (auto-created)
└── logs/                      # Run logs and screenshots
```

---

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt

# Install ChromeDriver (for Selenium)
pip install webdriver-manager
```

### 2. Configure Credentials
```bash
cp .env.example .env
# Edit .env with your OpenAI key and LeetCode session
```

**Getting LeetCode Session Cookie (Recommended):**
1. Log in at https://leetcode.com in your browser
2. Open DevTools (`F12`) → Application → Cookies → `leetcode.com`
3. Copy `LEETCODE_SESSION` and `csrftoken` values to `.env`

### 3. Run the Pipeline
```bash
# Solve problem #1 (Two Sum) — full pipeline
python main.py 1

# Preview solution without submitting
python main.py 1 --dry-run

# Use a different language
python main.py 1 --language java

# View analytics dashboard
python main.py --stats

# Export results to CSV
python main.py --export
```

---

## System Modules Explained

| Module | File | Responsibility |
|--------|------|----------------|
| 1. Navigation | `navigator.py` | Opens browser, handles login via session cookie or form |
| 2. Extraction | `extractor.py` | Queries LeetCode GraphQL API for problem data |
| 3. GPT Solver | `gpt_solver.py` | Builds prompts, calls GPT-4o, handles retries |
| 4. Validator | `validator.py` | AST syntax check, Black formatting, edge case run |
| 5. Submitter | `submitter.py` | REST API submission + Selenium fallback |
| 6. Analytics | `analytics.py` | SQLite logging, stats, CSV export, dashboard |

---

## Pipeline Flow

```
User Input (Q#)
     │
     ▼
[1] Navigator    — Launches Chrome, authenticates with LeetCode
     │
     ▼
[2] Extractor    — GraphQL API → Title, Description, Examples, Tags
     │
     ▼
[3] GPT Solver   — Prompt Engineering → gpt-4o → Optimized Solution
     │
     ▼
[4] Validator    — AST parse, Black format, local example run
     │
     ▼
[5] Submitter    — POST to LeetCode Submit API → Poll for verdict
     │
     ▼
[6] Analytics    — Log to SQLite → Update stats → Print result
```

---

## Prompt Engineering Strategy

The GPT prompt includes:
- **Role**: "Expert competitive programmer"
- **Context**: Difficulty, tags, acceptance rate, full description
- **Starter code**: Language-specific template
- **Constraints**: No markdown fences, include complexity comments
- **Temperature**: 0.2 (deterministic, less creative variation)

On Wrong Answer, the system retries with the failed test case in context.

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Browser Automation | Selenium 4 + ChromeDriver |
| AI Solution Generation | OpenAI GPT-4o |
| Problem Fetching | LeetCode GraphQL API |
| Code Formatting | Black |
| Database | SQLite (built-in) |
| HTTP Client | requests |
| Configuration | python-dotenv |

---

## ⚠ Important Notes

1. **Understand the code** — Always read and understand solutions before submitting
2. **Rate limits** — Don't spam submissions; LeetCode may flag automated accounts
3. **Session cookies expire** — Refresh your `LEETCODE_SESSION` if login fails
4. **GPT costs money** — Monitor your OpenAI usage; ~$0.02/problem with GPT-4o
5. **Ethical use** — This tool is for learning acceleration, not cheating