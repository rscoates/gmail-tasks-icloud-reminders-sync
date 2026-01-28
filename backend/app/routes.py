from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.schemas import (
    SettingsUpdate, SettingsResponse, SyncLogResponse, SyncTriggerResponse,
    GoogleAuthUrl, ICloudCredentials, TaskListResponse, CalendarResponse,
    StatusResponse
)
from app.models import SyncLog, SyncStatus, SyncDirection
from app.services import google_tasks, icloud_reminders
from app.services.sync_service import get_setting, set_setting, run_sync
from app.services.scheduler import sync_scheduler

router = APIRouter()


# ============ Status & Settings ============

@router.get("/status", response_model=StatusResponse)
def get_status(db: Session = Depends(get_db)):
    """Get current sync status and configuration."""
    last_sync = db.query(SyncLog).order_by(SyncLog.id.desc()).first()
    interval = int(get_setting(db, "sync_interval_minutes", "15"))
    
    return StatusResponse(
        scheduler_running=sync_scheduler.is_running(),
        next_sync_at=sync_scheduler.get_next_run_time(),
        last_sync=SyncLogResponse.model_validate(last_sync) if last_sync else None,
        sync_interval_minutes=interval,
        google_connected=google_tasks.is_google_connected(db),
        icloud_connected=icloud_reminders.is_icloud_connected(db)
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    """Get current settings."""
    direction_str = get_setting(db, "sync_direction", SyncDirection.BIDIRECTIONAL.value)
    
    return SettingsResponse(
        sync_interval_minutes=int(get_setting(db, "sync_interval_minutes", "15")),
        sync_direction=SyncDirection(direction_str),
        gmail_task_list_id=get_setting(db, "gmail_task_list_id"),
        icloud_calendar_name=get_setting(db, "icloud_calendar_name"),
        google_connected=google_tasks.is_google_connected(db),
        icloud_connected=icloud_reminders.is_icloud_connected(db)
    )


@router.put("/settings", response_model=SettingsResponse)
def update_settings(settings: SettingsUpdate, db: Session = Depends(get_db)):
    """Update sync settings."""
    set_setting(db, "sync_interval_minutes", str(settings.sync_interval_minutes))
    set_setting(db, "sync_direction", settings.sync_direction.value)
    
    if settings.gmail_task_list_id:
        set_setting(db, "gmail_task_list_id", settings.gmail_task_list_id)
    if settings.icloud_calendar_name:
        set_setting(db, "icloud_calendar_name", settings.icloud_calendar_name)
    
    # Restart scheduler with new interval
    sync_scheduler.start_sync_job(settings.sync_interval_minutes)
    
    return get_settings(db)


# ============ Sync Operations ============

@router.post("/sync/trigger", response_model=SyncTriggerResponse)
def trigger_sync(db: Session = Depends(get_db)):
    """Manually trigger a sync operation."""
    sync_log = run_sync(db)
    
    status_msg = "Sync completed successfully" if sync_log.status == SyncStatus.SUCCESS else f"Sync failed: {sync_log.error_message}"
    
    return SyncTriggerResponse(
        message=status_msg,
        sync_id=sync_log.id
    )


@router.get("/sync/logs", response_model=List[SyncLogResponse])
def get_sync_logs(
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db)
):
    """Get sync history logs."""
    logs = db.query(SyncLog).order_by(SyncLog.id.desc()).limit(limit).all()
    return [SyncLogResponse.model_validate(log) for log in logs]


@router.post("/scheduler/start")
def start_scheduler(db: Session = Depends(get_db)):
    """Start the sync scheduler."""
    interval = int(get_setting(db, "sync_interval_minutes", "15"))
    sync_scheduler.start_sync_job(interval)
    return {"message": "Scheduler started", "interval_minutes": interval}


@router.post("/scheduler/stop")
def stop_scheduler():
    """Stop the sync scheduler."""
    sync_scheduler.stop_sync_job()
    return {"message": "Scheduler stopped"}


# ============ Google Authentication ============

@router.get("/auth/google/url", response_model=GoogleAuthUrl)
def get_google_auth_url():
    """Get Google OAuth authorization URL."""
    auth_url = google_tasks.get_auth_url()
    return GoogleAuthUrl(auth_url=auth_url)


@router.get("/auth/google/callback")
def google_callback(code: str, db: Session = Depends(get_db)):
    """Handle Google OAuth callback."""
    try:
        google_tasks.exchange_code_for_tokens(code, db)
        return {"message": "Google authentication successful"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/google/tasklists", response_model=List[TaskListResponse])
def list_google_task_lists(db: Session = Depends(get_db)):
    """List available Google Task lists."""
    try:
        task_lists = google_tasks.list_task_lists(db)
        return [TaskListResponse(id=tl["id"], title=tl["title"]) for tl in task_lists]
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ iCloud Authentication ============

@router.post("/auth/icloud")
def set_icloud_credentials(credentials: ICloudCredentials, db: Session = Depends(get_db)):
    """Set iCloud credentials (username and app-specific password)."""
    try:
        icloud_reminders.save_icloud_credentials(db, credentials.username, credentials.app_password)
        
        # Verify connection
        if icloud_reminders.is_icloud_connected(db):
            return {"message": "iCloud credentials saved and verified"}
        else:
            raise HTTPException(status_code=401, detail="Could not connect to iCloud with provided credentials")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/icloud/calendars", response_model=List[CalendarResponse])
def list_icloud_calendars(db: Session = Depends(get_db)):
    """List available iCloud reminder lists."""
    try:
        calendars = icloud_reminders.list_reminder_calendars(db)
        return [CalendarResponse(
            id=c["id"],
            name=c["name"],
            color=c.get("color"),
            is_default=c.get("is_default", False)
        ) for c in calendars]
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
