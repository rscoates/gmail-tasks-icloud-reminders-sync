from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models import SyncLog, SyncStatus, SyncDirection, TaskMapping, Settings
from app.services import google_tasks, icloud_reminders


def get_setting(db: Session, key: str, default: str = None) -> Optional[str]:
    """Get a setting value from the database."""
    setting = db.query(Settings).filter(Settings.key == key).first()
    return setting.value if setting else default


def set_setting(db: Session, key: str, value: str):
    """Set a setting value in the database."""
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = Settings(key=key, value=value)
        db.add(setting)
    db.commit()


def sync_gmail_task_to_icloud(
    db: Session,
    task: dict,
    task_list_id: str,
    calendar_id: str
) -> Optional[TaskMapping]:
    """Sync a single Gmail task to iCloud reminders."""
    # Check if already mapped
    mapping = db.query(TaskMapping).filter(
        TaskMapping.gmail_task_id == task["id"]
    ).first()
    
    title = task.get("title", "Untitled Task")
    notes = task.get("notes", "")
    due_str = task.get("due")
    due = datetime.fromisoformat(due_str.replace("Z", "+00:00")) if due_str else None
    is_completed = task.get("status") == "completed"
    
    if mapping and mapping.icloud_reminder_uid:
        # Update existing reminder
        try:
            # Update reminder directly by ID
            icloud_reminders.update_reminder(
                db,
                mapping.icloud_reminder_uid,
                summary=title,
                description=notes,
                completed=is_completed,
                due=due
            )
            mapping.title = title
            mapping.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            print(f"Error updating reminder: {e}")
    else:
        # Create new reminder
        try:
            result = icloud_reminders.create_reminder(
                db,
                calendar_id,
                summary=title,
                description=notes,
                due=due
            )
            
            if mapping:
                mapping.icloud_reminder_uid = result["id"]
                mapping.icloud_calendar_url = calendar_id
                mapping.title = title
                mapping.updated_at = datetime.utcnow()
            else:
                mapping = TaskMapping(
                    gmail_task_id=task["id"],
                    gmail_task_list_id=task_list_id,
                    icloud_reminder_uid=result["id"],
                    icloud_calendar_url=calendar_id,
                    title=title
                )
                db.add(mapping)
            
            db.commit()
        except Exception as e:
            print(f"Error creating reminder: {e}")
            return None
    
    return mapping


def sync_icloud_reminder_to_gmail(
    db: Session,
    reminder: dict,
    calendar_id: str,
    task_list_id: str
) -> Optional[TaskMapping]:
    """Sync a single iCloud reminder to Gmail tasks."""
    # Check if already mapped
    mapping = db.query(TaskMapping).filter(
        TaskMapping.icloud_reminder_uid == reminder["id"]
    ).first()
    
    title = reminder.get("summary", "Untitled Reminder")
    notes = reminder.get("description", "")
    due = reminder.get("due")
    is_completed = reminder.get("completed", False)
    
    if mapping and mapping.gmail_task_id:
        # Update existing task
        try:
            update_data = {"title": title}
            if notes:
                update_data["notes"] = notes
            if due:
                update_data["due"] = due.isoformat() + "Z" if due else None
            # Sync completion status
            update_data["status"] = "completed" if is_completed else "needsAction"
            
            google_tasks.update_task(
                db,
                mapping.gmail_task_list_id,
                mapping.gmail_task_id,
                **update_data
            )
            mapping.title = title
            mapping.updated_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            print(f"Error updating task: {e}")
    else:
        # Create new task
        try:
            result = google_tasks.create_task(
                db,
                task_list_id,
                title=title,
                notes=notes,
                due=due,
                status="completed" if is_completed else "needsAction"
            )
            
            if mapping:
                mapping.gmail_task_id = result["id"]
                mapping.gmail_task_list_id = task_list_id
                mapping.title = title
                mapping.updated_at = datetime.utcnow()
            else:
                mapping = TaskMapping(
                    gmail_task_id=result["id"],
                    gmail_task_list_id=task_list_id,
                    icloud_reminder_uid=reminder["id"],
                    icloud_calendar_url=calendar_id,
                    title=title
                )
                db.add(mapping)
            
            db.commit()
        except Exception as e:
            print(f"Error creating task: {e}")
            return None
    
    return mapping


