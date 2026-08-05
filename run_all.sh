#!/usr/bin/env bash
# Full pipeline check. Run this before pushing.
#
#   ./run_all.sh          uses your .env key, generates real reports (~$0.40)
#   ./run_all.sh --mock   offline, no key, no cost
#
set -euo pipefail
cd "$(dirname "$0")"

MOCK=""
if [[ "${1:-}" == "--mock" ]]; then
  MOCK="--mock"
  export BEDTIME_PROVIDER=mock
fi

hr() { printf '\n\033[1;36m── %s\033[0m\n' "$1"; }
ok() { printf '\033[0;32m   ✓ %s\033[0m\n' "$1"; }
no() { printf '\033[0;31m   ✗ %s\033[0m\n' "$1"; exit 1; }

hr "1/9  environment"
python3 --version
if [[ -z "$MOCK" ]]; then
  if grep -q "^OPENAI_API_KEY=.*PASTE_YOUR_KEY_HERE" .env 2>/dev/null; then
    no ".env still has the placeholder key. Paste your real key on line 7."
  fi
  grep -q "^OPENAI_API_KEY=sk-" .env 2>/dev/null && ok "API key present" \
    || no "no OPENAI_API_KEY in .env (or use --mock)"
else
  ok "mock mode, no key needed"
fi

hr "2/9  dependencies"
pip install -q -r requirements.txt && ok "installed"

hr "3/9  test suite"
BEDTIME_PROVIDER=mock python -m pytest tests/ -q

hr "4/9  every module imports"
python - <<'EOF'
import glob, importlib
mods = [p[:-3].replace("/", ".") for p in glob.glob("bedtime/**/*.py", recursive=True)
        if "__init__" not in p]
for m in mods:
    importlib.import_module(m)
import main
from bedtime.config import MODEL, MODEL_SUNSET
from bedtime.prompts import PROMPT_VERSION
print(f"   {len(mods)} modules | model={MODEL} (sunset {MODEL_SUNSET}) | prompts={PROMPT_VERSION}")
EOF
ok "all import"

hr "5/9  seed library passes its own gate"
python -m bedtime.library.seed --check | tail -4

hr "6/9  covers stay in frame"
python - <<'EOF'
import io
from svgelements import SVG
from bedtime.web.covers import cover_svg, CW, CH
from bedtime.library.seed_stories import SEED_STORIES

def bounds(svg):
    doc = SVG.parse(io.StringIO(svg))
    lo_x = lo_y = 1e9; hi_x = hi_y = -1e9
    for el in doc.elements():
        try:
            b = el.bbox()
        except Exception:
            continue
        if b:
            lo_x, lo_y = min(lo_x, b[0]), min(lo_y, b[1])
            hi_x, hi_y = max(hi_x, b[2]), max(hi_y, b[3])
    return lo_x, lo_y, hi_x, hi_y

worst = 0
for e in SEED_STORIES:
    for w, h, t in [(400, 260, True), (460, 300, False), (300, 190, False)]:
        x0, y0, x1, y1 = bounds(cover_svg(e["id"], e["title"], e["category"],
                                          w, h, t, e["story"]))
        worst = max(worst, -x0, -y0, x1 - CW, y1 - CH, 0)
    root = cover_svg(e["id"], e["title"], e["category"], story=e["story"])
    root = root[:root.index(">") + 1]
    assert "%" not in root, f"{e['id']}: percent width breaks <img> sizing"
print(f"   worst overflow across 30 renders: {worst:.1f}px")
assert worst <= 2, "covers are out of frame"
EOF
ok "in frame"

hr "7/9  red team (CI gate)"
python -m bedtime.evaluation.red_team $MOCK --strict-exit | tail -3

hr "8/9  reports"
if [[ -n "$MOCK" ]]; then
  echo "   skipping calibrate/eval in mock mode (numbers would be meaningless)"
  python -m bedtime.evaluation.calibrate --mock >/dev/null && ok "calibrate runs"
  python -m bedtime.evaluation.run_eval  --mock >/dev/null && ok "eval runs"
else
  echo "   this makes real API calls, roughly \$0.40 total"
  python -m bedtime.evaluation.calibrate | tail -4
  python -m bedtime.evaluation.run_eval  | tail -3
fi
python -m bedtime.observability.dashboard >/dev/null && ok "dashboard built"

hr "9/9  secret scan"
if git ls-files 2>/dev/null | grep -q .; then
  FILES=$(git ls-files)
else
  FILES=$(find . -type f \( -name '*.py' -o -name '*.md' -o -name '*.txt' \
          -o -name '*.toml' -o -name '*.html' \) -not -path './.git/*' -not -name '.env')
fi
if echo "$FILES" | xargs grep -lE 'sk-[A-Za-z0-9_-]{20,}' 2>/dev/null | grep -q .; then
  no "an API key is in a file git can see - fix before pushing"
fi
ok "no key in anything git would commit"
grep -qx ".env" .gitignore && ok ".env is gitignored" || no ".env is NOT gitignored"

printf '\n\033[1;32m═══ all checks passed ═══\033[0m\n'
echo "Reports:   reports/"
echo "Covers:    reports/covers_preview.html"
echo "Dashboard: reports/dashboard.html"
echo
echo "Next:  git push  →  see DEPLOY.md"
