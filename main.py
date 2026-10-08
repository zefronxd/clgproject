import json
import os
import re
import secrets
import threading
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import requests
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

from distress_keywords import matches_distress_phrase


BASE_DIR = Path(__file__).resolve().parent
EMOTIONS = ["anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise"]
EMOTION_MODEL = os.environ.get(
    "EMOTION_MODEL", "j-hartmann/emotion-english-distilroberta-base"
)
HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "").strip()
HF_ENDPOINT = f"https://router.huggingface.co/hf-inference/models/{EMOTION_MODEL}"
CHAT_SYSTEM_PROMPT = (
    "You are MindTrack's supportive check-in companion. Reply in the user's "
    "language (English, Hindi or Hinglish), in 2-4 short sentences, in a warm "
    "and non-judgmental tone. You are not a therapist or doctor: never diagnose, "
    "never suggest medication, and never claim to replace professional help. "
    "Ask at most one gentle follow-up question. If the user seems to be in "
    "crisis, encourage contacting a trusted person or a helpline."
)
CHAT_UNAVAILABLE_MESSAGE = "Chat is unavailable right now. Please try again later."
CHAT_SUPPORT_MESSAGE = (
    "I’m really sorry you’re facing this. You don’t have to handle it alone—"
    "please reach out to someone you trust or contact one of these helplines now."
)
CHAT_RATE_LIMIT = 20
CHAT_RATE_WINDOW_SECONDS = 60
_chat_requests_by_user = defaultdict(deque)
_chat_rate_lock = threading.Lock()

app = Flask(__name__)
secret_key = os.environ.get("SESSION_SECRET")
if not secret_key:
    raise RuntimeError("SESSION_SECRET is required to start MindTrack.")

Path(app.instance_path).mkdir(parents=True, exist_ok=True)
app.config.update(
    SECRET_KEY=secret_key,
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{Path(app.instance_path) / 'mindtrack.db'}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
)
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)


class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    emotion = db.Column(db.String(20), nullable=False)
    scores_json = db.Column(db.Text, nullable=False)
    sentiment_score = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)

    @property
    def scores(self):
        return json.loads(self.scores_json)


with app.app_context():
    db.create_all()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def prepare_request():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    user_id = session.get("user_id")
    g.user = db.session.get(User, user_id) if user_id else None
    if request.method == "POST":
        sent_token = request.headers.get(
            "X-CSRF-Token", request.form.get("csrf_token", "")
        )
        if not secrets.compare_digest(session["_csrf_token"], sent_token):
            abort(400, description="Your form expired. Refresh the page and try again.")


@app.context_processor
def template_values():
    return {
        "csrf_token": session.get("_csrf_token", ""),
        "demo_mode": not bool(HF_API_TOKEN),
        "active_user": g.get("user"),
        "current_date": datetime.utcnow(),
    }


def score_with_keywords(text):
    words = {
        "anger": (
            "angry", "anger", "furious", "annoyed", "irritated", "mad", "hate",
            "frustrated", "rage",
        ),
        "disgust": (
            "disgusted", "gross", "revolting", "nauseating", "repulsed",
        ),
        "fear": (
            "afraid", "anxious", "scared", "fear", "worried", "panic", "nervous",
            "terrified", "unsafe",
        ),
        "joy": (
            "happy", "joy", "grateful", "excited", "love", "great", "hopeful",
            "peaceful", "proud", "good",
        ),
        "sadness": (
            "sad", "lonely", "down", "cry", "empty", "tired", "heartbroken",
            "miserable", "hopeless", "upset",
        ),
        "surprise": (
            "surprised", "unexpected", "amazed", "shocked", "astonished",
        ),
    }
    lowered = text.lower()
    counts = {
        emotion: sum(
            len(re.findall(r"(?<!\w)" + re.escape(word) + r"(?!\w)", lowered))
            for word in terms
        )
        for emotion, terms in words.items()
    }
    raw = {emotion: 0.08 + 0.78 * count for emotion, count in counts.items()}
    raw["neutral"] = 0.62 if not any(counts.values()) else 0.12
    total = sum(raw.values())
    return {emotion: raw[emotion] / total for emotion in EMOTIONS}


