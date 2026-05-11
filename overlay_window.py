"""Wispr-style floating recording indicator with X, stop, and hands-free support."""
import math
import os
import random
import sys
import threading
import objc
import AppKit
from AppKit import (
    NSApplication, NSWindow, NSView, NSBezierPath, NSColor, NSButton,
    NSBackingStoreBuffered, NSMakeRect, NSMakeSize,
    NSWindowStyleMaskBorderless, NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSBezelStyleCircular, NSButtonTypeMomentaryLight,
)
from Foundation import NSTimer, NSRunLoop, NSDefaultRunLoopMode

# Command file for IPC back to main app
CMD_FILE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/wispr_cmd"

_level = 0.5
_level_lock = threading.Lock()


def _read_stdin():
    """Read audio levels piped from main process."""
    global _level
    import sys
    for line in sys.stdin:
        try:
            with _level_lock:
                _level = float(line.strip())
        except ValueError:
            pass


threading.Thread(target=_read_stdin, daemon=True).start()


def _send(cmd):
    with open(CMD_FILE, "w") as f:
        f.write(cmd)
    AppKit.NSApp.terminate_(None)


class WaveformView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(WaveformView, self).initWithFrame_(frame)
        if self:
            self._bars = [0.15] * 10
            self._t = 0.0
        return self

    def tick_(self, _timer):
        with _level_lock:
            lvl = _level
        self._t += 0.14
        for i in range(len(self._bars)):
            centre_bias = 1.0 - abs(i - 4.5) / 5.0
            wave = 0.5 + 0.5 * math.sin(self._t * 1.1 + i * 0.85)
            noise = random.uniform(0.85, 1.15)
            base = max(0.08, lvl * wave * noise * (0.5 + 0.5 * centre_bias))
            self._bars[i] = self._bars[i] * 0.5 + base * 0.5
        self.setNeedsDisplay_(True)

    def drawRect_(self, dirty):
        b = self.bounds()
        w, h = b.size.width, b.size.height
        NSColor.clearColor().setFill()
        AppKit.NSRectFill(b)

        # Dark pill
        pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, h / 2, h / 2)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.10, 0.11, 0.96).setFill()
        pill.fill()

        # Waveform bars — centred between the two buttons
        btn_w = h  # buttons are square/circular
        avail = w - btn_w * 2 - 16
        n = len(self._bars)
        bar_w = 2.5
        gap = (avail - n * bar_w) / (n - 1)
        gap = max(2.0, min(gap, 5.0))
        total = n * bar_w + (n - 1) * gap
        sx = btn_w + 8 + (avail - total) / 2
        max_h = h * 0.68

        NSColor.colorWithCalibratedWhite_alpha_(0.95, 1.0).setFill()
        for i, lvl in enumerate(self._bars):
            bh = max(3.0, lvl * max_h)
            x = sx + i * (bar_w + gap)
            y = (h - bh) / 2
            r = NSMakeRect(x, y, bar_w, bh)
            p = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(r, 1.2, 1.2)
            p.fill()


class CancelButton(NSView):
    """Grey circle with X — cancels recording."""

    def drawRect_(self, dirty):
        b = self.bounds()
        s = min(b.size.width, b.size.height) - 4
        x = (b.size.width - s) / 2
        y = (b.size.height - s) / 2
        circle = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x, y, s, s))
        NSColor.colorWithCalibratedWhite_alpha_(0.45, 1.0).setFill()
        circle.fill()
        # X
        NSColor.colorWithCalibratedWhite_alpha_(0.9, 1.0).setStroke()
        pad = s * 0.3
        line1 = NSBezierPath.bezierPath()
        line1.moveToPoint_((x + pad, y + pad))
        line1.lineToPoint_((x + s - pad, y + s - pad))
        line1.setLineWidth_(1.8)
        line1.setLineCapStyle_(AppKit.NSLineCapStyleRound)
        line1.stroke()
        line2 = NSBezierPath.bezierPath()
        line2.moveToPoint_((x + s - pad, y + pad))
        line2.lineToPoint_((x + pad, y + s - pad))
        line2.setLineWidth_(1.8)
        line2.setLineCapStyle_(AppKit.NSLineCapStyleRound)
        line2.stroke()

    def mouseDown_(self, event):
        _send("cancel")


class StopButton(NSView):
    """Red circle with white square — stops and transcribes."""

    def drawRect_(self, dirty):
        b = self.bounds()
        s = min(b.size.width, b.size.height) - 4
        x = (b.size.width - s) / 2
        y = (b.size.height - s) / 2
        circle = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(x, y, s, s))
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.93, 0.35, 0.38, 1.0).setFill()
        circle.fill()
        # Square
        sq = s * 0.36
        NSColor.whiteColor().setFill()
        sq_rect = NSMakeRect(x + (s - sq) / 2, y + (s - sq) / 2, sq, sq)
        NSBezierPath.fillRect_(sq_rect)

    def mouseDown_(self, event):
        _send("stop")


# ── App setup ─────────────────────────────────────────────────────────────────
app = NSApplication.sharedApplication()
app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

screen = AppKit.NSScreen.mainScreen()
sf = screen.frame()
W, H = 180, 38
x = (sf.size.width - W) / 2
y = 44

win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    NSMakeRect(x, y, W, H),
    NSWindowStyleMaskBorderless,
    NSBackingStoreBuffered,
    False,
)
win.setLevel_(NSFloatingWindowLevel + 2)
win.setOpaque_(False)
win.setBackgroundColor_(NSColor.clearColor())
win.setHasShadow_(True)
win.setIgnoresMouseEvents_(False)
win.setCollectionBehavior_(
    NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
)

content = win.contentView()

# Waveform view fills entire background
wave = WaveformView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
wave.setWantsLayer_(True)
content.addSubview_(wave)

# Cancel button (left)
cancel_btn = CancelButton.alloc().initWithFrame_(NSMakeRect(4, 4, H - 8, H - 8))
cancel_btn.setWantsLayer_(True)
content.addSubview_(cancel_btn)

# Stop button (right)
stop_btn = StopButton.alloc().initWithFrame_(NSMakeRect(W - H + 4, 4, H - 8, H - 8))
stop_btn.setWantsLayer_(True)
content.addSubview_(stop_btn)

win.orderFrontRegardless()
win.makeKeyWindow()

timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
    1 / 30, wave, "tick:", None, True
)
NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSDefaultRunLoopMode)

app.run()
