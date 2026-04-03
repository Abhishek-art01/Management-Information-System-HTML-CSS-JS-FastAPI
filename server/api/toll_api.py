import pandas as pd
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List, Optional

from database import get_session
from models import TripData, TollData, TollRouteRule

router = APIRouter(prefix="/api/toll", tags=["Toll Audit"])


# ─────────────────────────────────────────────
#  PYDANTIC SCHEMAS
# ─────────────────────────────────────────────

class MarkTollRequest(BaseModel):
    trip_unique_id: str
    selected_toll_ids: List[str]


class TollRouteRuleRequest(BaseModel):
    landmark:      str
    office:        str
    toll_name:     str      # transaction_description from TollData
    is_toll_route: bool     # True = toll route | False = NOT a toll route


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def clean_val(v):
    try:
        if v is None: return None
        if isinstance(v, float) and pd.isna(v): return None
        if isinstance(v, pd.Timestamp) and pd.isna(v): return None
        return v
    except Exception:
        return v


def clean_dict(d: dict) -> dict:
    return {k: clean_val(v) for k, v in d.items()}


def is_blank(val) -> bool:
    if val is None: return True
    return str(val).strip().lower() in ("", "none", "nan", "nat", "0")


def parse_trip_dt(row):
    for fmt in ["{date} {time}", "{date}T{time}"]:
        try:
            s = fmt.format(date=str(row["shift_date"]).strip(), time=str(row["shift_time"]).strip())
            return pd.to_datetime(s, dayfirst=True)
        except Exception:
            pass
    try:
        return pd.to_datetime(str(row["shift_date"]).strip(), dayfirst=True)
    except Exception:
        return pd.NaT


def nk(s) -> str:
    """Normalise key: strip + upper."""
    return str(s or "").strip().upper()


# ─────────────────────────────────────────────
#  AVAILABLE SHIFT DATES
# ─────────────────────────────────────────────

