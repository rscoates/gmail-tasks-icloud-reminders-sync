# Gmail-Reminder Sync

A macOS application that synchronizes Gmail Tasks with iCloud Reminders using Apple's native EventKit framework. Features a web frontend for monitoring and manual sync triggers with a configurable sync interval.

## Features

- 🔄 **Bidirectional Sync**: Sync tasks from Gmail to iCloud and vice versa
- ✅ **Completion Status Sync**: Mark complete on either side and it syncs
- ⏰ **Scheduled Sync**: Configure sync interval from the web UI (default: 15 minutes)
- 🖥️ **Web Dashboard**: Monitor sync status, view history, and trigger manual syncs
- 🐳 **Partially Dockerized**: Database and frontend in Docker, backend runs natively on macOS, and has to for now.
- 🔐 **Secure**: OAuth 2.0 for Google authentication

## Requirements

- **macOS 13 (Ventura) or later** - Required for EventKit access
- **Docker & Docker Compose** - For database and frontend
- **Python 3.9+** - For running the backend
- **Google Cloud Project** with Tasks API enabled

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│    Backend      │────▶│   PostgreSQL    │
│   (Nginx/HTML)  │     │   (FastAPI)     │     │   (Docker)      │
│    (Docker)     │     │  (Native macOS) │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            ┌─────────────┐     ┌─────────────┐
            │   Google    │     │   macOS     │
            │  Tasks API  │     │  EventKit   │
            └─────────────┘     └─────────────┘
                                      │
                                ┌─────┴─────┐
                                ▼           ▼
                           iCloud      Local
                          Reminders   Reminders
```

> **Note**: The backend must run natively on macOS because it uses Apple's EventKit
> framework to access Reminders. **This cannot run in Docker!!!!**.

1. **Docker & Docker Compose** installed
2. **Google Cloud Project** with Tasks API enabled
3. **Apple ID** with App-Specific Password

## Quick Start

### 1. Clone and Configure

```bash
git clone <repo-url>
cd gmail-reminder-sync
cp .env.example .env
```

### 2. Set Up Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the **Google Tasks API**
4. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client IDs**
5. Set application type to **Web application**
6. Add authorized redirect URI: `http://localhost:8000/api/auth/google/callback`
7. Copy **Client ID** and **Client Secret** to your `.env` file

### 3. Start Docker Services

```bash
# Start the database and frontend
docker compose up -d
```

### 4. Start the Backend (Native macOS)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the backend
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sync_db \
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **First Run**: macOS will prompt you to grant Reminders access. Click "Allow".
> If the prompt doesn't appear, check System Settings → Privacy & Security → Reminders.

### 5. Access the Dashboard

Open http://localhost in your browser

1. Click "Connect Google" and authorize access
2. Select your Google Task List and iCloud Reminder List
3. Click "Save Settings" then "Sync Now"

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required: Google OAuth credentials
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback

# Optional
DEFAULT_SYNC_INTERVAL_MINUTES=15
```

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | Required |
| `GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret | Required |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | `http://localhost:8000/api/auth/google/callback` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/sync_db` |
| `DEFAULT_SYNC_INTERVAL_MINUTES` | Default sync interval | `15` |

### Sync Directions

- **Bidirectional**: Sync both ways (default)
- **Gmail → iCloud**: Only sync Gmail Tasks to iCloud Reminders
- **iCloud → Gmail**: Only sync iCloud Reminders to Gmail Tasks

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Get current sync status |
| `/api/settings` | GET/PUT | Get or update settings |
| `/api/sync/trigger` | POST | Manually trigger sync |
| `/api/sync/logs` | GET | Get sync history |
| `/api/scheduler/start` | POST | Start the scheduler |
| `/api/scheduler/stop` | POST | Stop the scheduler |
| `/api/auth/google/url` | GET | Get Google auth URL |
| `/api/auth/icloud` | POST | Set iCloud credentials |
| `/api/google/tasklists` | GET | List Google Task lists |
| `/api/icloud/calendars` | GET | List iCloud calendars |

Full API documentation available at http://localhost:8000/docs

## Development

### Project Structure

```
gmail-reminder-sync/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   ├── google_tasks.py    # Google Tasks API
│   │   │   ├── icloud_reminders.py # EventKit integration
│   │   │   ├── sync_service.py    # Sync logic
│   │   │   └── scheduler.py       # Background scheduler
│   │   ├── main.py                # FastAPI app
│   │   ├── routes.py              # API endpoints
│   │   └── models.py              # Database models
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── docker-compose.yml
```

### Run Backend in Development Mode

```bash
cd backend
source venv/bin/activate
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sync_db \
  python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### View Database

```bash
docker exec -it sync-db psql -U postgres -d sync_db
```

### View Logs

```bash
# Frontend/nginx logs
docker compose logs -f frontend

# Backend logs are in your terminal running uvicorn
```

## Troubleshooting

### macOS Reminders Permission

If reminders aren't syncing:
1. Go to **System Settings** → **Privacy & Security** → **Reminders**
2. Ensure **Terminal** (or your IDE) has access
3. If not listed, run the backend once to trigger the permission prompt

### Google Auth Issues

- Ensure redirect URI matches exactly in Google Console and your request
- Check that **Tasks API** is enabled in your Google Cloud project
- If scopes changed, you may need to re-authenticate

### Sync Not Working

- Check the sync logs in the dashboard
- Ensure both Google is connected (green badge)
- Verify a Task List and Reminder List are selected
- Check that reminders aren't being filtered (completed tasks need `showHidden=True`)

## License

MIT License
