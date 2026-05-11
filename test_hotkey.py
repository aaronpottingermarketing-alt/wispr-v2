"""Run this to check if Right Option key is being detected."""
import time
from AppKit import NSEvent, NSEventMaskFlagsChanged, NSEventModifierFlagOption
from PyObjCTools import AppHelper

def handler(event):
    print(f"Key event — keyCode: {event.keyCode()}, flags: {event.modifierFlags()}")
    if event.keyCode() == 61:
        held = bool(event.modifierFlags() & NSEventModifierFlagOption)
        print(f"  >> Right Option {'PRESSED' if held else 'RELEASED'}")

monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
    NSEventMaskFlagsChanged, handler
)

print("Listening for modifier keys — press Right Option a few times, then Ctrl+C to stop")
AppHelper.runConsoleEventLoop()
