import os
import time
from openai import OpenAI
import db
from config import WHISPER_MODEL, LANGUAGE

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def transcribe(wav_buf):
    """Send WAV buffer to Whisper API. Returns (text, duration_s) or (None, 0)."""
    if wav_buf is None:
        return None, 0
    t0 = time.time()
    try:
        settings = db.get_settings()
        language = settings.get("language", LANGUAGE)
        result = get_client().audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=wav_buf,
            language=language,
        )
        duration_s = round(time.time() - t0, 2)
        text = result.text.strip()
        return (text, duration_s) if text else (None, 0)
    except Exception as e:
        print(f"[wispr] transcription error: {e}")
        return None, 0
