"""Транскрибація голосових повідомлень через faster-whisper."""
import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("core.voice")

_model = None

def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log.info("Завантажую Whisper модель...")
        _model = WhisperModel("base", device="cpu", compute_type="int8")
        log.info("Whisper готовий")
    return _model

def transcribe(ogg_path: str) -> str:
    """Конвертує .ogg → .wav і транскрибує. Повертає текст."""
    wav_path = ogg_path.replace(".ogg", ".wav")
    try:
        # конвертація через ffmpeg
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, timeout=30
        )
        if result.returncode != 0:
            log.error(f"ffmpeg помилка: {result.stderr.decode()}")
            return ""

        model = _get_model()
        segments, info = model.transcribe(wav_path, language="uk", beam_size=1)
        text = " ".join(s.text.strip() for s in segments).strip()
        log.info(f"Транскрибовано ({info.language}): {text}")
        return text

    except Exception as e:
        log.error(f"Помилка транскрибації: {e}")
        return ""
    finally:
        for p in [ogg_path, wav_path]:
            try:
                os.unlink(p)
            except Exception:
                pass
