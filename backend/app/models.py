from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from app.database import Base
import enum


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class SyncDirection(str, enum.Enum):
    GMAIL_TO_ICLOUD = "gmail_to_icloud"
    ICLOUD_TO_GMAIL = "icloud_to_gmail"
    BIDIRECTIONAL = "bidirectional"


class Settings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SyncLog(Base):
    __tablename__ = "sync_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(SQLEnum(SyncStatus), default=SyncStatus.PENDING)
    direction = Column(SQLEnum(SyncDirection), default=SyncDirection.BIDIRECTIONAL)
    tasks_synced = Column(Integer, default=0)
    reminders_synced = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class TaskMapping(Base):
    """Maps Gmail Task IDs to iCloud Reminder IDs for sync tracking"""
    __tablename__ = "task_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    gmail_task_id = Column(String(255), unique=True, nullable=False, index=True)
    gmail_task_list_id = Column(String(255), nullable=False)
    icloud_reminder_uid = Column(String(255), unique=True, nullable=True, index=True)
    icloud_calendar_url = Column(Text, nullable=True)
    title = Column(String(500), nullable=False)
    last_known_completed = Column(Boolean, default=False)  # Track last synced completion status
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Credential(Base):
    """Stores OAuth tokens and credentials securely"""
    __tablename__ = "credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    service = Column(String(50), unique=True, nullable=False)  # 'google' or 'icloud'
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expiry = Column(DateTime(timezone=True), nullable=True)
    extra_data = Column(Text, nullable=True)  # JSON for additional data
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
