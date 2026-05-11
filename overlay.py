import subprocess
import sys
import os
import threading

_proc = None
_pipe_thread = None
_stop_pipe = threading.Event()
_python = sys.executable
_script = os.path.join(os.path.dirname(__file__), "overlay_window.py")
CMD_FILE = "/tmp/wispr_cmd"


def cmd_file():
    return CMD_FILE


def show_recording():
    global _proc, _pipe_thread, _stop_pipe
    try:
        os.remove(CMD_FILE)
    except FileNotFoundError:
        pass

    if _proc is None or _proc.poll() is not None:
        _proc = subprocess.Popen(
            [_python, _script, CMD_FILE],
            stdin=subprocess.PIPE,
        )
        _stop_pipe.clear()
        _pipe_thread = threading.Thread(target=_stream_levels, daemon=True)
        _pipe_thread.start()


def hide_recording():
    global _proc, _pipe_thread
    _stop_pipe.set()
    if _proc and _proc.poll() is None:
        _proc.terminate()
    _proc = None


def _stream_levels():
    """Write audio level to overlay stdin at 30fps."""
    import recorder
    import time
    while not _stop_pipe.is_set():
        try:
            if _proc and _proc.poll() is None:
                level = recorder.current_level
                _proc.stdin.write(f"{level:.3f}\n".encode())
                _proc.stdin.flush()
        except Exception:
            break
        time.sleep(1 / 30)


def read_command():
    try:
        with open(CMD_FILE) as f:
            cmd = f.read().strip()
        os.remove(CMD_FILE)
        return cmd if cmd in ("cancel", "stop") else None
    except FileNotFoundError:
        return None
