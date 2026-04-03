from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from fastapi import Request
from sqlmodel import Session, select

# Internal Imports
from database import engine
from models import User, TripData, ClientData, RawTripData, OperationData, T3AddressLocality
from auth import verify_password, get_password_hash
from config import get_settings

cfg = get_settings()


# --- 1. AUTHENTICATION BACKEND ---
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form.get("username"), form.get("password")
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == username)).first()
            if user and verify_password(password, user.password_hash):
                request.session.update({"user": user.username})
                return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("user") in ["admin", "chickenman"]


# --- 2. ADMIN VIEWS ---
class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.username]

    async def on_model_change(self, data, model, is_created, request):
        password = data.get("password_hash")
        if password and not (len(password) == 60 and password.startswith("$")):
            hashed = get_password_hash(password)
            model.password_hash = hashed
            data["password_hash"] = hashed


class TripDataAdmin(ModelView, model=TripData):
    column_list = [TripData.shift_date, TripData.unique_id, TripData.employee_name]


class ClientDataAdmin(ModelView, model=ClientData):
    column_list = [ClientData.id, ClientData.unique_id]


class AddressLocalityAdmin(ModelView, model=T3AddressLocality):
    name = "Address Master"
    column_list = [T3AddressLocality.id, T3AddressLocality.address, T3AddressLocality.locality]


# --- 3. THE SETUP FUNCTION ---
def setup_admin(app):
    """
    This function is called by main.py.
    It attaches the Admin interface to the main FastAPI app.

    FIX: Use cfg.secret_key instead of a hardcoded string.
         A different key from the session key previously caused session
         conflicts on HTTPS platforms like Render.
    """
    admin = Admin(app, engine, authentication_backend=AdminAuth(secret_key=cfg.secret_key))

    # Add Views
    admin.add_view(UserAdmin)
    admin.add_view(TripDataAdmin)
    admin.add_view(ClientDataAdmin)
    admin.add_view(AddressLocalityAdmin)

    return admin