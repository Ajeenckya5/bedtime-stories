"""Public entry point for narration.

    narrator = Narrator(settings)
    result = narrator.narrate(story, title="The Lamp That Waited")
    narrator.play(result)
"""

import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..observability.metrics import METRICS
from ..observability.tracing import LOG
from .pacing import build_script
from .voice import Narration, audio_key, build_engine


class Narrator:
    def __init__(self, settings, engine=None):
        self.settings = settings
        self.engine = engine or build_engine(settings)
        self.audio_dir = Path(settings.audio_dir)

    def narrate(self, story: str, title: str = "", force: bool = False,
                trace=None):
        """Render a story to an audio file. Cached by content hash."""
        if not story or not story.strip():
            return Narration(error="nothing to narrate")

        script = build_script(story, title, base_speed=self.settings.tts_speed)
        voice = getattr(self.engine, "voice", "default")
        key = audio_key(script.text, str(voice), script.speed)
        out = self.audio_dir / f"{key}.mp3"

        if out.exists() and not force:
            METRICS.inc("tts_cache_hits_total")
            if trace is not None:
                trace.event("narration_cached", path=str(out))
            return Narration(audio_path=out, duration_estimate_s=script.est_seconds,
                             voice=str(voice), engine=self.engine.name, cached=True,
                             bytes_written=out.stat().st_size)

        # Also check for the offline engine's own formats.
        for suffix in (".aiff", ".wav"):
            alt = out.with_suffix(suffix)
            if alt.exists() and not force:
                METRICS.inc("tts_cache_hits_total")
                return Narration(audio_path=alt, duration_estimate_s=script.est_seconds,
                                 voice=str(voice), engine=self.engine.name, cached=True,
                                 bytes_written=alt.stat().st_size)

        LOG.info("narrating %r (%d segments, ~%.0fs)", title or "story",
                 script.n_segments, script.est_seconds)
        result = self.engine.synthesise(script, out)

        if trace is not None:
            trace.event("narrated", engine=result.engine, voice=result.voice,
                        seconds=result.duration_estimate_s, ok=result.ok,
                        error=result.error or "none")
        if not result.ok:
            LOG.warning("narration failed: %s", result.error)
        return result

    def play(self, narration: Narration) -> bool:
        """Play the file on this machine. Returns False if we can't."""
        if not narration.ok or narration.audio_path is None:
            return False
        path = str(narration.audio_path)
        system = platform.system()

        player = None
        if system == "Darwin":
            player = ["afplay", path]
        elif system == "Linux":
            for cmd in ("mpg123", "ffplay", "aplay", "paplay"):
                if shutil.which(cmd):
                    player = [cmd, path] if cmd != "ffplay" else \
                        [cmd, "-nodisp", "-autoexit", path]
                    break
        elif system == "Windows":
            player = ["cmd", "/c", "start", "", path]

        if not player or not shutil.which(player[0]):
            LOG.info("no audio player found - the file is at %s", path)
            return False
        try:
            subprocess.run(player, check=True, capture_output=True)
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            LOG.warning("playback failed: %s", exc)
            return False

    def cached_files(self):
        if not self.audio_dir.exists():
            return []
        return sorted(self.audio_dir.glob("*.*"), key=lambda p: -p.stat().st_mtime)

    def stats(self):
        files = self.cached_files()
        return {
            "engine": self.engine.name,
            "voice": getattr(self.engine, "voice", "default"),
            "cached_files": len(files),
            "bytes": sum(f.stat().st_size for f in files),
            "dir": str(self.audio_dir),
        }
