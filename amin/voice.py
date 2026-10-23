"""Speech to text for voice mode, on this machine (Whisper via MLX).

    general    whisper-large-v3-turbo: English, Arabic, and language detection
    Malayalam  whisper-medium-malayalam (VRC-LC's fine-tune, Apache-2.0): the
               general model's Malayalam is weak, so Malayalam speech is
               re-run through the specialist

Audio arrives as whatever the browser recorded (webm/opus, mp4/aac, wav) and
is decoded by ffmpeg. Nothing is sent anywhere: Chrome's built-in speech
recognition was not used because it uploads audio to Google.

    uv sync --extra voice    # then models download on first use, or:
    make voice-models
"""

from __future__ import annotations

import re
import tempfile
import threading
from pathlib import Path

from .config import settings

_lock = threading.Lock()  # one transcription at a time: they share the GPU with answering
SUFFIXES = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3",
            "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/aac": ".aac"}


class VoiceUnavailable(RuntimeError):
    pass


def _model(path: Path, repo: str) -> str:
    return str(path) if path.exists() else repo


def transcribe(audio: bytes, content_type: str = "audio/webm", lang: str | None = None,
               prompt: str | None = None) -> dict:
    """{"text": ..., "lang": "en" | "ar" | "ml" | ...}. `lang` is a hint; None detects it.
    `prompt` primes Whisper's vocabulary (used for the wake phrase)."""
    try:
        import mlx_whisper
    except ImportError as exc:  # optional extra
        raise VoiceUnavailable("voice mode needs: uv sync --extra voice") from exc
    suffix = SUFFIXES.get(content_type.split(";")[0].strip(), ".webm")
    general = _model(settings.whisper_model, "mlx-community/whisper-large-v3-turbo")
    malayalam = _model(settings.whisper_ml_model, "mlx-community/whisper-medium-malayalam-mlx")
    with tempfile.NamedTemporaryFile(suffix=suffix) as f, _lock:
        f.write(audio)
        f.flush()
        if lang == "ml":
            result = mlx_whisper.transcribe(f.name, path_or_hf_repo=malayalam, language="ml", initial_prompt=prompt)
        else:
            result = mlx_whisper.transcribe(f.name, path_or_hf_repo=general, language=lang, initial_prompt=prompt)
            if result.get("language") == "ml":
                result = mlx_whisper.transcribe(f.name, path_or_hf_repo=malayalam, language="ml",
                                                initial_prompt=prompt)
    return {"text": " ".join(result.get("text", "").split()), "lang": result.get("language") or lang or ""}


# -- wake word ---------------------------------------------------------------
#
# "Hey Amin" without a trained wake-word model: the browser sends only short
# bursts of speech, and a small Whisper checks whether one starts with Amin's
# name. Ready-made wake-word models (openWakeWord's) are licensed
# non-commercial, and Whisper is MIT. The name must come first, alone or after
# a greeting, so "Amina called" and "I mean it" do not wake it (E37).

WAKE = re.compile(
    r"^[\W_]*(?:(?:hey|hi|hello|ok(?:ay)?|يا|ഹേ|ഹായ്)[\s,،]*)?"
    r"(?:a{1,2}mee?n|amine?|أمين|امين|അമീൻ|ആമിൻ|അമിൻ|അമീന്)(?![\w])[\s,،.!?؟]*",
    re.IGNORECASE,
)


WAKE_PROMPT = "Amin, Hey Amin, يا أمين, ഹേ അമീൻ."
# For the full re-transcription: the name in one script only. The mixed prompt
# tipped an Arabic clip into the Malayalam model.
NAME_IN = {"en": "Hey Amin.", "ar": "يا أمين.", "ml": "ഹേ അമീൻ."}


def wake(audio: bytes, content_type: str = "audio/webm") -> dict:
    """{"wake": bool, "rest": what followed the name, "text": the whole clip}."""
    try:
        import mlx_whisper
    except ImportError as exc:
        raise VoiceUnavailable("voice mode needs: uv sync --extra voice") from exc
    suffix = SUFFIXES.get(content_type.split(";")[0].strip(), ".webm")
    small = _model(settings.whisper_wake_model, "mlx-community/whisper-base-mlx")
    with tempfile.NamedTemporaryFile(suffix=suffix) as f, _lock:
        f.write(audio)
        f.flush()
        # Whisper does not know the name: unprimed it hears "Hey, I'm in". Priming
        # with it in all three scripts took synthetic clips from 1/6 to 6/6 woken,
        # with 1 of 5 near misses ("Amina called earlier") also waking it (E37).
        heard = mlx_whisper.transcribe(f.name, path_or_hf_repo=small, initial_prompt=WAKE_PROMPT)
    text, lang = " ".join(heard.get("text", "").split()), heard.get("language")
    m = WAKE.match(text)
    if not m:
        return {"wake": False, "rest": "", "text": text}
    rest = text[m.end():].strip()
    if rest:
        # The small model only has to catch the name. A question after it is
        # what will be answered, so it gets the full models: base garbled
        # "يا أمين، متى ينتهي العقد؟" into "ما تاياً تهي العقل".
        hint = lang if lang in NAME_IN else None
        full = transcribe(audio, content_type, lang=hint, prompt=NAME_IN.get(hint, "Hey Amin."))["text"]
        m2 = WAKE.match(full)
        rest = full[m2.end():].strip() if m2 else full
    return {"wake": True, "rest": rest, "text": text}