def run_sync(db: Session, direction: SyncDirection = None) -> SyncLog:
    """Run the synchronization between Gmail Tasks and iCloud Reminders."""
    # Get settings
    if direction is None:
        direction_str = get_setting(db, "sync_direction", SyncDirection.BIDIRECTIONAL.value)
        direction = SyncDirection(direction_str)
    
    task_list_id = get_setting(db, "gmail_task_list_id", "@default")
    calendar_id = get_setting(db, "icloud_calendar_name")
    
    # Create sync log
    sync_log = SyncLog(
        status=SyncStatus.RUNNING,
        direction=direction,
        started_at=datetime.utcnow()
    )
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)
    
    tasks_synced = 0
    reminders_synced = 0
    error_message = None
    
    try:
        # Check connections
        if not google_tasks.is_google_connected(db):
            raise ValueError("Google Tasks is not connected. Please authenticate first.")
        
        if not icloud_reminders.is_icloud_connected(db):
            raise ValueError("iCloud is not connected. Please configure credentials first.")
        
        if not calendar_id:
            raise ValueError("iCloud calendar not configured. Please select a reminder list.")
        
        # Build maps of current state for bidirectional sync
        gmail_tasks_map = {}
        icloud_reminders_map = {}
        
        if direction in [SyncDirection.GMAIL_TO_ICLOUD, SyncDirection.BIDIRECTIONAL]:
            tasks = google_tasks.list_tasks(db, task_list_id)
            gmail_tasks_map = {t["id"]: t for t in tasks if t.get("title")}
        
        if direction in [SyncDirection.ICLOUD_TO_GMAIL, SyncDirection.BIDIRECTIONAL]:
            reminders = icloud_reminders.list_reminders(db, calendar_id)
            icloud_reminders_map = {r["id"]: r for r in reminders if r.get("summary")}
        
        # For bidirectional sync, handle completion changes intelligently
        if direction == SyncDirection.BIDIRECTIONAL:
            # Get all existing mappings
            mappings = db.query(TaskMapping).all()
            
            for mapping in mappings:
                task = gmail_tasks_map.get(mapping.gmail_task_id)
                reminder = icloud_reminders_map.get(mapping.icloud_reminder_uid)
                
                if task and reminder:
                    gmail_completed = task.get("status") == "completed"
                    icloud_completed = reminder.get("completed", False)
                    last_known = mapping.last_known_completed or False
                    
                    # Detect which side changed
                    gmail_changed = gmail_completed != last_known
                    icloud_changed = icloud_completed != last_known
                    
                    if gmail_changed and not icloud_changed:
                        # Gmail changed, update iCloud
                        icloud_reminders.update_reminder(
                            db, mapping.icloud_reminder_uid, completed=gmail_completed
                        )
                        mapping.last_known_completed = gmail_completed
                    elif icloud_changed and not gmail_changed:
                        # iCloud changed, update Gmail
                        google_tasks.update_task(
                            db, mapping.gmail_task_list_id, mapping.gmail_task_id,
                            status="completed" if icloud_completed else "needsAction"
                        )
                        mapping.last_known_completed = icloud_completed
                    elif gmail_changed and icloud_changed:
                        # Both changed - prefer completed state (if either is done, mark both done)
                        final_state = gmail_completed or icloud_completed
                        if gmail_completed != final_state:
                            google_tasks.update_task(
                                db, mapping.gmail_task_list_id, mapping.gmail_task_id,
                                status="completed" if final_state else "needsAction"
                            )
                        if icloud_completed != final_state:
                            icloud_reminders.update_reminder(
                                db, mapping.icloud_reminder_uid, completed=final_state
                            )
                        mapping.last_known_completed = final_state
                    
                    # Also sync title/notes from Gmail to iCloud
                    icloud_reminders.update_reminder(
                        db, mapping.icloud_reminder_uid,
                        summary=task.get("title"),
                        description=task.get("notes", "")
                    )
                    tasks_synced += 1
            
            db.commit()
            
            # Handle unmapped items (new on either side)
            mapped_gmail_ids = {m.gmail_task_id for m in mappings}
            mapped_icloud_ids = {m.icloud_reminder_uid for m in mappings}
            
            # New Gmail tasks -> create in iCloud
            for task_id, task in gmail_tasks_map.items():
                if task_id not in mapped_gmail_ids:
                    mapping = sync_gmail_task_to_icloud(db, task, task_list_id, calendar_id)
                    if mapping:
                        mapping.last_known_completed = task.get("status") == "completed"
                        tasks_synced += 1
            
            # New iCloud reminders -> create in Gmail
            for reminder_id, reminder in icloud_reminders_map.items():
                if reminder_id not in mapped_icloud_ids:
                    mapping = sync_icloud_reminder_to_gmail(db, reminder, calendar_id, task_list_id)
                    if mapping:
                        mapping.last_known_completed = reminder.get("completed", False)
                        reminders_synced += 1
        
        elif direction == SyncDirection.GMAIL_TO_ICLOUD:
            for task in gmail_tasks_map.values():
                mapping = sync_gmail_task_to_icloud(db, task, task_list_id, calendar_id)
                if mapping:
                    mapping.last_known_completed = task.get("status") == "completed"
                    tasks_synced += 1
        
        elif direction == SyncDirection.ICLOUD_TO_GMAIL:
            for reminder in icloud_reminders_map.values():
                mapping = sync_icloud_reminder_to_gmail(db, reminder, calendar_id, task_list_id)
                if mapping:
                    mapping.last_known_completed = reminder.get("completed", False)
                    reminders_synced += 1
        
        db.commit()
        sync_log.status = SyncStatus.SUCCESS
        
    except Exception as e:
        error_message = str(e)
        sync_log.status = SyncStatus.FAILED
        sync_log.error_message = error_message
        print(f"Sync error: {e}")
    
    sync_log.tasks_synced = tasks_synced
    sync_log.reminders_synced = reminders_synced
    sync_log.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(sync_log)
    
    return sync_log
