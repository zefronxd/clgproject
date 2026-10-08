# MindTrack

MindTrack is a private daily journal with emotion scoring, sentiment trends, and support resources when an entry may signal distress.

## Run & Operate

- Start the **MindTrack** workflow (`python main.py`), which serves the Flask app on port 5000.
- `python -m py_compile main.py distress_keywords.py` — check Python syntax.
- `python -m unittest discover -s tests` — run the chat API safety and behavior tests.
- `uv sync` — install the Python dependencies from `pyproject.toml`.
- Required environment secret: `SESSION_SECRET`.
- Optional environment secret: `HF_API_TOKEN` enables Hugging Face emotion scoring. Without it, the app uses its keyword-based demo scorer.
- Optional environment variable: `EMOTION_MODEL` selects the Hugging Face model; the default is `j-hartmann/emotion-english-distilroberta-base`.
- Optional environment secret: `GROQ_API_KEY` enables Chat Check-in; without it, chat fails gracefully and other pages continue to work.
- Optional environment variable: `GROQ_MODEL` selects the Groq model; the default is `openai/gpt-oss-120b`.

## Stack

- Python 3.11+
- Flask, Flask-SQLAlchemy, and SQLite
- Jinja HTML templates, plain CSS and JavaScript, Chart.js from CDN
- Hugging Face Inference API when configured; no local transformer models

The workspace also contains the original pnpm/TypeScript scaffold and its API/design artifacts. MindTrack itself runs through the Python workflow and does not use React or Node.

## Where things live

- `main.py` — Flask routes, authentication, persistence, emotion scoring, dashboard calculations, and demo data.
- `templates/` — authentication, journal, history, dashboard, and error pages.
- `static/` — responsive styles and small browser scripts.
- `distress_keywords.py` — editable distress phrase list.
- `helplines.json` — support phone lines shown after a distress signal.
- `insight_config.json` — fixed, non-AI suggestions for dashboard insights.
- `instance/mindtrack.db` — local SQLite database (created automatically and excluded from version control).
- `README.md` — run instructions, environment variables, privacy notes, and page descriptions.

## Product

- Separate username/password accounts; each journal entry query is scoped to the signed-in user.
- Check-ins are limited to 3,000 characters and include emotion scores, sentiment, timestamp, and a distress-resource check.
- History is newest-first and supports deleting individual entries.
- Dashboard charts show daily sentiment and emotion counts for 7- or 30-day periods, with fixed rule-based observations.
- The dashboard can add one batch of 30 sample entries for demonstrating the charts.

## Architecture decisions

- SQLite is local to the app to keep this college-project MVP straightforward.
- Journal text is sent to Hugging Face only when `HF_API_TOKEN` is configured. Otherwise, keyword scoring runs locally.
- Chat transcripts stay in tab-scoped browser storage. Only the latest six chat messages are sent to Groq, after local distress phrase detection; journal entries are not included.
- Passwords use Werkzeug's password hashing; all mutating forms use a session-bound CSRF token.
- Distress phrase matches only trigger support information; they are not a diagnosis.

## Gotchas

- `SESSION_SECRET` is required at startup. Do not commit secret values.
- Hugging Face model/API errors fall back to local keyword scoring.
- The demo data action is idempotent per account; it will not repeatedly add duplicate sample batches.
- Do not log journal text.
