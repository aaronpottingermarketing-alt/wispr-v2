import subprocess
import sys
import os

_proc = None
_python = sys.executable
_script = os.path.join(os.path.dirname(__file__), "overlay_window.py")
CMD_FILE = "/tmp/wispr_cmd"


def cmd_file():
    return CMD_FILE


def show_recording():
    global _proc
    # Clear any previous command
    try:
        os.remove(CMD_FILE)
    except FileNotFoundError:
        pass
    if _proc is None or _proc.poll() is not None:
        _proc = subprocess.Popen([_python, _script, CMD_FILE])


def hide_recording():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
    _proc = None


def read_command():
    """Returns 'cancel', 'stop', or None."""
    try:
        with open(CMD_FILE) as f:
            cmd = f.read().strip()
        os.remove(CMD_FILE)
        return cmd if cmd in ("cancel", "stop") else None
    except FileNotFoundError:
        return None
