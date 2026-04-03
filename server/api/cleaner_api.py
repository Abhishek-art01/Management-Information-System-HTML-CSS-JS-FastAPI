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
from cleaner.mis_data_cleaner import process_client_data, process_raw_data,process_ba_row_data
from cleaner.fastag_data_cleaner import process_fastag_data
from cleaner.cleaner_helper import create_styled_excel
from cleaner.cleaner_helper import bulk_save_unique, sync_addresses_to_t3
from cleaner.operation_data_cleaner import process_operation_app_data,process_operation_manual_pickup_data,process_operation_manual_drop_data

# 1. Setup paths relative to THIS file
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CLIENT_DIR = BASE_DIR / "client"
# Define the generated folder path here
GENERATED_DIR = CLIENT_DIR / "DataCleaner" / "generated"

templates = Jinja2Templates(directory=str(CLIENT_DIR / "DataCleaner"))
router = APIRouter()


# ==========================================
# 🚀 DATA CLEANER API 
# ==========================================
@router.get("/cleaner")
async def cleaner_page(request: Request):
    if not request.session.get("user"): return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
    "Datacleaner.html", 
    {"request": request, "user": request.session.get("user")}
)


@router.post("/clean-data")
async def clean_data(
    files: List[UploadFile] = File(...),
    cleanerType: str = Form(...),
    session: Session = Depends(get_session)
):
    try:
        print(f"🚀 Processing {len(files)} files with mode: {cleanerType}")
        df_result = None
        excel_output = None
        filename = "output.xlsx"
        rows_saved = 0
        new_addresses = 0


        # ==========================================
        # A. CLIENT DATA
        # ==========================================
        if cleanerType == "client":
            content = await files[0].read()
            df_result, excel_output, filename = process_client_data(content)
            
            # # 1. Database Logic
            # rows_saved = bulk_save_unique(session, ClientData, df_result)
            # if df_result is not None:
            #     new_addresses = sync_addresses_to_t3(session, df_result)
            
            # # 2. Sync Unique IDs (Custom Logic)
            # if df_result is not None and not df_result.empty and "unique_id" in df_result.columns:
            #     incoming_ids = df_result["unique_id"].dropna().unique().tolist()
            #     existing_ids = set(session.exec(select(ClientData.unique_id).where(col(ClientData.unique_id).in_(incoming_ids))).all())
            #     new_rows = df_result[~df_result["unique_id"].isin(existing_ids)]
            #     if not new_rows.empty:
            #         records = [ClientData(**row.to_dict()) for _, row in new_rows.iterrows()]
            #         session.add_all(records)
            #         session.commit()

            # 3. Save & Return (FIXED: Added this block)
            if excel_output is None:
                return Response("Error processing Client data", status_code=400)
            
            generated_dir = GENERATED_DIR
            os.makedirs(generated_dir, exist_ok=True)
            save_path = generated_dir / filename
            with open(save_path, "wb") as f:
                f.write(excel_output.read())

            return {
                "status": "success", 
                "file_url": filename, 
                "rows_processed": len(df_result) if df_result is not None else 0, 
                "db_rows_added": rows_saved, 
                "new_addresses_added": new_addresses
            }

        # ==========================================
        # B. RAW DATA
        # ==========================================
        elif cleanerType == "raw":
            file_data = []
            for f in files:
                content = await f.read()
                file_data.append((f.filename, content))
            
            df_result, excel_output, filename = process_raw_data(file_data)
            
            # 1. Database Logic
            rows_saved = bulk_save_unique(session, RawTripData, df_result)
            if df_result is not None:
                new_addresses = sync_addresses_to_t3(session, df_result)

            # 2. Save & Return (Corrected for BytesIO pointer)
            if excel_output is None:
                return Response("Error processing Raw data", status_code=400)
            
            generated_dir = GENERATED_DIR
            generated_dir.mkdir(parents=True, exist_ok=True)
            
            save_path = generated_dir / filename
            
            # Reset pointer and write buffer
            excel_output.seek(0) 
            with open(save_path, "wb") as f:
                f.write(excel_output.getbuffer()) # ✅ Best practice for BytesIO

            return {
                "status": "success", 
                "file_url": filename, 
                "rows_processed": len(df_result) if df_result is not None else 0, 
                "db_rows_added": rows_saved, 
                "new_addresses_added": new_addresses
            }
        # --- C. APP OPERATION ---            

        elif cleanerType == "operation_app":
            file_data = []
            for f in files:
                content = await f.read()
                file_data.append((f.filename, content))
            df_result, excel_output, filename = process_operation_app_data(file_data)

            if excel_output is None:
                return Response("Error processing data", status_code=400)

            generated_dir = GENERATED_DIR
            os.makedirs(generated_dir, exist_ok=True)
            save_path = generated_dir / filename
            with open(save_path, "wb") as f:
                f.write(excel_output.read())

            row_count = len(df_result) if df_result is not None else "Formatting Only"
            return {
                "status": "success",
                "file_url": filename,
                "rows_processed": row_count,
                "db_rows_added": rows_saved
            }

        #--- D. Operation Manual ---
        elif cleanerType == "operation_manual_pickup":
            file_data = []
            for f in files:
                content = await f.read()
                file_data.append((f.filename, content))
            df_result, excel_output, filename = process_operation_manual_pickup_data(file_data)

            if excel_output is None:
                return Response("Error processing data", status_code=400)

            generated_dir = GENERATED_DIR
            os.makedirs(generated_dir, exist_ok=True)
            save_path = generated_dir / filename
            with open(save_path, "wb") as f:
                f.write(excel_output.read())

            row_count = len(df_result) if df_result is not None else "Formatting Only"
            return {
                "status": "success",
                "file_url": filename,
                "rows_processed": row_count,
                "db_rows_added": rows_saved
            }
        #--- D. Operation Manual Drop ---
        elif cleanerType == "operation_manual_drop":
            file_data = []
            for f in files:
                content = await f.read()
                file_data.append((f.filename, content))
            df_result, excel_output, filename = process_operation_manual_drop_data(file_data)

            if excel_output is None:
                return Response("Error processing data", status_code=400)

            generated_dir = GENERATED_DIR
            os.makedirs(generated_dir, exist_ok=True)
            save_path = generated_dir / filename
            with open(save_path, "wb") as f:
                f.write(excel_output.read())

            row_count = len(df_result) if df_result is not None else "Formatting Only"
            return {
                "status": "success",
                "file_url": filename,
                "rows_processed": row_count,
                "db_rows_added": rows_saved
            }

        # --- D. BA ROW DATA (CSV) ---
        elif cleanerType == "ba_row":
            content = await files[0].read()
            df_result, excel_output, filename = process_ba_row_data(content)
            
            # ... (Existing Database Logic) ...

            # ✅ ADD THIS BLOCK TO SAVE THE FILE AND RETURN RESPONSE
            if excel_output is None:
                return Response("Error processing BA data", status_code=400)

            # 1. Save the generated file to disk so the frontend can download it
            generated_dir = GENERATED_DIR
            os.makedirs(generated_dir, exist_ok=True)
            save_path = generated_dir / filename
            
            with open(save_path, "wb") as f:
                f.write(excel_output.read())

            # 2. Return the JSON response the frontend is waiting for
            row_count = len(df_result) if df_result is not None else 0
            return {
                "status": "success",
                "file_url": filename,
                "rows_processed": row_count,
                "db_rows_added": rows_saved
            }

        # --- E. FASTAG DATA (PDF) ---
        elif cleanerType == "fastag":
            # 1. Collect files as (filename, content) tuples
            file_data = []
            for f in files:
                content = await f.read()
                file_data.append((f.filename, content))  # <--- Pass filename here!
            
            # 2. Pass to function
            df_result, excel_output, filename = process_fastag_data(file_data)

            # 3. Handle Errors
            if excel_output is None:
                return Response("Error processing Fastag PDF", status_code=400)

            # 4. Save to Disk
            generated_dir = GENERATED_DIR
            os.makedirs(generated_dir, exist_ok=True)
            save_path = generated_dir / filename
            
            with open(save_path, "wb") as f:
                f.write(excel_output.read())

            # 5. Return Response
            row_count = len(df_result) if df_result is not None else 0
            return {
                "status": "success",
                "file_url": filename,
                "rows_processed": row_count,
                "db_rows_added": 0
            }

    except Exception as e:
        print(f"❌ Server Error: {e}")
        return Response(f"Internal Error: {e}", status_code=500)
        