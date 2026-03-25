from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, col
from database import get_session
from models import TripData
from datetime import datetime
import os
import io
from sqlalchemy import text
import pandas as pd
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form, Response, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

# SQLModel & Admin
from sqlmodel import select, Session, desc, col, update, SQLModel
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

# --- INTERNAL IMPORTS ---
from auth import verify_password, get_password_hash
from database import create_db_and_tables, get_session, engine
from models import User, ClientData, RawTripData, OperationData, TripData, T3AddressLocality, T3LocalityZone, T3ZoneKm, BARowData
from models import LocalityMappingSchema,BulkMappingSchema, NewMasterSchema


BASE_DIR = Path(__file__).resolve().parent.parent.parent
CLIENT_DIR = BASE_DIR / "client"

templates = Jinja2Templates(directory=str(CLIENT_DIR / "LocalityCorner"))

router = APIRouter()
# ==========================================
# 📍 LOCALITY MANAGER API (Complete)
# ==========================================

# 1. PAGE ROUTE
@router.get("/locality-manager")
async def locality_manager_page(request: Request):
    if not request.session.get("user"): return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
    "Localitycorner.html", 
    {"request": request, "user": request.session.get("user")}
)



# 2. API: Get Dropdown Data (One-line fetch & format)
@router.get("/api/dropdown-localities/")
def get_master_localities(session: Session = Depends(get_session)):
    return [
        {**loc.model_dump(), "billing_km": km or "-"} 
        for loc, km in session.exec(
            select(T3LocalityZone, T3ZoneKm.km)
            .join(T3ZoneKm, T3LocalityZone.zone == T3ZoneKm.zone, isouter=True)
            .order_by(T3LocalityZone.locality)
        ).all()
    ]

# 3. API: View All / Pagination
@router.get("/api/localities/")
def get_address_table(page: int = 1, search: str = "", session: Session = Depends(get_session)):
    limit = 20
    offset = (page - 1) * limit
    
    # Correct JOIN for your Schema: Address -> LocalityZone -> ZoneKm
    query = select(T3AddressLocality, T3LocalityZone, T3ZoneKm)\
        .join(T3LocalityZone, T3AddressLocality.locality == T3LocalityZone.locality, isouter=True)\
        .join(T3ZoneKm, T3LocalityZone.zone == T3ZoneKm.zone, isouter=True)\
        .order_by(desc(T3AddressLocality.id))
    
    if search:
        query = query.where(T3AddressLocality.address.contains(search))
    
    total_records = len(session.exec(select(T3AddressLocality).where(T3AddressLocality.address.contains(search))).all())
    pending_count = len(session.exec(select(T3AddressLocality).where(col(T3AddressLocality.locality).is_(None))).all())
    
    results = session.exec(query.offset(offset).limit(limit)).all()
    
    data = []
    for address_row, locality_row, zone_km_row in results:
        data.append({
            "id": address_row.id,
            "address": address_row.address,
            "locality_id": address_row.locality, # String is the ID here
            "locality": address_row.locality,
            "zone": locality_row.zone if locality_row else None, 
            "km": zone_km_row.km if zone_km_row else 0, # Fetch KM from joined table
            "status": "Done" if address_row.locality else "Pending"
        })
        
    return {
        "results": data,
        "pagination": {"total_pages": (total_records // limit) + 1},
        "global_pending": pending_count
    }

# 4. API: Get Next Pending Item
@router.get("/api/next-pending/")
def get_next_pending(session: Session = Depends(get_session)):
    row = session.exec(select(T3AddressLocality).where(col(T3AddressLocality.locality).is_(None)).limit(1)).first()
    if not row:
        return {"found": False}
    return {"found": True, "data": row}

# 5. API: Save Single Mapping
@router.post("/api/save-mapping/")
def save_mapping(data: LocalityMappingSchema, session: Session = Depends(get_session)):
    row = session.get(T3AddressLocality, data.address_id)
    if not row:
        return JSONResponse({"success": False, "error": "Address not found"}, status_code=404)
    
    # Update Relation
    row.locality = data.locality_name
    
    # Update Cache Fields (Zone/KM) automatically
    locality_info = session.exec(
        select(T3LocalityZone, T3ZoneKm)
        .join(T3ZoneKm, T3LocalityZone.zone == T3ZoneKm.zone, isouter=True)
        .where(T3LocalityZone.locality == data.locality_name)
    ).first()

    if locality_info:
        loc_row, km_row = locality_info
        row.zone = loc_row.zone
        row.km = km_row.km if km_row else None

    session.add(row)
    session.commit()
    return {"success": True}

# 6. API: Search Pending
@router.get("/api/search-pending/")
def search_pending(q: str = "", page: int = 1, session: Session = Depends(get_session)):
    limit = 50
    offset = (page - 1) * limit
    
    query = select(T3AddressLocality).where(col(T3AddressLocality.locality).is_(None))
    if q:
        query = query.where(T3AddressLocality.address.contains(q))
        
    total = len(session.exec(query).all())
    results = session.exec(query.offset(offset).limit(limit)).all()
    
    return {
        "results": results,
        "pagination": {"total_records": total}
    }

# 7. API: Bulk Save
@router.post("/api/bulk-save/")
def bulk_save(data: BulkMappingSchema, session: Session = Depends(get_session)):
    cache_values = {"locality": data.locality_name}
    
    locality_info = session.exec(
        select(T3LocalityZone, T3ZoneKm)
        .join(T3ZoneKm, T3LocalityZone.zone == T3ZoneKm.zone, isouter=True)
        .where(T3LocalityZone.locality == data.locality_name)
    ).first()

    if locality_info:
        loc_row, km_row = locality_info
        cache_values["zone"] = loc_row.zone
        cache_values["km"] = km_row.km if km_row else None

    statement = (
        update(T3AddressLocality)
        .where(col(T3AddressLocality.id).in_(data.address_ids))
        .values(**cache_values)
    )
    result = session.exec(statement)
    session.commit()
    return {"success": True, "count": result.rowcount}

# 8. API: Add New Master Locality
@router.post("/api/add-master-locality/")
def add_master(data: NewMasterSchema, session: Session = Depends(get_session)):
    try:
        # Auto-create Zone if missing to avoid FK error
        if not session.get(T3ZoneKm, data.zone_name):
             session.add(T3ZoneKm(zone=data.zone_name, km="0")) 
        
        new_loc = T3LocalityZone(locality=data.locality_name, zone=data.zone_name)
        session.add(new_loc)
        session.commit()
        return {"success": True}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)