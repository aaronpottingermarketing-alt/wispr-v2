import os
import sys
import time
import traceback
import threading
import webbrowser
import rumps
from dotenv import load_dotenv
from AppKit import NSWorkspace, NSEvent, NSEventMaskFlagsChanged, NSEventModifierFlagOption
import ApplicationServices as AX

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

_LOG = os.path.join(os.path.dirname(__file__), "wispr.log")

def _log_crash(msg):
    try:
        with open(_LOG, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

def _excepthook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _log_crash(f"[wispr] CRASH (main thread):\n{msg}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)

def _thread_excepthook(args):
    msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    _log_crash(f"[wispr] CRASH (thread {args.thread.name}):\n{msg}")

sys.excepthook = _excepthook
threading.excepthook = _thread_excepthook

from config import DASHBOARD_PORT
from recorder import Recorder
from transcriber import transcribe
from injector import inject
from overlay import show_recording, hide_recording, read_command
import db
import server

ICON_IDLE = "🎙"
ICON_REC  = "🔴"
ICON_BUSY = "⏳"

RIGHT_OPTION_KEYCODE = 61


class WisprLocal(rumps.App):
    def __init__(self):
        super().__init__(ICON_IDLE, quit_button=None)
        self.menu = [
            rumps.MenuItem("Wispr Local", callback=None),
            rumps.MenuItem("Open Dashboard", callback=self._open_dashboard),
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]
        self._recorder      = Recorder()
        self._recording     = False
        self._lock          = threading.Lock()
        self._monitor       = None
        self._target_app    = None
        self._record_start  = 0.0

        server.start_server(port=DASHBOARD_PORT)
        rumps.Timer(self._setup_listener, 0.5).start()

    # ── Listener ──────────────────────────────────────────────────────────────

    def _setup_listener(self, sender):
        sender.stop()
        try:
            AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: True})

            def handler(event):
                if event.keyCode() != RIGHT_OPTION_KEYCODE:
                    return
                held = bool(event.modifierFlags() & NSEventModifierFlagOption)
                with self._lock:
                    if held and not self._recording:
                        self._recording  = True
                        # Safe — NSWorkspace imported at module level
                        self._target_app = NSWorkspace.sharedWorkspace().frontmostApplication()
                        threading.Thread(target=self._begin_recording, daemon=True).start()
                    elif not held and self._recording:
                        self._recording = False
                        threading.Thread(target=self._finish_recording, daemon=True).start()

            self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskFlagsChanged, handler
            )
            print("[wispr] hotkey listener ready", flush=True)
            rumps.Timer(self._check_overlay_cmd, 0.1).start()

        except Exception as e:
            print(f"[wispr] listener setup error: {e}", flush=True)

    # ── Overlay button commands ───────────────────────────────────────────────

    def _check_overlay_cmd(self, sender):
        cmd = read_command()
        if cmd == "cancel":
            with self._lock:
                if self._recording:
                    self._recording = False
            self._recorder.stop()
            hide_recording()
            self._set_icon(ICON_IDLE)
        elif cmd == "stop":
            with self._lock:
                if self._recording:
                    self._recording = False
                    threading.Thread(target=self._finish_recording, daemon=True).start()

    # ── Recording flow ────────────────────────────────────────────────────────

    def _begin_recording(self):
        self._record_start = time.monotonic()
        self._set_icon(ICON_REC)
        self._recorder.start()
        show_recording()

    def _finish_recording(self):
        elapsed = time.monotonic() - self._record_start
        if elapsed < 0.3:
            time.sleep(0.3 - elapsed)
        wav_buf = self._recorder.stop()
        hide_recording()
        self._set_icon(ICON_BUSY)
        text, duration_s = transcribe(wav_buf)
        if text:
            pasted = inject(text, target_app=self._target_app)
            word_count = len(text.split())
            cost_usd = round(duration_s * 0.006 / 60, 6)
            db.save_transcription(text, duration_s, word_count, cost_usd)
            settings = db.get_settings()
            if settings.get("obsidian_auto_save") == "true":
                try:
                    tid = db.get_latest_id()
                    if tid:
                        _save_to_obsidian(tid, settings)
                except Exception as e:
                    print(f"[wispr] obsidian auto-save error: {e}", flush=True)
            preview = text[:50] + ("…" if len(text) > 50 else "")
            if pasted:
                self._notify("✓ Pasted", preview)
            else:
                self._notify("✓ Copied — press Cmd+V", preview)
        else:
            self._notify("", "Nothing detected — try again")
        self._set_icon(ICON_IDLE)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_icon(self, icon):
        rumps.Timer(lambda _: setattr(self, "title", icon), 0).start()

    def _notify(self, subtitle, message):
        # rumps.notification must run on the main thread — dispatch via zero-delay timer
        rumps.Timer(
            lambda _: rumps.notification("Wispr Local", subtitle, message, sound=False), 0
        ).start()

    def _open_dashboard(self, _):
        webbrowser.open(f"http://localhost:{DASHBOARD_PORT}")

    def _quit(self, _):
        rumps.quit_application()


def _save_to_obsidian(tid, settings):
    row = db.get_transcription(tid)
    if not row:
        return
    vault = os.path.expanduser(settings.get("obsidian_vault", "~/Documents/Vault"))
    folder = settings.get("obsidian_folder", "Voice Notes")
    save_dir = os.path.join(vault, folder)
    os.makedirs(save_dir, exist_ok=True)
    created = row["created_at"][:16].replace(":", "-")
    filepath = os.path.join(save_dir, f"{created} voice-note.md")
    words = row.get("word_count") or len(row["text"].split())
    cost = row.get("cost_usd") or 0
    content = f"# Voice Note — {row['created_at'][:16]}\n\n{row['text']}\n\n---\n*Transcribed by Wispr Local · {words} words · ${cost:.4f}*\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    WisprLocal().run()
