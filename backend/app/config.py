from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:postgres@db:5432/sync_db"
    
    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    
    # iCloud CalDAV
    icloud_username: str = ""
    icloud_app_password: str = ""
    
    # Sync settings
    default_sync_interval_minutes: int = 15
    
    # App settings
    app_secret_key: str = "change-this-in-production"
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
