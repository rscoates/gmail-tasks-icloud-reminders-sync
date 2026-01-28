from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.models import SyncStatus, SyncDirection


class SettingsUpdate(BaseModel):
    sync_interval_minutes: int
    sync_direction: SyncDirection
    gmail_task_list_id: Optional[str] = None
    icloud_calendar_name: Optional[str] = None


class SettingsResponse(BaseModel):
    sync_interval_minutes: int
    sync_direction: SyncDirection
    gmail_task_list_id: Optional[str] = None
    icloud_calendar_name: Optional[str] = None
    google_connected: bool = False
    icloud_connected: bool = False


class SyncLogResponse(BaseModel):
    id: int
    status: SyncStatus
    direction: SyncDirection
    tasks_synced: int
    reminders_synced: int
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SyncTriggerResponse(BaseModel):
    message: str
    sync_id: int


class GoogleAuthUrl(BaseModel):
    auth_url: str


class ICloudCredentials(BaseModel):
    username: str
    app_password: str


class TaskListResponse(BaseModel):
    id: str
    title: str


class CalendarResponse(BaseModel):
    id: str
    name: str
    color: Optional[str] = None
    is_default: bool = False


class StatusResponse(BaseModel):
    scheduler_running: bool
    next_sync_at: Optional[datetime] = None
    last_sync: Optional[SyncLogResponse] = None
    sync_interval_minutes: int
    google_connected: bool
    icloud_connected: bool
