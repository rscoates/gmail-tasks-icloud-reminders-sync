from typing import List, Optional, NamedTuple
from datetime import datetime
from threading import Event
from enum import Enum
import json
import platform
from sqlalchemy.orm import Session

from EventKit import EKEventStore, EKEntityTypeReminder, EKReminder
from Foundation import NSCalendar, NSCalendarUnitYear, NSCalendarUnitMonth, NSCalendarUnitDay
from Foundation import NSCalendarUnitHour, NSCalendarUnitMinute, NSCalendarUnitSecond, NSDate

from app.models import Credential


class Priority(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Reminder(NamedTuple):
    id: str
    title: str
    due_date: Optional[datetime]
    notes: Optional[str]
    completed: bool
    priority: int
    list_id: str


# Global EventStore instance
_event_store: Optional[EKEventStore] = None


def _get_macos_version() -> tuple:
    """Get macOS version as a tuple of integers."""
    version = platform.mac_ver()[0]
    parts = version.split('.')
    return tuple(int(p) for p in parts[:2])


def _grant_permission() -> EKEventStore:
    """Grants permission to access reminders and returns the EKEventStore."""
    event_store = EKEventStore.alloc().init()
    done = Event()
    result = {}

    def completion_handler(granted: bool, error) -> None:
        result["granted"] = granted
        result["error"] = error
        done.set()

    macos_version = _get_macos_version()
    
    # macOS 14+ uses requestFullAccessToRemindersWithCompletion_
    # Older versions use requestAccessToEntityType_completion_
    if macos_version >= (14, 0):
        event_store.requestFullAccessToRemindersWithCompletion_(completion_handler)
    else:
        event_store.requestAccessToEntityType_completion_(EKEntityTypeReminder, completion_handler)
    
    done.wait(timeout=60)
    
    if not result.get("granted"):
        raise PermissionError("No access to reminders. Please grant access in System Preferences > Privacy & Security > Reminders")

    return event_store


def get_event_store() -> EKEventStore:
    """Get or create the EKEventStore instance."""
    global _event_store
    if _event_store is None:
        _event_store = _grant_permission()
    return _event_store


def save_icloud_credentials(db: Session, username: str, app_password: str):
    """Store iCloud credentials in database.
    
    Note: With EventKit, credentials are handled by macOS.
    This function is kept for API compatibility but credentials are not used.
    """
    cred_record = db.query(Credential).filter(Credential.service == "icloud").first()
    
    cred_data = {
        "access_token": app_password,
        "extra_data": json.dumps({"username": username, "note": "EventKit uses macOS credentials"})
    }
    
    if cred_record:
        for key, value in cred_data.items():
            setattr(cred_record, key, value)
    else:
        cred_record = Credential(service="icloud", **cred_data)
        db.add(cred_record)
    
    db.commit()


def get_icloud_credentials(db: Session) -> Optional[tuple]:
    """Retrieve stored iCloud credentials."""
    cred_record = db.query(Credential).filter(Credential.service == "icloud").first()
    
    if not cred_record or not cred_record.access_token:
        return None
    
    extra_data = json.loads(cred_record.extra_data) if cred_record.extra_data else {}
    username = extra_data.get("username")
    
    if not username:
        return None
    
    return (username, cred_record.access_token)


def list_reminder_calendars(db: Session) -> List[dict]:
    """List all reminder lists using EventKit."""
    event_store = get_event_store()
    calendars = event_store.calendarsForEntityType_(EKEntityTypeReminder)
    
    default_calendar = event_store.defaultCalendarForNewReminders()
    default_id = default_calendar.calendarIdentifier() if default_calendar else None
    
    result = []
    for calendar in calendars:
        result.append({
            "id": calendar.calendarIdentifier(),
            "name": calendar.title(),
            "color": str(calendar.color()) if calendar.color() else None,
            "is_default": calendar.calendarIdentifier() == default_id
        })
    
    return result


def _convert_ek_reminder(ek_reminder) -> Reminder:
    """Convert an EKReminder to our Reminder type."""
    due_date = None
    if ek_reminder.dueDateComponents():
        ns_date = ek_reminder.dueDateComponents().date()
        if ns_date:
            due_date = datetime.fromtimestamp(ns_date.timeIntervalSince1970())
    
    return Reminder(
        id=ek_reminder.calendarItemIdentifier(),
        title=ek_reminder.title() or "",
        due_date=due_date,
        notes=ek_reminder.notes(),
        completed=ek_reminder.isCompleted(),
        priority=ek_reminder.priority() if hasattr(ek_reminder, "priority") else 0,
        list_id=ek_reminder.calendar().calendarIdentifier(),
    )


def list_reminders(db: Session, calendar_id: str) -> List[dict]:
    """List all reminders in a reminder list."""
    event_store = get_event_store()
    
    # Get the calendar
    ek_calendar = event_store.calendarWithIdentifier_(calendar_id)
    if not ek_calendar:
        return []
    
    # Create predicate for all reminders in this calendar
    predicate = event_store.predicateForRemindersInCalendars_([ek_calendar])
    
    # Fetch reminders
    fetch_done = Event()
    found_reminders = []
    
    def completion_handler(reminders):
        nonlocal found_reminders
        if reminders:
            found_reminders = list(reminders)
        fetch_done.set()
    
    event_store.fetchRemindersMatchingPredicate_completion_(predicate, completion_handler)
    fetch_done.wait(timeout=30)
    
    result = []
    for ek_reminder in found_reminders:
        r = _convert_ek_reminder(ek_reminder)
        result.append({
            "id": r.id,
            "summary": r.title,
            "description": r.notes,
            "due": r.due_date,
            "completed": r.completed,
            "priority": r.priority,
            "list_id": r.list_id,
            "flagged": False,
            "url": None
        })
    
    return result


def create_reminder(
    db: Session,
    calendar_id: str,
    summary: str,
    description: str = None,
    due: datetime = None,
    priority: int = 0
) -> dict:
    """Create a new reminder using EventKit."""
    event_store = get_event_store()
    
    # Get the calendar
    ek_calendar = event_store.calendarWithIdentifier_(calendar_id)
    if not ek_calendar:
        raise ValueError(f"Calendar with ID '{calendar_id}' not found")
    
    # Create reminder
    new_reminder = EKReminder.reminderWithEventStore_(event_store)
    new_reminder.setCalendar_(ek_calendar)
    new_reminder.setTitle_(summary)
    
    if description:
        new_reminder.setNotes_(description)
    
    if due:
        components = NSCalendar.currentCalendar().components_fromDate_(
            NSCalendarUnitYear | NSCalendarUnitMonth | NSCalendarUnitDay |
            NSCalendarUnitHour | NSCalendarUnitMinute | NSCalendarUnitSecond,
            NSDate.dateWithTimeIntervalSince1970_(due.timestamp()),
        )
        new_reminder.setDueDateComponents_(components)
    
    if priority:
        new_reminder.setPriority_(priority)
    
    # Save - PyObjC returns (success, error) tuple for methods with error output params
    success, error = event_store.saveReminder_commit_error_(new_reminder, True, None)
    
    if not success:
        raise RuntimeError(f"Failed to create reminder: {error}")
    
    return {
        "id": new_reminder.calendarItemIdentifier(),
        "summary": new_reminder.title(),
        "list_id": ek_calendar.calendarIdentifier()
    }


def update_reminder(
    db: Session,
    reminder_id: str,
    summary: str = None,
    description: str = None,
    completed: bool = None,
    due: datetime = None
) -> dict:
    """Update an existing reminder using EventKit."""
    event_store = get_event_store()
    
    ek_reminder = event_store.calendarItemWithIdentifier_(reminder_id)
    if not ek_reminder:
        raise ValueError(f"Reminder with ID '{reminder_id}' not found")
    
    if summary is not None:
        ek_reminder.setTitle_(summary)
    
    if description is not None:
        ek_reminder.setNotes_(description)
    
    if completed is not None:
        ek_reminder.setCompleted_(completed)
    
    if due is not None:
        components = NSCalendar.currentCalendar().components_fromDate_(
            NSCalendarUnitYear | NSCalendarUnitMonth | NSCalendarUnitDay |
            NSCalendarUnitHour | NSCalendarUnitMinute | NSCalendarUnitSecond,
            NSDate.dateWithTimeIntervalSince1970_(due.timestamp()),
        )
        ek_reminder.setDueDateComponents_(components)
    
    # Save - PyObjC returns (success, error) tuple for methods with error output params
    success, error = event_store.saveReminder_commit_error_(ek_reminder, True, None)
    
    if not success:
        raise RuntimeError(f"Failed to update reminder: {error}")
    
    return {
        "id": ek_reminder.calendarItemIdentifier(),
        "summary": ek_reminder.title(),
        "list_id": ek_reminder.calendar().calendarIdentifier()
    }


def delete_reminder(db: Session, reminder_id: str):
    """Delete a reminder using EventKit."""
    event_store = get_event_store()
    
    ek_reminder = event_store.calendarItemWithIdentifier_(reminder_id)
    if not ek_reminder:
        raise ValueError(f"Reminder with ID '{reminder_id}' not found")
    
    error = None
    success = event_store.removeReminder_commit_error_(ek_reminder, True, error)
    
    if not success:
        raise RuntimeError(f"Failed to delete reminder: {error}")


def is_icloud_connected(db: Session) -> bool:
    """Check if EventKit/Reminders access is available."""
    try:
        event_store = get_event_store()
        # Try to list calendars to verify access
        calendars = event_store.calendarsForEntityType_(EKEntityTypeReminder)
        return calendars is not None and len(calendars) > 0
    except Exception as e:
        print(f"iCloud/EventKit not connected: {e}")
        return False
