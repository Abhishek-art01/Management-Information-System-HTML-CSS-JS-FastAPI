"""
create_admin.py — Create the first admin user for MIS.
Run once from the server/ folder (with venv active):

    python create_admin.py
"""
import sys
from sqlmodel import Session, select
from database import engine, create_db_and_tables
from models import User
from auth import get_password_hash
from dotenv import load_dotenv
import os

load_dotenv()

# ── Config — change these before running ─────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
# ─────────────────────────────────────────────────────────────

def create_admin():
    create_db_and_tables()

    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.username == ADMIN_USERNAME)
        ).first()

        if existing:
            print(f"⚠️  User '{ADMIN_USERNAME}' already exists. No changes made.")
            sys.exit(0)

        user = User(
            username=ADMIN_USERNAME,
            password_hash=get_password_hash(ADMIN_PASSWORD),
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    print("=" * 40)
    print("✅  Admin user created successfully!")
    print(f"    Username : {ADMIN_USERNAME}")
    print(f"    Password : {ADMIN_PASSWORD}")
    print("=" * 40)
    print("👉  Login at http://localhost:8000/login")
    print("⚠️  Change your password after first login.")

if __name__ == "__main__":
    create_admin()