def parse_model_scores(response_data):
    if isinstance(response_data, list) and response_data:
        if isinstance(response_data[0], list):
            response_data = response_data[0]
    if not isinstance(response_data, list):
        raise ValueError("Unexpected emotion model response.")

    result = {emotion: 0.0 for emotion in EMOTIONS}
    for item in response_data:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip().lower()
        if label in result:
            result[label] = max(0.0, float(item.get("score", 0)))
    total = sum(result.values())
    if total <= 0:
        raise ValueError("Emotion model returned no recognized labels.")
    return {emotion: result[emotion] / total for emotion in EMOTIONS}


def detect_emotions(text):
    if not HF_API_TOKEN:
        return score_with_keywords(text), True

    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    for attempt in range(2):
        try:
            response = requests.post(
                HF_ENDPOINT,
                headers=headers,
                json={"inputs": text},
                timeout=20,
            )
            response.raise_for_status()
            return parse_model_scores(response.json()), False
        except (requests.RequestException, ValueError, TypeError, KeyError):
            if attempt == 1:
                break
    return score_with_keywords(text), True


def sentiment_for(scores):
    score = scores["joy"] - sum(
        scores[emotion] for emotion in ("anger", "disgust", "fear", "sadness")
    )
    if score > 0.2:
        label = "Positive"
    elif score < -0.2:
        label = "Negative"
    else:
        label = "Neutral"
    return round(max(-1.0, min(1.0, score)), 4), label


def is_distress(text, scores):
    return matches_distress_phrase(text) or (
        scores.get("sadness", 0) + scores.get("fear", 0) > 0.8
    )


def load_helplines():
    with (BASE_DIR / "helplines.json").open(encoding="utf-8") as file:
        return json.load(file)


def chat_rate_limited(user_id, now=None):
    now = time.monotonic() if now is None else now
    cutoff = now - CHAT_RATE_WINDOW_SECONDS
    with _chat_rate_lock:
        requests_for_user = _chat_requests_by_user[user_id]
        while requests_for_user and requests_for_user[0] <= cutoff:
            requests_for_user.popleft()
        if len(requests_for_user) >= CHAT_RATE_LIMIT:
            return True
        requests_for_user.append(now)
        return False


@app.get("/")
@login_required
def journal():
    recent_entry = (
        Entry.query.filter_by(user_id=g.user.id)
        .order_by(Entry.created_at.desc())
        .first()
    )
    return render_template("journal.html", result=None, recent_entry=recent_entry)


@app.post("/journal")
@login_required
def save_entry():
    text = request.form.get("text", "").strip()
    if not text:
        flash("Write a little about your day before saving.", "error")
        return render_template("journal.html", result=None, recent_entry=None), 400
    if len(text) > 3000:
        flash("Entries can be up to 3,000 characters.", "error")
        return render_template("journal.html", result=None, recent_entry=None), 400

    scores, used_demo = detect_emotions(text)
    emotion = max(scores, key=scores.get)
    sentiment_score, sentiment_label = sentiment_for(scores)
    entry = Entry(
        user_id=g.user.id,
        text=text,
        emotion=emotion,
        scores_json=json.dumps(scores),
        sentiment_score=sentiment_score,
    )
    db.session.add(entry)
    db.session.commit()

    result = {
        "entry": entry,
        "scores": scores,
        "emotion": emotion,
        "sentiment_label": sentiment_label,
        "used_demo": used_demo,
        "support": is_distress(text, scores),
    }
    return render_template(
        "journal.html",
        result=result,
        recent_entry=entry,
        helplines=load_helplines() if result["support"] else [],
    )


@app.get("/history")
@login_required
def history():
    entries = (
        Entry.query.filter_by(user_id=g.user.id)
        .order_by(Entry.created_at.desc())
        .all()
    )
    return render_template("history.html", entries=entries)


@app.get("/chat")
@login_required
def chat():
    return render_template("chat.html")


