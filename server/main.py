"""
main.py — FastAPI application entry-point.
All configuration is read from .env via config.py.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

# ── FIX: Import ProxyHeadersMiddleware so Starlette sees the correct
#         HTTPS scheme when running behind Render's reverse proxy.
#         Without this, scope["scheme"] is always "http" internally,
#         which breaks https_only=True cookie handling.
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from config import get_settings
from database import create_db_and_tables, engine
from admin import setup_admin
from api import cleaner_api, locality_api, download_api, gps_api, toll_api
from api import pages_api

# ── Paths ─────────────────────────────────────────────────────────────────────
cfg = get_settings()
BASE_DIR = Path(__file__).resolve().parent
CLIENT_DIR = BASE_DIR.parent / "client"

STATIC: dict[str, Path] = {
    "home":               CLIENT_DIR / "HomePage",
    "login":              CLIENT_DIR / "LoginPage",
    "cleaner":            CLIENT_DIR / "DataCleaner",
    "operation-manager":  CLIENT_DIR / "OperationManager",
    "locality":           CLIENT_DIR / "LocalityCorner",
    "components":         CLIENT_DIR / "Components",
    "gps":                CLIENT_DIR / "GPSCorner",
    "toll":               CLIENT_DIR / "Toll_routes",
}


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()

    # Fix auto-increment sequence drift on PostgreSQL
    if cfg.is_postgres:
        try:
            with Session(engine) as s:
                s.exec(
                    text(
                        "SELECT setval(pg_get_serial_sequence('t3_address_locality','id'),"
                        " coalesce(max(id),0)+1, false) FROM t3_address_locality;"
                    )
                )
                s.commit()
        except Exception:
            pass

    yield


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=cfg.app_title,
    version=cfg.app_version,
    debug=cfg.app_debug,
    lifespan=lifespan,
)

# ── FIX: Add ProxyHeadersMiddleware FIRST (outermost wrapper).
#         trusted_hosts="*" tells uvicorn to trust X-Forwarded-Proto from
#         Render's load balancer, so scope["scheme"] becomes "https".
#         This is what makes https_only=True work correctly on Render.
if cfg.is_render:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=cfg.secret_key,
    max_age=cfg.session_max_age,
    # ── FIX: Always use https_only=True on Render (now safe because
    #         ProxyHeadersMiddleware above makes the scheme correct).
    #         Use False locally so http://localhost still works.
    https_only=cfg.is_render,
    same_site="lax",
)

# ── Routers ───────────────────────────────────────────────────────────────────
for router_module in (pages_api, cleaner_api, locality_api, download_api, gps_api, toll_api):
    app.include_router(router_module.router)

# ── Static files ──────────────────────────────────────────────────────────────
_mounts = [
    ("/home-static",               "home"),
    ("/login-static",              "login"),
    ("/cleaner-static",            "cleaner"),
    ("/locality-static",           "locality"),
    ("/operation-manager-static",  "operation-manager"),
    ("/components-static",         "components"),
    ("/Components",                "components"),
    ("/gps-static",                "gps"),
    ("/toll-static",               "toll"),
]

for url_path, key in _mounts:
    target = STATIC[key]
    if target.exists():
        app.mount(url_path, StaticFiles(directory=target), name=f"static_{key}_{url_path.strip('/')}")

setup_admin(app)