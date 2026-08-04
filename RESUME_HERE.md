# Done — start at README.md

This file was the mid-build checkpoint. The build is finished; you can delete it.

**Read [README.md](README.md) first.** Then:

- [BUILD_GUIDE.md](BUILD_GUIDE.md) — build it yourself, milestone by milestone
- [docs/block_diagram.svg](docs/block_diagram.svg) — the system diagram
- [docs/DESIGN_NOTES.md](docs/DESIGN_NOTES.md) — decisions and known weaknesses
- [reports/](reports/) — calibration, evaluation, safety

## One thing before you submit

The three reports in `reports/` were generated with `--mock` and carry a banner
saying so. Add your key and regenerate them so they contain real numbers:

```bash
cp .env.example .env      # paste your OPENAI_API_KEY
make reports              # ~5 min, roughly $0.30
```

Then check `reports/CALIBRATION_REPORT.md` — if the recommended threshold differs
from the current 82, set `BEDTIME_ACCEPT_THRESHOLD` in `.env` to match and note it.

Remove `.env` before you zip anything up. `make check` greps for a key and fails
the build if it finds one.
