#!/usr/bin/env python3
"""Script to request Reminders access on macOS."""

import sys
from threading import Event
from EventKit import EKEventStore, EKEntityTypeReminder
from Foundation import NSRunLoop, NSDate

print("Requesting Reminders access...")
print("A system dialog should appear. Please click 'OK' to grant access.")
print()

event_store = EKEventStore.alloc().init()
done = Event()
access_granted = False

def completion_handler(granted, error):
    global access_granted
    access_granted = granted
    if granted:
        print("✅ Access GRANTED!")
    else:
        print("❌ Access DENIED")
        if error:
            print(f"Error: {error}")
    done.set()

# Request access
event_store.requestAccessToEntityType_completion_(EKEntityTypeReminder, completion_handler)

# Run the run loop to allow the dialog to appear
print("Waiting for permission dialog...")
timeout = 60
while not done.is_set() and timeout > 0:
    # Process pending events (allows system dialogs to appear)
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(1.0))
    timeout -= 1

if not done.is_set():
    print("Timeout waiting for response")
    sys.exit(1)

# Verify access
calendars = event_store.calendarsForEntityType_(EKEntityTypeReminder)
if calendars and len(calendars) > 0:
    print(f"\n✅ Found {len(calendars)} reminder list(s):")
    for cal in calendars:
        print(f"  - {cal.title()}")
else:
    print("\n⚠️  No reminder lists found or access not working")

sys.exit(0 if access_granted else 1)
