# MindTrack

MindTrack is a small, private daily journal that highlights the emotion and sentiment in each check-in, shows mood trends, and offers support resources when an entry may signal distress. It is a college-project MVP, not a medical product.

## Run it

1. Install Python 3.11 or newer.
2. Install dependencies with `pip install -r requirements.txt`. For local development, `uv sync` is also available from `pyproject.toml`.
3. Set `SESSION_SECRET` to a long random value before starting the server.
4. Optionally set `HF_API_TOKEN` to enable Hugging Face Inference API emotion scoring. If it is missing or the service is unavailable, MindTrack uses its local keyword-based demo scorer.
5. Optionally set `EMOTION_MODEL`; the default is `j-hartmann/emotion-english-distilroberta-base`.
6. Optionally set `GROQ_API_KEY` to enable the Chat Check-in. Without it, the rest of MindTrack still works and chat displays an unavailable message.
7. Optionally set `GROQ_MODEL`; the default is `openai/gpt-oss-120b`.
8. Run `python main.py` and open `http://localhost:5000`.

In Replit, use the **MindTrack** workflow. SQLite data is stored in `instance/mindtrack.db`.

## Deploy on Heroku

For a GitHub-connected Heroku deploy, connect this repository in the app's **Deploy** tab and deploy the selected branch. The root `app.json` declares Heroku-24, the Python buildpack, and default Config Vars for provisioning and Review Apps. This path uses `.python-version`, `requirements.txt`, and the existing `Procfile`. `requirements.txt` is the deployment dependency manifest; do not add a second Python lockfile alongside it.

Before deploying, set `SESSION_SECRET` to a long random value in the app's Config Vars and set `COOKIE_SECURE` to `1`. Add `HF_API_TOKEN` only if you want emotion scoring through Hugging Face. The existing `Procfile` remains available for Heroku's Python buildpack deployment path.

The root `heroku.yml` and `Dockerfile` are an alternative container-stack deployment path; they are not used by the current Heroku-24 buildpack deploy. To use that path, set the app stack to `container` and deploy through Heroku Git as described in Heroku's [Docker manifest guide](https://devcenter.heroku.com/articles/build-docker-images-heroku-yml).

Heroku dynos have an ephemeral filesystem. MindTrack's SQLite database stores account and journal data on that filesystem, so use this deployment only for demos; records can disappear when a dyno restarts or redeploys. Use a persistent database before keeping real journals.

Heroku dynos are paid. Check the [current Heroku pricing](https://www.heroku.com/pricing) before creating or scaling the app. This workspace is not connected to a Heroku account, so these files prepare the app but do not create a live Heroku service.

## Deploy on Render

The root `render.yaml` is a Render Blueprint for the free web-service tier. Connect this repository in Render and deploy the Blueprint. Render generates `SESSION_SECRET` automatically; emotion scoring uses the local keyword fallback unless you add `HF_API_TOKEN` under the service's environment settings.

The free tier has an ephemeral filesystem and no persistent disk. Because MindTrack stores accounts and journal entries in SQLite, those records can be lost when the service restarts, sleeps, or redeploys. Use this setup for demos only; choose persistent storage before keeping real journals.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `SESSION_SECRET` | Yes | Signs Flask sessions. Keep it private; do not commit it. |
| `HF_API_TOKEN` | No | Enables emotion scoring through Hugging Face. Entry text is sent to Hugging Face when this is configured. |
| `EMOTION_MODEL` | No | Hugging Face model ID; defaults to `j-hartmann/emotion-english-distilroberta-base`. |
| `GROQ_API_KEY` | No | Enables Chat Check-in through Groq. Chat text and up to five previous chat messages are sent to Groq after the local distress check; journal entries are never sent. |
| `GROQ_MODEL` | No | Groq model ID; defaults to `openai/gpt-oss-120b`. |
| `PORT` | No | Server port; defaults to `5000`. |
| `COOKIE_SECURE` | No | Set to `1` when serving over HTTPS to require secure session cookies. |

## Pages

- **Journal** — write up to 3,000 characters, save a check-in, and see its emotion scores and sentiment label.
- **Insights** — see average daily sentiment and emotion counts for the last 7 or 30 days, plus fixed rule-based observations.
- **Past entries** — read entries newest-first and delete individual entries.
- **Chat Check-in** — have a short conversation with a supportive AI companion. The transcript stays in the current browser tab's session storage and is not saved to the journal or server.
- **Sign up / log in** — hashed passwords and account-scoped entries.

The Insights page includes a CSRF-protected button to load 30 example entries. Example entries can be deleted from Past entries.

## Privacy and support

Journal text is stored in the local SQLite database for this app. When `HF_API_TOKEN` is configured, the text of an entry is sent to Hugging Face for emotion scoring. Without a token, scoring uses a local keyword fallback. Journal text is not written to application logs.

Chat messages are processed by Groq when `GROQ_API_KEY` is configured. Before a message is sent, MindTrack checks its local distress phrase list and shows support resources instead of calling Groq when a phrase matches. Chat history is held in browser session storage, is not written to the database or application logs, and is limited to 20 messages per minute per signed-in user. Chat is unavailable when no Groq key is configured.

The distress phrase list lives in `distress_keywords.py`, and support phone lines are in `helplines.json`. These checks are not a diagnosis. MindTrack always displays: “MindTrack is not a medical tool and not a substitute for professional help.”
