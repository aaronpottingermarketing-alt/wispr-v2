import io
import wave
import threading
import numpy as np
import sounddevice as sd
from config import SAMPLE_RATE, CHANNELS


class Recorder:
    def __init__(self):
        self._frames = []
        self._lock = threading.Lock()
        self._stream = None

    def start(self):
        self._frames = []
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as e:
            print(f"[wispr] mic unavailable: {e}", flush=True)
            self._stream = None

    def _callback(self, indata, frames, time, status):
        with self._lock:
            self._frames.append(indata.copy())

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return self._to_wav_bytes()

    def _to_wav_bytes(self):
        with self._lock:
            if not self._frames:
                return None
            audio = np.concatenate(self._frames, axis=0)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        buf.seek(0)
        buf.name = "audio.wav"  # openai SDK needs a name attribute
        return buf