@router.get("/available_dates")
def get_available_dates(session: Session = Depends(get_session)):
    all_trips = session.exec(select(TripData)).all()
    if not all_trips:
        return []
    dates = set()
    for t in all_trips:
        val = str(t.shift_date or "").strip()
        if val and val.lower() not in ("none", "nan", "nat", ""):
            dates.add(val)

    def norm(d):
        try:
            return pd.to_datetime(d, dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            return d

    return sorted(dates, key=norm, reverse=True)


# ─────────────────────────────────────────────
#  GET ALL ROUTE RULES  (for debugging / management page)
# ─────────────────────────────────────────────

@router.get("/route_rules")
def get_route_rules(session: Session = Depends(get_session)):
    rules = session.exec(select(TollRouteRule)).all()
    return [r.model_dump() for r in rules]


# ─────────────────────────────────────────────
#  SAVE / UPDATE A TOLL ROUTE RULE
#  POST /api/toll/route_rule
#  Upserts on (landmark, office, toll_name) triple
# ─────────────────────────────────────────────

@router.post("/route_rule")
def save_route_rule(payload: TollRouteRuleRequest, session: Session = Depends(get_session)):
    lm  = nk(payload.landmark)
    ofc = nk(payload.office)
    tn  = nk(payload.toll_name)

    existing = session.exec(
        select(TollRouteRule).where(
            TollRouteRule.landmark  == lm,
            TollRouteRule.office    == ofc,
            TollRouteRule.toll_name == tn,
        )
    ).first()

    if existing:
        existing.is_toll_route = payload.is_toll_route
        session.add(existing)
    else:
        rule = TollRouteRule(
            landmark=lm, office=ofc, toll_name=tn,
            is_toll_route=payload.is_toll_route,
            created_at=datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        )
        session.add(rule)

    session.commit()
    return {
        "ok": True,
        "is_toll_route": payload.is_toll_route,
        "landmark": lm, "office": ofc, "toll_name": tn,
    }


# ─────────────────────────────────────────────
#  GET POTENTIAL MATCHES
#  - shift_date  : single date (frontend fires parallel for multi-date)
#  - time_gap_hours : ±window 1h-4h
#  Rules applied:
#    • (landmark, office, toll_name) in blocked_set → toll removed from results
#    • Each remaining toll gets _rule: "toll_route" | null
# ─────────────────────────────────────────────

@router.get("/potential_matches")
def get_potential_tolls(
    shift_date:     str   = Query(...),
    time_gap_hours: float = Query(1.5),
    session: Session = Depends(get_session),
):
    time_gap_hours = max(1.0, min(4.0, time_gap_hours))
    print(f"\n[TollAudit] shift_date={shift_date!r}  gap=±{time_gap_hours}h")

    # ── 1. Load rules ─────────────────────────────────────────────────
    all_rules    = session.exec(select(TollRouteRule)).all()
    blocked_set  = set()   # hide these tolls entirely
    positive_set = set()   # confirmed toll-route badge

    for r in all_rules:
        key = (nk(r.landmark), nk(r.office), nk(r.toll_name))
        if r.is_toll_route:
            positive_set.add(key)
        else:
            blocked_set.add(key)

    print(f"[TollAudit] Rules → confirmed:{len(positive_set)}  blocked:{len(blocked_set)}")

    # ── 2. Trips for requested date ────────────────────────────────────
    all_trips = session.exec(select(TripData)).all()
    trips_for_date = [t for t in all_trips if str(t.shift_date or "").strip() == shift_date.strip()]
    if not trips_for_date:
        return []

    # ── 3. All tolls ───────────────────────────────────────────────────
    all_tolls = session.exec(select(TollData)).all()

    df_trips = pd.DataFrame([t.model_dump() for t in trips_for_date])
    df_tolls = pd.DataFrame([t.model_dump() for t in all_tolls]) if all_tolls else pd.DataFrame()

    # ── 4. Clean vehicle numbers ───────────────────────────────────────
    df_trips["cab_clean"] = (
        df_trips["cab_reg_no"].astype(str)
        .str.strip().str.upper().str.replace(r"\s+", "", regex=True)
    )
    if not df_tolls.empty:
        veh_col = next(
            (c for c in ("veh", "vehicle_number", "vehicle_no") if c in df_tolls.columns), None
        )
        df_tolls["veh_clean"] = (
            df_tolls[veh_col].astype(str).str.strip().str.upper().str.replace(r"\s+", "", regex=True)
            if veh_col else ""
        )

    # ── 5. Parse datetimes ─────────────────────────────────────────────
    df_trips["trip_dt"] = df_trips.apply(parse_trip_dt, axis=1)
    if not df_tolls.empty:
        dt_col = next(
            (c for c in ("travel_date_time", "travel_datetime", "datetime") if c in df_tolls.columns), None
        )
        df_tolls["toll_dt"] = (
            pd.to_datetime(df_tolls[dt_col], errors="coerce", dayfirst=True) if dt_col else pd.NaT
        )

    # ── 6. Narrow toll time window ─────────────────────────────────────
    if not df_tolls.empty and df_tolls["toll_dt"].notna().any():
        try:
            target_dt = pd.to_datetime(shift_date, dayfirst=True)
            df_tolls = df_tolls[
                df_tolls["toll_dt"].isna() |
                (
                    (df_tolls["toll_dt"] >= target_dt - pd.Timedelta(hours=time_gap_hours + 1))
                    & (df_tolls["toll_dt"] <= target_dt + pd.Timedelta(hours=24 + time_gap_hours + 1))
                )
            ].copy()
        except Exception as e:
            print(f"[TollAudit] Window filter error: {e}")

    # ── 7. Linked-toll lookup (trip unique_id → tolls) ─────────────────
    linked_tolls_map: dict = {}
    if not df_tolls.empty and "unique_id" in df_tolls.columns:
        for _, trow in df_tolls.iterrows():
            uid = str(trow.get("unique_id") or "").strip()
            if not is_blank(uid):
                td = clean_dict(trow.to_dict())
                td.pop("toll_dt", None); td.pop("veh_clean", None)
                linked_tolls_map.setdefault(uid, []).append(td)

    # ── 8. Unassigned toll pool ────────────────────────────────────────
    if not df_tolls.empty and "unique_id" in df_tolls.columns:
        df_unassigned = df_tolls[df_tolls["unique_id"].apply(is_blank)].copy()
    elif not df_tolls.empty:
        df_unassigned = df_tolls.copy()
    else:
        df_unassigned = pd.DataFrame()

    # ── 9. Helper: tag toll with rule, or None if blocked ─────────────
    def tag_toll(td: dict, t_lm: str, t_ofc: str) -> Optional[dict]:
        tn  = nk(str(td.get("transaction_description") or ""))
        key = (t_lm, t_ofc, tn)
        if key in blocked_set:
            return None                                 # filtered out
        td["_rule"] = "toll_route" if key in positive_set else None
        return td

    # ── 10. Match loop ─────────────────────────────────────────────────
    matches = []
    for _, trip in df_trips.iterrows():
        trip_dict = clean_dict(trip.to_dict())
        trip_dict.pop("trip_dt", None); trip_dict.pop("cab_clean", None)

        trip_uid   = str(trip.get("unique_id") or "").strip()
        is_updated = not is_blank(str(trip.get("toll_name") or ""))
        t_lm  = nk(str(trip.get("landmark") or ""))
        t_ofc = nk(str(trip.get("office")   or ""))

        if is_updated:
            raw_list = linked_tolls_map.get(trip_uid, [])
            if not raw_list:
                continue
            toll_list = [r for r in (tag_toll(dict(td), t_lm, t_ofc) for td in raw_list) if r]
            if not toll_list:
                continue
            matches.append({"trip": trip_dict, "tolls": toll_list})
            continue

        # Pending — match unassigned tolls in time window
        if df_unassigned.empty or pd.isna(trip["trip_dt"]) or is_blank(trip["cab_clean"]):
            continue

        veh_tolls  = df_unassigned[df_unassigned["veh_clean"] == trip["cab_clean"]]
        veh_tolls  = veh_tolls[veh_tolls["toll_dt"].notna()]
        if veh_tolls.empty:
            continue

        time_diffs  = (veh_tolls["toll_dt"] - trip["trip_dt"]).dt.total_seconds() / 3600.0
        valid_tolls = veh_tolls[(time_diffs >= -time_gap_hours) & (time_diffs <= time_gap_hours)]
        if valid_tolls.empty:
            continue

        toll_list = []
        for t in valid_tolls.to_dict(orient="records"):
            td = clean_dict(t)
            td.pop("toll_dt", None); td.pop("veh_clean", None)
            tagged = tag_toll(td, t_lm, t_ofc)
            if tagged:
                toll_list.append(tagged)

        if not toll_list:
            continue

        matches.append({"trip": trip_dict, "tolls": toll_list})

    print(f"[TollAudit] Matches returned: {len(matches)}\n")
    return matches


# ─────────────────────────────────────────────
#  MARK / LINK TOLLS TO TRIP
# ─────────────────────────────────────────────

@router.post("/mark")
def mark_toll_trips(payload: MarkTollRequest, session: Session = Depends(get_session)):
    trip = session.exec(
        select(TripData).where(TripData.unique_id == payload.trip_unique_id)
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip not found: {payload.trip_unique_id}")

    total_amount = 0.0
    toll_names   = []

    for toll_id_str in payload.selected_toll_ids:
        toll = None
        try:
            toll = session.exec(select(TollData).where(TollData.id == int(toll_id_str))).first()
        except (ValueError, TypeError):
            pass
        if toll is None:
            toll = session.exec(select(TollData).where(TollData.id == toll_id_str)).first()

        if toll:
            toll.unique_id   = trip.unique_id
            total_amount    += float(toll.amount or 0)
            toll_names.append(str(toll.transaction_description or "Unknown Toll"))
            session.add(toll)
        else:
            print(f"[TollAudit] WARNING: Toll id={toll_id_str} not found.")

    trip.unique_toll_id = ",".join(payload.selected_toll_ids)
    trip.toll_amount    = total_amount
    trip.toll_name      = " | ".join(toll_names)

    session.add(trip)
    session.commit()

    return {
        "message": "Tolls linked!",
        "linked_unique_id": trip.unique_id,
        "total_amount": total_amount,
    }