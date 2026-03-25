# MIS — Management Information System v2.0

> Clean dark UI · FastAPI backend · `.env` config · Fully responsive

## Project Structure

```
mis/
├── client/                  ← Frontend (HTML/CSS/JS)
│   ├── Components/
│   │   ├── theme.css        ← Shared dark design system
│   │   ├── Sidebar.css
│   │   └── Sidebar.js
│   ├── LoginPage/
│   ├── HomePage/
│   ├── DataCleaner/
│   ├── LocalityCorner/
│   ├── GPSCorner/
│   ├── B2BCorner/
│   ├── OperationManager/
│   └── Toll_routes/
└── server/                  ← FastAPI backend
    ├── .env                 ← ⭐ Environment config (edit this)
    ├── config.py            ← Reads .env, single source of truth
    ├── main.py
    ├── database.py
    ├── models.py
    ├── auth.py
    ├── admin.py
    ├── requirements.txt
    ├── api/
    └── cleaner/
```

## Quick Start

### 1. Configure environment
```bash
cd server
# Edit .env with your settings:
nano .env
```

Key settings:
| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `CHANGE_ME` | **Must change** — session security |
| `DATABASE_URL` | `sqlite:///./mis.db` | SQLite (dev) or PostgreSQL (prod) |
| `CORS_ORIGINS` | `http://localhost:8000` | Allowed origins |
| `COMPANY_NAME` | `T3 Logistics` | Shown in UI |

### 2. Install dependencies
```bash
cd server
pip install -r requirements.txt
```

### 3. Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Open
Visit [http://localhost:8000](http://localhost:8000)

---

## Production (Render / Railway)

Set these environment variables on your host:

```
DATABASE_URL=postgresql://user:pass@host:5432/db
SECRET_KEY=<openssl rand -hex 32>
CORS_ORIGINS=https://yourdomain.com
APP_DEBUG=false
```

The `RENDER` environment variable is automatically detected to enable HTTPS-only cookies.

---

## Design System

All pages use a shared dark token system in `client/Components/theme.css`:

- **Colors**: `var(--accent)` (red), `var(--cyan)`, `var(--green)`, `var(--amber)`, `var(--purple)`
- **Surfaces**: `--bg-base`, `--bg-surface`, `--bg-elevated`, `--bg-overlay`
- **Typography**: DM Sans + JetBrains Mono
- **Components**: `.card`, `.btn`, `.form-input`, `.table-wrapper`, `.badge`, `.drop-zone`, `.alert`

To create a new page:
```html
<link rel="stylesheet" href="/components-static/theme.css">
<link rel="stylesheet" href="/components-static/Sidebar.css">
<script src="/components-static/Sidebar.js" defer></script>
```
