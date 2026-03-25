import os
import io
import pandas as pd
from pathlib import Path
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select, Session, text
from fastapi import APIRouter, Depends, Request, File, UploadFile, Response, Form

# Internal Imports
from database import get_session
from models import ClientData, RawTripData, OperationData, TripData, TollData
from cleaner.cleaner_helper import create_styled_excel

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CLIENT_DIR = BASE_DIR / "client"
GENERATED_DIR = BASE_DIR / "client" / "DataCleaner" / "generated"

templates = Jinja2Templates(directory=str(CLIENT_DIR / "OperationManager"))
router = APIRouter()

# --- 1. OPERATION MANAGER PAGE ---
@router.get("/operation-manager")
async def operation_manager_page(request: Request):
    if not request.session.get("user"): 
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("operation_manager.html", {"request": request})

# --- 2. DOWNLOAD STATIC FILE ENDPOINT ---
@router.get("/download/{filename}")
async def download_file(filename: str, request: Request):
    if not request.session.get("user"):
        return Response("Unauthorized", status_code=401)
    file_path = GENERATED_DIR / filename
    if not file_path.exists():
        return Response("File not found", status_code=404)
    return FileResponse(path=file_path, filename=filename)

# --- 3. DYNAMIC DATABASE DOWNLOAD ENDPOINT ---
@router.get("/api/{table_type}/download")
def download_specific_table(table_type: str, session: Session = Depends(get_session)):
    # Map the URL parameter to the correct Database Model
    model_map = {
        "operation":  OperationData,
        "client":     ClientData,
        "raw":        RawTripData,
        "trip_data":  TripData,   # keep old key
        "tripdata":   TripData,   # ← ADD THIS — actual SQL table name
        "toll":       TollData,
    }
    if table_type not in model_map:
        return {"status": "error", "message": "Invalid table type selected."}
    
    # Query the database
    model_class = model_map[table_type]
    statement = select(model_class)
    results = session.exec(statement).all()
    
    if not results:
        return {"status": "error", "message": f"No data found in {table_type} table."}
    
    # Convert to Pandas DataFrame
    data = [row.model_dump() for row in results]
    df = pd.DataFrame(data)
    
    # 🔥 USE YOUR HELPER FUNCTION!
    # It returns the dataframe, the BytesIO output, and the filename
    filename_prefix = f"{table_type.capitalize()}_Export"
    _, output, generated_filename = create_styled_excel(df, filename_prefix=filename_prefix)
    
    headers = {'Content-Disposition': f'attachment; filename="{generated_filename}"'}
    return StreamingResponse(
        output, 
        headers=headers, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# --- 4. UPLOAD OPERATION DATA ENDPOINT ---
@router.post("/api/operation/upload")
async def upload_operation_data(file: UploadFile = File(...), session: Session = Depends(get_session)):
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        
        # Clean data for SQL insertion
        df = df.where(pd.notnull(df), None)
        records = df.to_dict(orient="records")
        
        if not records:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Uploaded file is empty."})

        # Clear old data and insert new data
        session.exec(text("DELETE FROM tripdata"))
        db_records = [TripData(**row) for row in records]
        
        session.add_all(db_records)
        session.commit()

        return JSONResponse(content={"status": "success", "message": f"Successfully uploaded {len(db_records)} new rows."})
    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    
@router.get("/api/tables")
async def get_available_tables(session: Session = Depends(get_session)):
    try:
        from sqlalchemy import inspect
        
        # Get engine from the active session
        inspector = inspect(session.bind)
        all_tables = inspector.get_table_names()
        
        # Exclude user-related tables
        excluded = {"user", "users", "user_roles", "user_sessions", "alembic_version"}
        filtered = [t for t in all_tables if t.lower() not in excluded]
        
        return {"tables": filtered}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    
@router.post("/api/upload")
async def upload_data(
    file: UploadFile = File(...),
    table: str = Form(...),
    mode: str = Form(...),          # "append" or "erase"
    session: Session = Depends(get_session)
):
    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
        df = df.where(pd.notnull(df), None)
        records = df.to_dict(orient="records")

        if not records:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Uploaded file is empty."})

        if mode == "erase":
            # Delete all existing rows in the target table
            session.exec(text(f"DELETE FROM {table}"))
            session.commit()

        if mode == "append":
            # Fetch existing rows as a set of tuples for deduplication
            existing_rows = session.exec(text(f"SELECT * FROM {table}")).all()
            existing_set  = set(existing_rows)
            records = [r for r in records if tuple(r.values()) not in existing_set]

            if not records:
                return JSONResponse(content={"status": "success", "message": "No new unique rows to insert."})

        # Raw insert into any table without needing a model
        session.exec(text(f"INSERT INTO {table} ({', '.join(records[0].keys())}) VALUES ({', '.join([':' + k for k in records[0].keys()])})"), records)
        session.commit()

        return JSONResponse(content={"status": "success", "message": f"Successfully inserted {len(records)} rows into '{table}'."})

    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})