@app.post("/api/chat")
def chat_api():
    if g.user is None:
        return jsonify(error="Please log in to use chat."), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Please send a valid chat message."), 400

    user_message = payload.get("message")
    if not isinstance(user_message, str):
        return jsonify(error="Please send a valid chat message."), 400
    user_message = user_message.strip()
    if not user_message:
        return jsonify(error="Please enter a message."), 400
    if len(user_message) > 500:
        return jsonify(error="Messages can be up to 500 characters."), 400

    if chat_rate_limited(g.user.id):
        return jsonify(error="Please wait a moment before sending another message."), 429

    if matches_distress_phrase(user_message):
        helplines = load_helplines()
        helplines.sort(key=lambda line: line.get("phone") != "14416")
        return jsonify(
            reply=CHAT_SUPPORT_MESSAGE,
            distress=True,
            helplines=helplines,
        )

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return jsonify(reply=CHAT_UNAVAILABLE_MESSAGE), 503

    history = payload.get("history", [])
    if not isinstance(history, list):
        return jsonify(error="Please send a valid chat history."), 400
    context_messages = []
    for item in history[-5:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if (
            role in ("user", "assistant")
            and isinstance(content, str)
            and content.strip()
            and len(content) <= 2000
        ):
            context_messages.append({"role": role, "content": content.strip()[-512:]})

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        *context_messages,
        {"role": "user", "content": user_message},
    ]
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
                "messages": messages,
            },
            timeout=20,
        )
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Groq returned an empty response.")
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError):
        return jsonify(reply=CHAT_UNAVAILABLE_MESSAGE), 503

    return jsonify(reply=reply.strip())


