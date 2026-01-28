from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import engine, Base
from app.routes import router
from app.services.scheduler import sync_scheduler
from app.services.sync_service import get_setting
from app.database import SessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    
    # Start scheduler if previously configured
    db = SessionLocal()
    try:
        interval = get_setting(db, "sync_interval_minutes")
        if interval:
            sync_scheduler.start_sync_job(int(interval))
    finally:
        db.close()
    
    yield
    
    # Shutdown
    sync_scheduler.stop_sync_job()


app = FastAPI(
    title="Gmail-Reminder Sync",
    description="Synchronize Gmail Tasks with iOS Reminders",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"message": "Gmail-Reminder Sync API", "docs": "/docs"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
