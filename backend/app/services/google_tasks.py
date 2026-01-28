from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from typing import List, Optional
import json
from datetime import datetime
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Credential

settings = get_settings()

SCOPES = ['https://www.googleapis.com/auth/tasks']


def get_google_auth_flow() -> Flow:
    """Create OAuth flow for Google authentication."""
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [settings.google_redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri
    )
    return flow


def get_auth_url() -> str:
    """Generate Google OAuth authorization URL."""
    flow = get_google_auth_flow()
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return auth_url


def exchange_code_for_tokens(code: str, db: Session) -> Credentials:
    """Exchange authorization code for tokens and store them."""
    flow = get_google_auth_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    # Store credentials in database
    cred_record = db.query(Credential).filter(Credential.service == "google").first()
    
    cred_data = {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        "extra_data": json.dumps({
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else SCOPES
        })
    }
    
    if cred_record:
        for key, value in cred_data.items():
            setattr(cred_record, key, value)
    else:
        cred_record = Credential(service="google", **cred_data)
        db.add(cred_record)
    
    db.commit()
    return credentials


def get_google_credentials(db: Session) -> Optional[Credentials]:
    """Retrieve stored Google credentials."""
    cred_record = db.query(Credential).filter(Credential.service == "google").first()
    
    if not cred_record or not cred_record.access_token:
        return None
    
    extra_data = json.loads(cred_record.extra_data) if cred_record.extra_data else {}
    
    credentials = Credentials(
        token=cred_record.access_token,
        refresh_token=cred_record.refresh_token,
        token_uri=extra_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=extra_data.get("client_id", settings.google_client_id),
        client_secret=extra_data.get("client_secret", settings.google_client_secret),
        scopes=extra_data.get("scopes", SCOPES)
    )
    
    return credentials


def get_tasks_service(db: Session):
    """Get Google Tasks API service."""
    credentials = get_google_credentials(db)
    if not credentials:
        raise ValueError("Google credentials not found. Please authenticate first.")
    
    return build('tasks', 'v1', credentials=credentials)


def list_task_lists(db: Session) -> List[dict]:
    """List all Google Tasks lists."""
    service = get_tasks_service(db)
    results = service.tasklists().list().execute()
    return results.get('items', [])


def list_tasks(db: Session, task_list_id: str = '@default') -> List[dict]:
    """List all tasks in a task list, handling pagination."""
    service = get_tasks_service(db)
    all_tasks = []
    page_token = None
    
    while True:
        results = service.tasks().list(
            tasklist=task_list_id,
            showCompleted=True,
            showHidden=True,  # Include hidden/completed tasks
            maxResults=100,   # Get more per page
            pageToken=page_token
        ).execute()
        
        tasks = results.get('items', [])
        all_tasks.extend(tasks)
        
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    
    return all_tasks


def create_task(db: Session, task_list_id: str, title: str, notes: str = None, due: datetime = None, status: str = None) -> dict:
    """Create a new task in Google Tasks."""
    service = get_tasks_service(db)
    
    task_body = {'title': title}
    if notes:
        task_body['notes'] = notes
    if due:
        task_body['due'] = due.isoformat() + 'Z'
    if status:
        task_body['status'] = status
    
    return service.tasks().insert(tasklist=task_list_id, body=task_body).execute()


def update_task(db: Session, task_list_id: str, task_id: str, **kwargs) -> dict:
    """Update an existing task."""
    service = get_tasks_service(db)
    
    # Get current task
    task = service.tasks().get(tasklist=task_list_id, task=task_id).execute()
    
    # Update fields
    for key, value in kwargs.items():
        if value is not None:
            task[key] = value
    
    return service.tasks().update(tasklist=task_list_id, task=task_id, body=task).execute()


def delete_task(db: Session, task_list_id: str, task_id: str):
    """Delete a task."""
    service = get_tasks_service(db)
    service.tasks().delete(tasklist=task_list_id, task=task_id).execute()


def is_google_connected(db: Session) -> bool:
    """Check if Google is authenticated."""
    try:
        creds = get_google_credentials(db)
        return creds is not None
    except Exception:
        return False