@app.post("/history/<int:entry_id>/delete")
@login_required
def delete_entry(entry_id):
    entry = Entry.query.filter_by(id=entry_id, user_id=g.user.id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash("Entry deleted.", "success")
    return redirect(url_for("history"))


def load_insight_config():
    with (BASE_DIR / "insight_config.json").open(encoding="utf-8") as file:
        return json.load(file)


@app.get("/dashboard")
@login_required
def dashboard():
    days = 30 if request.args.get("days") == "30" else 7
    now = datetime.utcnow()
    first_day = datetime(now.year, now.month, now.day) - timedelta(days=days - 1)
    current_entries = (
        Entry.query.filter(
            Entry.user_id == g.user.id,
            Entry.created_at >= first_day,
            Entry.created_at <= now,
        )
        .order_by(Entry.created_at.asc())
        .all()
    )
    previous_start = first_day - timedelta(days=days)
    previous_end = first_day - timedelta(microseconds=1)
    previous_entries = Entry.query.filter(
        Entry.user_id == g.user.id,
        Entry.created_at >= previous_start,
        Entry.created_at <= previous_end,
    ).all()

    dates = [first_day + timedelta(days=offset) for offset in range(days)]
    by_date = {date.date(): [] for date in dates}
    for entry in current_entries:
        by_date.setdefault(entry.created_at.date(), []).append(entry)
    labels = [date.strftime("%b %-d") for date in dates]
    averages = [
        round(sum(item.sentiment_score for item in by_date[date.date()]) / len(by_date[date.date()]), 3)
        if by_date[date.date()]
        else None
        for date in dates
    ]

    counts = Counter(entry.emotion for entry in current_entries)
    emotion_counts = {emotion: counts.get(emotion, 0) for emotion in EMOTIONS}
    insights = []
    observed_sentiments = [value for value in averages if value is not None]
    average_sentiment = (
        round(sum(observed_sentiments) / len(observed_sentiments), 3)
        if observed_sentiments
        else None
    )
    if current_entries:
        dominant = max(EMOTIONS, key=lambda emotion: (counts[emotion], -EMOTIONS.index(emotion)))
        insights.append(
            f"Your most frequent emotion in the last {days} days was {dominant}."
        )
        current_average = sum(item.sentiment_score for item in current_entries) / len(current_entries)
        if previous_entries:
            previous_average = sum(item.sentiment_score for item in previous_entries) / len(previous_entries)
            if current_average < previous_average - 0.1:
                insights.append("Your average sentiment is lower than in the previous period.")
            elif current_average > previous_average + 0.1:
                insights.append("Your average sentiment is higher than in the previous period.")
            else:
                insights.append("Your average sentiment is close to the previous period.")
        else:
            insights.append("Keep writing over time to compare this period with the one before it.")
        config = load_insight_config()
        suggestion = config.get(dominant)
        if suggestion:
            insights.append(suggestion)
    else:
        insights = [
            f"No entries in the last {days} days yet. A few check-ins will bring your trends to life.",
            "Your journal is private to your account.",
        ]

    return render_template(
        "dashboard.html",
        days=days,
        labels=labels,
        averages=averages,
        average_sentiment=average_sentiment,
        emotion_counts=emotion_counts,
        insights=insights,
        entry_count=len(current_entries),
    )


@app.post("/demo-data")
@login_required
def load_demo_data():
    existing = Entry.query.filter_by(user_id=g.user.id, is_demo=True).first()
    if existing:
        flash("Example entries are already loaded for your account.", "success")
        return redirect(url_for("dashboard"))

    examples = [
        ("I felt grateful for a quiet morning and a good cup of tea.", "joy"),
        ("Work felt overwhelming and I was worried about the deadline.", "fear"),
        ("I felt low-energy, but a short walk helped me reset.", "sadness"),
        ("I was annoyed by a last-minute change to my plans.", "anger"),
        ("A friend surprised me with a kind message today.", "surprise"),
        ("Today was steady and ordinary, which felt just right.", "neutral"),
        ("I felt proud after finishing something I had put off.", "joy"),
        ("I was nervous before the conversation, then felt calmer.", "fear"),
        ("I missed someone today and felt a little lonely.", "sadness"),
        ("A messy commute left me frustrated for a while.", "anger"),
        ("I found a new place to read and loved the atmosphere.", "joy"),
        ("I felt peaceful after taking a break from my screen.", "neutral"),
        ("The news caught me off guard, but I am processing it.", "surprise"),
        ("I felt anxious about making the right decision.", "fear"),
        ("I laughed with my family and felt lighter afterward.", "joy"),
        ("I was disappointed when a plan did not work out.", "sadness"),
        ("A small mistake irritated me more than I expected.", "anger"),
        ("I took things one step at a time and stayed steady.", "neutral"),
        ("A thoughtful gesture made me feel appreciated.", "joy"),
        ("I felt tense this morning, but the afternoon was easier.", "fear"),
        ("It was a quiet day with no strong feelings either way.", "neutral"),
        ("I felt sad about a change, even though I know it is okay.", "sadness"),
        ("I got an unexpected chance to try something new.", "surprise"),
        ("I was frustrated, so I took a pause before responding.", "anger"),
        ("I am looking forward to spending time with people I care about.", "joy"),
        ("I worried about the week ahead and wrote down a plan.", "fear"),
        ("I enjoyed a simple meal and a slow evening.", "neutral"),
        ("I felt a little down, then checked in with a friend.", "sadness"),
        ("I finished the day feeling hopeful about tomorrow.", "joy"),
        ("Something unexpected made me smile today.", "surprise"),
    ]
    now = datetime.utcnow()
    for days_ago, (text, emotion) in enumerate(examples):
        scores = {name: 0.04 for name in EMOTIONS}
        scores[emotion] = 0.76
        remainder = (1.0 - scores[emotion]) / (len(EMOTIONS) - 1)
        for name in EMOTIONS:
            if name != emotion:
                scores[name] = remainder
        sentiment_score, _ = sentiment_for(scores)
        db.session.add(
            Entry(
                user_id=g.user.id,
                text=text,
                emotion=emotion,
                scores_json=json.dumps(scores),
                sentiment_score=sentiment_score,
                created_at=now - timedelta(days=days_ago, hours=(days_ago * 3) % 12),
                is_demo=True,
            )
        )
    db.session.commit()
    flash("30 example entries added. You can remove any of them from History.", "success")
    return redirect(url_for("dashboard"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user:
        return redirect(url_for("journal"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        if not re.fullmatch(r"[a-z0-9_.-]{3,50}", username):
            flash("Choose a username with 3–50 letters, numbers, dots, dashes, or underscores.", "error")
        elif len(password) < 8:
            flash("Your password must be at least 8 characters.", "error")
        elif User.query.filter_by(username=username).first():
            flash("That username is already in use.", "error")
        else:
            user = User(username=username, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            session.clear()
            session["user_id"] = user.id
            flash("Your private journal is ready.", "success")
            return redirect(url_for("journal"))
    return render_template("auth.html", mode="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("journal"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("The username or password did not match.", "error")
        else:
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("journal"))
    return render_template("auth.html", mode="login")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/healthz")
def health_check():
    return {"status": "ok"}, 200


@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", title="Form expired", message=error.description), 400


@app.errorhandler(404)
def not_found(_error):
    return render_template(
        "error.html",
        title="Page not found",
        message="That page or journal entry could not be found.",
    ), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
