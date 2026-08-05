# Deploying to Streamlit Community Cloud

Takes about two minutes. I can't do it for you — Streamlit Cloud needs GitHub
OAuth through their web UI, there's no API.

## Before you start: read this bit

**A public URL with your OpenAI key behind it is a live billing risk.** Anyone
who finds the link spends your credit. Three things protect you, and you should
use all three:

1. **Set `APP_PASSWORD`** in secrets. The app shows a password screen and stops
   dead without it. This is the important one.
2. **Set a low daily cap.** `BEDTIME_MAX_USD_PER_DAY = "5.00"` means the worst
   case is five dollars, not five hundred.
3. **Set a usage limit on the OpenAI side too.** Platform → Settings → Limits →
   hard cap. Belt and braces, because the app's cap is per-process and Streamlit
   can restart.

If you'd rather not risk it at all, deploy with `BEDTIME_PROVIDER = "mock"`. The
shelf, the covers, the reading room and the quality panel all work; the stories
are canned. That's a perfectly good demo for a submission link.

## Steps

**1. Push to GitHub**

```bash
cd ~/Downloads/"AI Agent Deployment Engineer Takehome"
git init
git add -A
git diff --cached --name-only | grep -x ".env" && echo "STOP: .env staged"
git diff --cached -U0 | grep -E "sk-[A-Za-z0-9_-]{20,}" && echo "STOP: key staged"
git commit -m "Bedtime story engine"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/bedtime-stories.git
git push -u origin main
```

Run `./run_all.sh --mock` first. It scans the working tree for `sk-` followed by
20+ key characters and separately confirms `.env` is in `.gitignore`. `make
check` does the scan but not the gitignore check, so it can pass on a repo that
is about to commit a key.

**2. Deploy**

- Go to <https://share.streamlit.io> and sign in with GitHub
- **Create app** → **Deploy a public app from a repo**
- Repository: your repo · Branch: `main` · Main file path: `app.py`
- Click **Advanced settings** *before* deploying and paste your secrets:

```toml
OPENAI_API_KEY = "sk-proj-..."
APP_PASSWORD = "pick-something"
BEDTIME_PROVIDER = "openai"
BEDTIME_MAX_USD_PER_DAY = "5.00"
BEDTIME_MAX_USD_PER_RUN = "0.10"
BEDTIME_JUDGE_SAMPLES = "2"
```

- **Deploy**. First build takes 2–4 minutes.

`BEDTIME_JUDGE_SAMPLES = "2"` is worth it on a hosted deploy: it cuts a third
off the cost and most of the latency, and the score gets a little noisier. Fine
for a demo, not for calibration.

## What to expect

Streamlit Cloud's free tier gives you ~1 GB RAM and sleeps the app after a few
days of no traffic — it wakes on the next visit, taking ~30 seconds. Fine for a
portfolio link.

The SQLite files (`data/memory.sqlite3`, `data/cache.sqlite3`) and generated
audio live on ephemeral disk. **They vanish on every redeploy or wake-up.** So
story memory and the audio cache work within a session and reset between them.
That's acceptable here; making it durable means Postgres and S3, which is a
different project.

## Local run

```bash
pip install -r requirements.txt
cp .env.example .env         # add your key
streamlit run app.py
```

Opens on <http://localhost:8501>. No password prompt locally unless you set
`APP_PASSWORD`.

## If something breaks

**Blank page / "Oh no."** — check the logs in the Streamlit Cloud panel
(bottom right, "Manage app"). Usually a missing dependency; add it to
`requirements.txt` and push.

**"No API key — offline demo"** — `OPENAI_API_KEY` didn't reach the app. Check
it's in the Secrets box with quotes around the value, and reboot the app from
the Manage panel.

**Stories are slow** — that's real: 7–10 model calls at ~2s each. Drop
`BEDTIME_JUDGE_SAMPLES` to 2 and `BEDTIME_MAX_REVISIONS` to 1.

**Audio doesn't play** — the free tier has no `ffmpeg`, but we don't need it
(OpenAI returns MP3 directly). If TTS fails it degrades to a warning and the
text still shows. Check the daily budget hasn't been hit.
