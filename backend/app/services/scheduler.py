from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from typing import Optional

from app.database import SessionLocal
from app.services.sync_service import run_sync, get_setting


class SyncScheduler:
    _instance = None
    _scheduler: Optional[BackgroundScheduler] = None
    _job_id = "sync_job"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._scheduler = BackgroundScheduler()
            cls._scheduler.start()
        return cls._instance
    
    @property
    def scheduler(self) -> BackgroundScheduler:
        return self._scheduler
    
    def _run_sync_job(self):
        """Execute sync job with its own database session."""
        db = SessionLocal()
        try:
            run_sync(db)
        except Exception as e:
            print(f"Scheduled sync error: {e}")
        finally:
            db.close()
    
    def start_sync_job(self, interval_minutes: int = None):
        """Start or update the sync job."""
        if interval_minutes is None:
            db = SessionLocal()
            try:
                interval_str = get_setting(db, "sync_interval_minutes", "15")
                interval_minutes = int(interval_str)
            finally:
                db.close()
        
        # Remove existing job if any
        self.stop_sync_job()
        
        # Add new job
        self._scheduler.add_job(
            self._run_sync_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=self._job_id,
            name="Gmail-iCloud Sync",
            replace_existing=True
        )
        
        print(f"Sync job scheduled to run every {interval_minutes} minutes")
    
    def stop_sync_job(self):
        """Stop the sync job."""
        try:
            self._scheduler.remove_job(self._job_id)
        except Exception:
            pass  # Job doesn't exist
    
    def is_running(self) -> bool:
        """Check if the sync job is scheduled."""
        job = self._scheduler.get_job(self._job_id)
        return job is not None
    
    def get_next_run_time(self) -> Optional[datetime]:
        """Get the next scheduled run time."""
        job = self._scheduler.get_job(self._job_id)
        return job.next_run_time if job else None
    
    def trigger_now(self):
        """Trigger an immediate sync."""
        db = SessionLocal()
        try:
            return run_sync(db)
        finally:
            db.close()


# Global scheduler instance
sync_scheduler = SyncScheduler()
