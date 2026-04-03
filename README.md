# MIS — Management Information System v2.0

> Clean dark UI · FastAPI backend · `.env` config · Fully responsive

---

## Requirements

| Tool | Minimum version | Check |
|---|---|---|
| Python | 3.10+ | `python --version` |
| pip | any recent | `pip --version` |

No Node.js, Docker, or external services needed for local development.

---

## Project Structure

```
mis/
├── client/                  ← Frontend (HTML / CSS / JS — no build step)
│   ├── Components/
│   │   ├── theme.css        ← Shared dark design system
│   │   ├── Sidebar.css
│   │   └── Sidebar.js
│   ├── LoginPage/
│   ├── HomePage/
│   ├── DataCleaner/
│   ├── LocalityCorner/
│   ├── GPSCorner/
│   ├── OperationManager/
│   └── TollRoutes/
└── server/                  ← FastAPI backend
    ├── .env.example         ← ⭐ Copy to .env and fill in values
    ├── .env                 ← Your local config (git-ignored)
    ├── config.py            ← Reads .env — single source of truth
    ├── main.py              ← App entry-point + middleware
    ├── database.py
    ├── models.py
    ├── auth.py
    ├── admin.py
    ├── requirements.txt
    ├── api/
    └── cleaner/
```

---

## Local Setup (Step by Step)

### Step 1 — Clone the repo

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
```

### Step 2 — Create a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the start of your terminal prompt.

### Step 3 — Install dependencies

```bash
cd server
pip install -r requirements.txt
```

This installs FastAPI, uvicorn, SQLModel, bcrypt, pandas, sqladmin, and all other packages.

### Step 4 — Create your `.env` file

```bash
# From inside the server/ folder:
cp .env.example .env
```

Then open `.env` and set a real secret key:

```bash
# Generate a secure key (run this in your terminal):
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and paste it as your `SECRET_KEY` in `.env`. The SQLite database needs no extra setup — it creates itself automatically.

### Step 5 — Run the server

```bash
# Make sure you are inside the server/ folder
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

`--reload` restarts the server automatically when you edit Python files.

### Step 6 — Create your first user

The app has no default users. You must create one via the admin panel.

1. Open [http://localhost:8000/admin](http://localhost:8000/admin)
2. Log in with **any** username and password — the first login to `/admin` bypasses auth if no users exist yet, **or** use the SQLite approach below.

**Easier method — create a user directly from Python:**

```bash
# Run this once from inside the server/ folder (with .venv active)
python - <<'EOF'
from sqlmodel import Session
from database import engine, create_db_and_tables
from models import User
from auth import get_password_hash

create_db_and_tables()

with Session(engine) as session:
    user = User(
        username="admin",
        password_hash=get_password_hash("your-password-here")
    )
    session.add(user)
    session.commit()
    print("✅ User created successfully")
EOF
```

Replace `"admin"` and `"your-password-here"` with your preferred credentials.

### Step 7 — Open the app

Visit [http://localhost:8000](http://localhost:8000) and log in with the credentials you just created.

---

## Environment Variables Reference

All variables live in `server/.env`. See `.env.example` for a template.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `CHANGE_ME` | **Must change.** Signs session cookies. |
| `SESSION_MAX_AGE` | `3600` | Session lifetime in seconds. |
| `DATABASE_URL` | `sqlite:///./mis.db` | SQLite (local) or PostgreSQL (prod). |
| `CORS_ORIGINS` | `http://localhost:8000,...` | Comma-separated allowed origins. |
| `APP_DEBUG` | `false` | Set `true` to see SQL queries in terminal. |
| `COMPANY_NAME` | `T3 Logistics` | Displayed in the UI. |

---

## Admin Panel

The built-in admin panel is available at `/admin`. It lets you:

- Create, edit, and delete **Users**
- Browse **TripData**, **ClientData**, **Address Locality** tables
- Set passwords — they are automatically hashed when saved through the panel

---

## Common Issues

**Port already in use**
```bash
# Kill whatever is on port 8000 and retry
# macOS / Linux:
lsof -ti:8000 | xargs kill -9
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**`ModuleNotFoundError`**
Make sure your virtual environment is activated (`(.venv)` in prompt) and you ran `pip install -r requirements.txt` from inside `server/`.

**`sqlite3.OperationalError: no such table`**
The database creates itself on first run. If you see this error, stop the server, delete `mis.db` if it exists, and restart.

**Login works locally but not on Render**
See the Render deployment section below — this is a proxy/HTTPS configuration issue that is already fixed in `main.py`.

---

## Render Deployment

### Required environment variables on Render

Set these in your Render service dashboard under **Environment**:

| Variable | Value |
|---|---|
| `SECRET_KEY` | A long random string — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Your PostgreSQL connection string from Render's database dashboard |
| `CORS_ORIGINS` | `https://your-app-name.onrender.com` |
| `APP_DEBUG` | `false` |

### Render start command

In your Render service settings, set the **Start Command** to:

```
uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
```

`--proxy-headers` and `--forwarded-allow-ips='*'` tell uvicorn to trust Render's load balancer, which is required for HTTPS session cookies to work correctly.

### Create your first user on Render

Use Render's **Shell** tab (in your service dashboard) and run:

```bash
python - <<'EOF'
from sqlmodel import Session
from database import engine, create_db_and_tables
from models import User
from auth import get_password_hash

create_db_and_tables()

with Session(engine) as session:
    user = User(
        username="admin",
        password_hash=get_password_hash("your-password-here")
    )
    session.add(user)
    session.commit()
    print("User created")
EOF
```

---

## Design System

All pages share the dark token system in `client/Components/theme.css`.

To add a new page, include these three lines in its `<head>`:

```html
<link rel="stylesheet" href="/components-static/theme.css">
<link rel="stylesheet" href="/components-static/Sidebar.css">
<script src="/components-static/Sidebar.js" defer></script>
```

Key CSS variables:

| Variable | Use |
|---|---|
| `--accent` | Primary red accent |
| `--cyan`, `--green`, `--amber`, `--purple` | Status / badge colours |
| `--bg-base`, `--bg-surface`, `--bg-elevated` | Dark background layers |
| `--text-primary`, `--text-secondary`, `--text-muted` | Text hierarchy |