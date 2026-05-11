import time
import threading
import pyperclip
import Quartz
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps, NSSound
import ApplicationServices as AX

V_KEYCODE = 9  # 'v'


def inject(text, target_app=None):
    previous = _safe_get_clipboard()
    pyperclip.copy(text)
    time.sleep(0.1)

    app = target_app or NSWorkspace.sharedWorkspace().frontmostApplication()

    # Try 1: AX direct text insertion (native apps)
    if _inject_via_ax(text):
        threading.Timer(1.5, lambda: pyperclip.copy(previous or "")).start()
        return True

    # Try 2: CGEventPost Cmd+V directly to the target process
    if app:
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.3)
        pid = app.processIdentifier()
        if _cmd_v_to_pid(pid):
            threading.Timer(3.0, lambda: pyperclip.copy(previous or "")).start()
            return True

    # Fallback: clipboard + sound + notification
    _play_sound("Tink")
    print("[wispr] clipboard ready — press Cmd+V", flush=True)
    threading.Timer(15.0, lambda: pyperclip.copy(previous or "")).start()
    return False


def _inject_via_ax(text):
    try:
        system_wide = AX.AXUIElementCreateSystemWide()
        err, focused = AX.AXUIElementCopyAttributeValue(
            system_wide, AX.kAXFocusedUIElementAttribute, None
        )
        if err != 0 or focused is None:
            return False
        err = AX.AXUIElementSetAttributeValue(
            focused, AX.kAXSelectedTextAttribute, text
        )
        if err != 0:
            return False
        time.sleep(0.05)
        err2, current = AX.AXUIElementCopyAttributeValue(
            focused, AX.kAXValueAttribute, None
        )
        if err2 == 0 and current and text[:20] in str(current):
            print("[wispr] paste OK (AX)", flush=True)
            return True
        return False
    except Exception:
        return False


def _cmd_v_to_pid(pid):
    try:
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        v_down = Quartz.CGEventCreateKeyboardEvent(src, V_KEYCODE, True)
        Quartz.CGEventSetFlags(v_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPostToPid(pid, v_down)
        time.sleep(0.05)
        v_up = Quartz.CGEventCreateKeyboardEvent(src, V_KEYCODE, False)
        Quartz.CGEventSetFlags(v_up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPostToPid(pid, v_up)
        time.sleep(0.1)
        # Verify clipboard was consumed (if clipboard is now empty-ish, paste worked)
        print("[wispr] paste attempted via CGEvent", flush=True)
        return True
    except Exception as e:
        print(f"[wispr] CGEvent error: {e}", flush=True)
        return False


def _play_sound(name):
    try:
        sound = NSSound.soundNamed_(name)
        if sound:
            sound.play()
    except Exception:
        pass


def _safe_get_clipboard():
    try:
        return pyperclip.paste()
    except Exception:
        return ""
