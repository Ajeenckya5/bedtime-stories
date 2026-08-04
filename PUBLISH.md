# Publishing: git, then Streamlit

Copy-paste in order. Roughly ten minutes end to end.

---

## Step 0 — revoke the old key first

The key currently in `.env` has been shared outside your machine. Before you do
anything else:

1. <https://platform.openai.com/api-keys>
2. Find it, click **Revoke**
3. **Create new secret key**, copy it
4. Open `.env` and replace line 7 with the new one

Takes 30 seconds. Skipping it means publishing with a key someone else may have.

---

## Step 1 — run the full pipeline

```bash
cd ~/Downloads/"AI Agent Deployment Engineer Takehome"
./run_all.sh --mock
```

Nine stages: tests, imports, seed gate, cover bounds, red team, reports, and a
secret scan that also confirms `.env` is gitignored. Use this rather than
`make check` — `make check` skips the `.gitignore` verification, which is the
one that stops a key reaching GitHub.

Everything must print green before you go on.

---

## Step 2 — set git up

Skip if you've used git on this machine before.

```bash
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

Without these, `git commit` stops with *"Please tell me who you are"*.

---

## Step 3 — stage, then check what you staged

```bash
git init
git add -A
```

**Stop here — do not commit yet.** This is the only moment the check is worth
anything: the staging area now holds the exact bytes that will go to GitHub.

```bash
git diff --cached --name-only | grep -x ".env" && echo "STOP: .env is staged" || echo "ok: .env not staged"
```

```bash
git diff --cached -U0 | grep -E "sk-[A-Za-z0-9_-]{20,}" && echo "STOP: key found" || echo "ok: no key staged"
```

Both must print `ok:`. If either says `STOP`, run `git rm --cached .env`, confirm
`.env` is on its own line in `.gitignore`, and re-run.

> The second command greps for `sk-` **followed by 20+ key characters**. A bare
> `grep "sk-"` matches eight documentation files in this repo — `PUBLISH.md`,
> `Makefile`, `.env.example` and others all contain the literal text `sk-proj-`
> as an example. A check that cries wolf on a clean repo is a check you'll learn
> to ignore.

---

## Step 4 — commit and push

```bash
git commit -m "Bedtime story engine: planner, LLM judge, guardrails, narration, web app"
git branch -M main
```

Now make an empty repo at <https://github.com/new> — **no** README, **no**
.gitignore, they'll conflict. Then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/bedtime-stories.git
git push -u origin main
```

If it asks for a password, GitHub wants a token, not your account password:
Settings → Developer settings → Personal access tokens → Tokens (classic) →
Generate new → tick `repo` → use that as the password.

### If a key does get pushed

Deleting the file and pushing again does **not** help — it stays in history and
is retrievable. Do this instead, in order:

1. **Revoke the key immediately** at <https://platform.openai.com/api-keys>.
   This is the step that actually protects you. The rest is tidying.
2. Delete the GitHub repo, `rm -rf .git`, and start from Step 3.

---

## Step 5 — deploy to Streamlit

1. <https://share.streamlit.io> → sign in with GitHub
2. **Create app** → **Deploy a public app from a repo**
3. Repository `YOUR_USERNAME/bedtime-stories` · Branch `main` · Main file `app.py`
4. Click **Advanced settings** *before* hitting deploy
5. Paste into the **Secrets** box:

```toml
OPENAI_API_KEY = "sk-proj-your-new-key"
APP_PASSWORD = "something-you-choose"
BEDTIME_PROVIDER = "openai"
BEDTIME_MAX_USD_PER_DAY = "5.00"
BEDTIME_MAX_USD_PER_RUN = "0.10"
BEDTIME_JUDGE_SAMPLES = "2"
```

6. **Deploy**. First build is 2–4 minutes.

### Or deploy with no key at all

If you'd rather not put a live key on a public URL — and for a submission link
I'd suggest not — use just this:

```toml
BEDTIME_PROVIDER = "mock"
```

Everything visual works: the shelf, the covers, the reading room, the voice
picker, the quality panel, the guardrail refusals. Only the story text is canned.
Zero billing risk, nothing to revoke later.

---

## Why the password matters

A public Streamlit URL with your key behind it means **anyone who finds the link
spends your money**. Three layers, use all of them:

| Layer | What it does |
|---|---|
| `APP_PASSWORD` | app stops dead at a password screen. The important one. |
| `BEDTIME_MAX_USD_PER_DAY` | in-app cap. Per-process, so a restart resets it. |
| OpenAI usage limit | Platform → Settings → Limits → hard cap. The real backstop. |

---

## Updating after a change

```bash
git add -A && git commit -m "what changed" && git push
```

Streamlit redeploys automatically within a minute or so.

---

## Known limits of the free tier

- **Sleeps** after a few days idle; wakes in ~30s on the next visit.
- **Ephemeral disk.** `data/*.sqlite3` and generated audio vanish on every
  redeploy or wake. Story memory and the audio cache work within a session and
  reset between them. Fine for a demo; durable would mean Postgres and S3.
- **~1 GB RAM.** Plenty here.

## If it breaks

**"Oh no." / blank page** — Manage app → logs, bottom right. Usually a missing
dependency; add it to `requirements.txt` and push.

**Sidebar says "No API key — offline demo"** — the secret didn't land. Check it's
in the Secrets box *with quotes*, then Reboot from the Manage panel.

**Stories take 30 seconds** — that's real, it's 7–10 model calls. Drop
`BEDTIME_JUDGE_SAMPLES` to 2 and `BEDTIME_MAX_REVISIONS` to 1.

**Audio button does nothing** — check the daily budget hasn't been hit. TTS
failures degrade to a warning; the text always still shows.
