import os
import time
from openai import OpenAI
import db
from config import WHISPER_MODEL, LANGUAGE

_client = None

_CLEANUP_PROMPT = """Clean up this voice transcription. Rules:
- Remove filler words: um, uh, er, like, you know, sort of, kind of, basically, literally, right
- Remove repeated words or phrases (e.g. "I want I want to" → "I want to")
- Fix homophones based on context (their/there/they're, to/too/two, etc.)
- Fix obvious transcription errors based on context
- Keep the meaning and tone exactly the same
- Do NOT add punctuation that wasn't implied, do NOT rephrase or summarise
- Return only the cleaned text, nothing else

Transcription: """


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
        raw = result.text.strip()
        if not raw:
            return None, 0
        print(f"[wispr] transcript: {repr(raw)}", flush=True)
        return raw, duration_s
    except Exception as e:
        print(f"[wispr] transcription error: {e}")
        return None, 0


def _cleanup(text):
    """Use GPT-4o-mini to strip fillers, repetitions and fix homophones."""
    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": _CLEANUP_PROMPT + text}],
            max_tokens=500,
            temperature=0,
        )
        cleaned = response.choices[0].message.content.strip()
        return cleaned if cleaned else text
    except Exception as e:
        print(f"[wispr] cleanup error: {e}", flush=True)
        return text  # fall back to raw transcript
