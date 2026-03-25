from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional

# Internal Imports
from database import get_session
from models import TripData  # Assuming TripData is the model holding these fields

router = APIRouter(prefix="/api", tags=["GPS"])

# --- PYDANTIC MODEL FOR INCOMING DATA ---
class GPSUpdatePayload(BaseModel):
    journey_start: Optional[str] = None
    journey_end: Optional[str] = None
    gps_time: Optional[str] = None
    gps_remark: Optional[str] = None

# --- 1. FETCH TRIPS API ---
@router.get("/gps_trips")
def get_gps_trips(
    date: Optional[str] = Query(None),
    vehicle: Optional[str] = Query(None),
    trip_direction: Optional[str] = Query(None),
    trip_id: Optional[str] = Query(None),
    session: Session = Depends(get_session)
):
    # Start with a base query
    statement = select(TripData)

    # Apply filters dynamically if they exist in the URL
    if date:
        statement = statement.where(TripData.trip_date == date)
    if vehicle:
        statement = statement.where(TripData.cab_reg_no.icontains(vehicle))
    if trip_direction:
        statement = statement.where(TripData.trip_direction.icontains(trip_direction))
    if trip_id:
        statement = statement.where(TripData.trip_id.icontains(trip_id))

    # Execute query
    trips = session.exec(statement).all()
    
    return trips

# --- 2. UPDATE GPS DATA API ---
@router.post("/update_gps/{unique_id}")
def update_gps_data(
    unique_id: str,
    payload: GPSUpdatePayload,
    session: Session = Depends(get_session)
):
    # Find the specific trip by its unique ID
    trip = session.exec(select(TripData).where(TripData.unique_id == unique_id)).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Update the fields
    trip.journey_start_location = payload.journey_start
    trip.journey_end_location = payload.journey_end
    trip.gps_time = payload.gps_time
    trip.gps_remark = payload.gps_remark

    # Save to database
    session.add(trip)
    session.commit()
    session.refresh(trip)

    return {"message": "GPS data updated successfully", "status": "success"}

"""
ADD these two endpoints to your existing GPS router file.
Also add TollData to your imports if not already present:
    from models import TripData, TollData
"""

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional

from database import get_session
from models import TripData, TollData


# ── Paste this model alongside your existing ones ──
class UpdateTollRequest(BaseModel):
    toll_name:   str
    toll_amount: float


# ── Helper (reuse if already defined elsewhere) ──
def _clean(d: dict) -> dict:
    return {k: (None if (v is not None and pd.isna(v)) else v) for k, v in d.items()}


# ══════════════════════════════════════════════════════════
#  GET /api/gps_trips_with_tolls
#  Returns every trip (filtered by query params) together
#  with its candidate tolls from the TollData table,
#  matched on cab number within ±1.5 h of shift time.
#  Already-linked trips carry their assigned tolls.
# ══════════════════════════════════════════════════════════
@router.get("/gps_trips_with_tolls")
def get_gps_trips_with_tolls(
    date:           Optional[str] = None,
    vehicle:        Optional[str] = None,
    trip_direction: Optional[str] = None,
    trip_id:        Optional[str] = None,
    session: Session = Depends(get_session)
):
    # 1. Build trip query with optional filters
    stmt = select(TripData)
    if date:
        stmt = stmt.where(TripData.shift_date == date)
    if vehicle:
        stmt = stmt.where(TripData.cab_reg_no == vehicle)
    if trip_direction:
        stmt = stmt.where(TripData.trip_direction.ilike(f"%{trip_direction}%"))
    if trip_id:
        stmt = stmt.where(TripData.trip_id == trip_id)

    trips = session.exec(stmt).all()
    if not trips:
        return []

    # 2. Fetch ALL tolls (needed for both pending matches and linked lookups)
    all_tolls = session.exec(select(TollData)).all()

    df_trips = pd.DataFrame([t.model_dump() for t in trips])
    df_tolls = pd.DataFrame([t.model_dump() for t in all_tolls]) if all_tolls else pd.DataFrame()

    # 3. Prepare columns
    df_trips['cab_clean'] = df_trips['cab_reg_no'].astype(str).str.strip().str.upper()
    df_trips['trip_dt']   = pd.to_datetime(
        df_trips['shift_date'].astype(str) + ' ' + df_trips['shift_time'].astype(str),
        errors='coerce', dayfirst=True
    )

    if not df_tolls.empty:
        df_tolls['veh_clean'] = df_tolls['veh'].astype(str).str.strip().str.upper()
        df_tolls['toll_dt']   = pd.to_datetime(
            df_tolls['travel_date_time'], errors='coerce', dayfirst=True
        )

    # 4. Pre-build linked-toll lookup: trip unique_id → [toll dicts]
    linked_map = {}
    if not df_tolls.empty and 'unique_id' in df_tolls.columns:
        for _, trow in df_tolls.iterrows():
            uid = str(trow.get('unique_id') or '').strip()
            if uid:
                td = _clean(trow.to_dict())
                td.pop('toll_dt',   None)
                td.pop('veh_clean', None)
                linked_map.setdefault(uid, []).append(td)

    result = []

    for _, trip in df_trips.iterrows():
        trip_dict = _clean(trip.to_dict())
        trip_dict.pop('trip_dt',   None)
        trip_dict.pop('cab_clean', None)

        trip_uid  = str(trip.get('unique_id') or '').strip()
        toll_name = str(trip.get('toll_name') or '').strip()
        is_linked = toll_name not in ('', 'None', 'nan')

        if is_linked:
            # Already linked — return the tolls assigned to this trip
            toll_list = linked_map.get(trip_uid, [])
        else:
            # Pending — find candidate tolls within ±1.5 h
            toll_list = []
            if not df_tolls.empty and not pd.isna(trip['trip_dt']):
                unassigned = df_tolls[
                    df_tolls['unique_id'].isna() |
                    (df_tolls['unique_id'].astype(str).str.strip() == '')
                ]
                veh_tolls = unassigned[unassigned['veh_clean'] == trip['cab_clean']]
                if not veh_tolls.empty:
                    diffs = (veh_tolls['toll_dt'] - trip['trip_dt']).dt.total_seconds() / 3600.0
                    valid = veh_tolls[(diffs >= -1.5) & (diffs <= 1.5)]
                    for _, trow in valid.iterrows():
                        td = _clean(trow.to_dict())
                        td.pop('toll_dt',   None)
                        td.pop('veh_clean', None)
                        toll_list.append(td)

        result.append({
            "trip":  trip_dict,
            "tolls": toll_list
        })

    return result


# ══════════════════════════════════════════════════════════
#  POST /api/update_toll/{unique_id}
#  Manually set toll_name + toll_amount on a trip
# ══════════════════════════════════════════════════════════
@router.post("/update_toll/{unique_id}")
def update_toll(
    unique_id: str,
    payload:   UpdateTollRequest,
    session:   Session = Depends(get_session)
):
    trip = session.exec(
        select(TripData).where(TripData.unique_id == unique_id)
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    trip.toll_name   = payload.toll_name
    trip.toll_amount = payload.toll_amount
    session.add(trip)
    session.commit()
    return {"message": "Toll updated successfully"}