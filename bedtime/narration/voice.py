"""Text to audio.

Same shape as the LLM provider layer: a protocol, a real implementation, and an
offline fallback so nothing breaks without a key.
  OpenAITTS   gpt-4o-mini-tts. Costs about a cent per story. Voice defaults to
"""

import hashlib
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol

from ..observability.metrics import METRICS
from ..observability.tracing import LOG
from .pacing import NarrationScript, split_for_tts

# Warm, unhurried voices first. Ordered by how well they suit a sleepy child.
OPENAI_VOICES = ("nova", "shimmer", "alloy", "fable", "echo", "onyx")


@dataclass
class Narration:
    audio_path: Optional[Path] = None
    duration_estimate_s: float = 0.0
    voice: str = ""
    engine: str = ""
    cached: bool = False
    bytes_written: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.audio_path is not None and not self.error


class TTSEngine(Protocol):
    name: str

    def synthesise(self, script: NarrationScript, out_path: Path) -> Narration: ...


def audio_key(text: str, voice: str, speed: float):
    material = f"{voice}|{speed:.2f}|{text}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


class OpenAITTS:
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini-tts",
                 voice: str = "nova", base_url: str = "", timeout: float = 60.0):
        self.model = model
        self.voice = voice if voice in OPENAI_VOICES else "nova"
        self._client = None
        try:
            import openai

            kwargs = {"api_key": api_key, "timeout": timeout, "max_retries": 2}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = openai.OpenAI(**kwargs)
        except Exception as exc:
            LOG.warning("openai tts unavailable: %s", exc)

    def synthesise(self, script: NarrationScript, out_path: Path) -> Narration:
        if self._client is None:
            return Narration(error="openai client unavailable", engine=self.name)

        chunks = split_for_tts(script.text)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # One chunk is the common case; longer stories get concatenated.
            # Raw MP3 frames concatenate cleanly enough for playback, and
            # avoiding a ffmpeg dependency is worth the slight imprecision.
            # NOTE: concatenating raw mp3 frames. Works for playback but the
            # duration metadata is wrong on multi-chunk files. ffmpeg would fix
            # it properly, not worth the dependency yet.
            with out_path.open("wb") as fh:
                for i, chunk in enumerate(chunks):
                    resp = self._client.audio.speech.create(
                        model=self.model,
                        voice=self.voice,
                        input=chunk,
                        speed=script.speed,
                        response_format="mp3",
                        instructions=script.instructions,
                    )
                    fh.write(resp.content)
                    METRICS.inc("tts_calls_total", engine=self.name)
                    LOG.debug("tts chunk %d/%d written", i + 1, len(chunks))

            size = out_path.stat().st_size
            METRICS.add("tts_bytes_total", size, engine=self.name)
            return Narration(audio_path=out_path, duration_estimate_s=script.est_seconds,
                             voice=self.voice, engine=self.name, bytes_written=size)
        except TypeError:
            # Older SDKs reject `instructions`. Retry without it rather than
            # failing - the pacing markup still does most of the work.
            return self._synthesise_plain(script, out_path, chunks)
        except Exception as exc:
            METRICS.inc("tts_errors_total", engine=self.name, error=type(exc).__name__)
            return Narration(error=str(exc)[:200], engine=self.name)

    def _synthesise_plain(self, script, out_path, chunks):
        try:
            with out_path.open("wb") as fh:
                for chunk in chunks:
                    resp = self._client.audio.speech.create(
                        model=self.model, voice=self.voice, input=chunk,
                        speed=script.speed, response_format="mp3")
                    fh.write(resp.content)
            size = out_path.stat().st_size
            return Narration(audio_path=out_path, duration_estimate_s=script.est_seconds,
                             voice=self.voice, engine=self.name, bytes_written=size)
        except Exception as exc:
            METRICS.inc("tts_errors_total", engine=self.name, error=type(exc).__name__)
            return Narration(error=str(exc)[:200], engine=self.name)


class SystemTTS:
    """Offline fallback. macOS `say`, else pyttsx3, else nothing."""
    name = "system"

    def __init__(self, voice: str = ""):
        self.voice = voice
        self._say = shutil.which("say") if platform.system() == "Darwin" else None

    @property
    def available(self) -> bool:
        if self._say:
            return True
        try:
            import pyttsx3  # noqa: F401
            return True
        except ImportError:
            return False

    def synthesise(self, script: NarrationScript, out_path: Path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # `say` writes AIFF, not MP3.
        aiff = out_path.with_suffix(".aiff")

        if self._say:
            try:
                # ~175 wpm is `say`'s default; scale by our speed factor.
                rate = str(int(175 * script.speed))
                cmd = [self._say, "-r", rate, "-o", str(aiff)]
                if self.voice:
                    cmd += ["-v", self.voice]
                subprocess.run(cmd + [script.text], check=True, capture_output=True,
                               timeout=180)
                METRICS.inc("tts_calls_total", engine=self.name)
                return Narration(audio_path=aiff, duration_estimate_s=script.est_seconds,
                                 voice=self.voice or "system", engine=self.name,
                                 bytes_written=aiff.stat().st_size)
            except (subprocess.SubprocessError, OSError) as exc:
                return Narration(error=f"say failed: {exc}"[:200], engine=self.name)

        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", int(175 * script.speed))
            engine.save_to_file(script.text, str(out_path.with_suffix(".wav")))
            engine.runAndWait()
            wav = out_path.with_suffix(".wav")
            return Narration(audio_path=wav, duration_estimate_s=script.est_seconds,
                             voice="system", engine=self.name,
                             bytes_written=wav.stat().st_size if wav.exists() else 0)
        except ImportError:
            return Narration(error="no offline TTS available (macOS `say` or pyttsx3)",
                             engine=self.name)
        except Exception as exc:
            return Narration(error=str(exc)[:200], engine=self.name)


def build_engine(settings) -> TTSEngine:
    if settings.tts_engine == "system":
        return SystemTTS(voice=settings.tts_system_voice)
    if settings.api_key:
        return OpenAITTS(api_key=settings.api_key, model=settings.tts_model,
                         voice=settings.tts_voice, base_url=settings.base_url,
                         timeout=settings.request_timeout_s)
    LOG.info("no API key - narration falling back to the system voice")
    return SystemTTS(voice=settings.tts_system_voice)
