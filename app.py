import os
import time
import threading
import webbrowser
import rumps
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

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

RIGHT_OPTION_KEYCODE  = 61
HANDS_FREE_HOLD_SECS  = 1.5  # hold this long to lock into hands-free mode


class WisprLocal(rumps.App):
    def __init__(self):
        super().__init__(ICON_IDLE, quit_button=None)
        self.menu = [
            rumps.MenuItem("Wispr Local", callback=None),
            rumps.MenuItem("Open Dashboard", callback=self._open_dashboard),
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]
        self._recorder   = Recorder()
        self._recording   = False
        self._hands_free  = False
        self._lock        = threading.Lock()
        self._monitor     = None
        self._target_app  = None
        self._press_time  = 0.0   # when Right Option was pressed
        self._hf_timer    = None  # fires after HANDS_FREE_HOLD_SECS

        server.start_server(port=DASHBOARD_PORT)
        rumps.Timer(self._setup_listener, 0.5).start()

    # ── Listener ──────────────────────────────────────────────────────────────

    def _setup_listener(self, sender):
        sender.stop()
        try:
            from AppKit import NSEvent, NSEventMaskFlagsChanged, NSEventModifierFlagOption
            import ApplicationServices as AX
            AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: True})

            def handler(event):
                if event.keyCode() != RIGHT_OPTION_KEYCODE:
                    return
                held = bool(event.modifierFlags() & NSEventModifierFlagOption)

                with self._lock:
                    if held and not self._recording:
                        # Start recording + begin hands-free countdown
                        self._recording  = True
                        self._press_time = time.time()
                        from AppKit import NSWorkspace
                        self._target_app = NSWorkspace.sharedWorkspace().frontmostApplication()
                        threading.Thread(target=self._begin_recording, daemon=True).start()
                        # After HANDS_FREE_HOLD_SECS, lock into hands-free
                        self._hf_timer = threading.Timer(
                            HANDS_FREE_HOLD_SECS, self._activate_hands_free
                        )
                        self._hf_timer.start()

                    elif held and self._hands_free:
                        # Tap while hands-free → stop
                        self._hands_free = False
                        self._recording  = False
                        threading.Thread(target=self._finish_recording, daemon=True).start()

                    elif not held:
                        # Key released
                        if self._hf_timer:
                            self._hf_timer.cancel()
                            self._hf_timer = None
                        if self._recording and not self._hands_free:
                            self._recording = False
                            threading.Thread(target=self._finish_recording, daemon=True).start()

            self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskFlagsChanged, handler
            )
            print("[wispr] hotkey listener ready", flush=True)

            # Poll for overlay button commands
            rumps.Timer(self._check_overlay_cmd, 0.1).start()

        except Exception as e:
            print(f"[wispr] listener setup error: {e}", flush=True)

    def _activate_hands_free(self):
        with self._lock:
            if self._recording:
                self._hands_free = True
        print("[wispr] hands-free mode locked", flush=True)

    # ── Overlay button commands ───────────────────────────────────────────────

    def _check_overlay_cmd(self, sender):
        cmd = read_command()
        if cmd == "cancel":
            with self._lock:
                if self._recording:
                    self._recording  = False
                    self._hands_free = False
            self._recorder.stop()   # discard audio
            hide_recording()
            self._set_icon(ICON_IDLE)
        elif cmd == "stop":
            with self._lock:
                if self._recording:
                    self._recording  = False
                    self._hands_free = False
                    threading.Thread(target=self._finish_recording, daemon=True).start()

    # ── Recording flow ────────────────────────────────────────────────────────

    def _begin_recording(self):
        self._set_icon(ICON_REC)
        self._recorder.start()
        show_recording()

    def _finish_recording(self):
        wav_buf = self._recorder.stop()
        hide_recording()
        self._set_icon(ICON_BUSY)
        text, duration_s = transcribe(wav_buf)
        if text:
            pasted = inject(text, target_app=self._target_app)
            word_count = len(text.split())
            cost_usd = round(duration_s * 0.006 / 60, 6)
            db.save_transcription(text, duration_s, word_count, cost_usd)
            preview = text[:50] + ("…" if len(text) > 50 else "")
            if pasted:
                rumps.notification("Wispr Local", "✓ Pasted", preview, sound=False)
            else:
                rumps.notification("Wispr Local", "✓ Copied — press Cmd+V", preview, sound=False)
        else:
            rumps.notification("Wispr Local", "", "Nothing detected — try again", sound=False)
        self._set_icon(ICON_IDLE)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_icon(self, icon):
        rumps.Timer(lambda _: setattr(self, "title", icon), 0).start()

    def _open_dashboard(self, _):
        webbrowser.open(f"http://localhost:{DASHBOARD_PORT}")

    def _quit(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    WisprLocal().run()
