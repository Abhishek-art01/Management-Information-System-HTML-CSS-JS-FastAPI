import pandas as pd
import numpy as np
import pdfplumber
import io
import re
import xlrd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
import traceback
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from datetime import datetime, timedelta
import os
import pandas as pd
from datetime import datetime
from io import BytesIO
from models import TripDataFile
from .cleaner_helper import (
    get_mandatory_columns, 
    get_xls_style_data, 
    format_excel_sheet,
    clean_cell_value,
    create_styled_excel,
    sync_addresses_to_t3
)



# ==========================================
# 1. APP OPERATION DATA CLEANER (Fully Optimized)
# ==========================================
def process_operation_app_data(file_list_bytes):
    # 1. Configuration
    COLUMN_TO_RENAME = {
        'DATE': 'shift_date', 'TRIP ID': 'trip_id', 'FLT NO.': 'flight_number', 
        'SAP ID': 'employee_id', 'EMP NAME': 'employee_name', 'EMPLOYEE ADDRESS': 'address', 
        'PICKUP LOCATION': 'landmark', 'DROP LOCATION': 'office', 'CAB NO': 'cab_last_digit',
        'AIRPORT DROP TIME': 'shift_time', 'REMARKS': 'mis_remark'
    }
    SKIP_HEADERS = ['CONTACT NO', 'GUARD ROUTE', 'PICKUP TIME']

    data_rows = []

    # 2. Extraction Loop (Extract Data + Evaluate Styles)
    for filename, content in file_list_bytes:
        if not filename.lower().endswith('.xls'): continue
        print(f"\n--- Processing File: {filename} ---")

        try:
            rb = xlrd.open_workbook(file_contents=content, formatting_info=True)
            rs = rb.sheet_by_index(0)
            source_headers = [str(rs.cell_value(0, c)).strip().upper() for c in range(rs.ncols)]
            
            # Identify specific columns for the Color Logic
            idx_trip = next((i for i, h in enumerate(source_headers) if 'TRIP ID' in h), None)
            idx_sap = next((i for i, h in enumerate(source_headers) if 'SAP ID' in h), None)
            idx_addr = next((i for i, h in enumerate(source_headers) if 'EMPLOYEE ADDRESS' in h), None)
            check_indices = [idx for idx in [idx_trip, idx_sap, idx_addr] if idx is not None]

            # Parse Rows
            for r_idx in range(1, rs.nrows):
                row_vals = [str(rs.cell_value(r_idx, c)).strip() for c in range(rs.ncols)]
                if sum(1 for v in row_vals if v != "") <= 3: 
                    continue # Skip mostly empty rows

                raw_row_dict = {}
                red_count = 0
                yellow_count = 0

                # Extract cells and check styles
                for c_idx in range(rs.ncols):
                    raw_header = source_headers[c_idx]
                    if any(skip in raw_header for skip in SKIP_HEADERS): continue
                    
                    val = rs.cell_value(r_idx, c_idx)
                    if isinstance(val, float) and val.is_integer():
                        val = int(val)
                    raw_row_dict[raw_header] = val

                    # Check colors only on the 3 critical columns
                    if c_idx in check_indices:
                        bg, fg, _ = get_xls_style_data(rb, rs.cell_xf_index(r_idx, c_idx), r_idx, c_idx)
                        if fg == "FF0000": red_count += 1
                        if bg == "FFFF00": yellow_count += 1

                # Apply Business Logic
                if red_count == 3:
                    raw_row_dict['REMARKS'] = "Cancel"
                elif yellow_count == 3:
                    raw_row_dict['REMARKS'] = "Alt Veh"

                # Keep row if it has identity
                if raw_row_dict.get('SAP ID') or raw_row_dict.get('EMP NAME'):
                    data_rows.append(raw_row_dict)
                    
            rb.release_resources()
            
        except Exception as e:
            print(f"[BREAKING ERROR] File {filename}: {e}")
            traceback.print_exc()

    if not data_rows:
        return None, None, None

    # 3. Pandas Processing
    df = pd.DataFrame(data_rows)
    
    # Rename matching columns to DB format
    rename_map = {k: v for k, v in COLUMN_TO_RENAME.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # 4. Safe Date & Time Conversion Helpers
    def convert_date(d):
        if pd.isna(d) or str(d).strip() == "": return ""
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(d))).strftime('%d-%m-%Y')
        except: return str(d).strip()

    def convert_time(t):
        if pd.isna(t) or str(t).strip() == "": return ""
        try:
            seconds = int(round((float(t) % 1) * 86400))
            return (datetime.min + timedelta(seconds=seconds)).strftime('%H:%M')
        except: return str(t).strip()

    # Apply conversions
    if 'shift_date' in df.columns: df['shift_date'] = df['shift_date'].apply(convert_date)
    if 'shift_time' in df.columns: df['shift_time'] = df['shift_time'].apply(convert_time)
    office_mapping = {
    "Delhi IGI T3": "Terminal-3",
    "Delhi Airport": "Terminal-3",
    "Delhi IGI T2": "Terminal-2",
    }

    if "office" in df.columns:
        df["office"] = df["office"].replace(office_mapping)

    # 6. Add Missing Model Headers Dynamically
    valid_model_columns = list(TripDataFile.model_fields.keys())
    for db_col in valid_model_columns:
        if db_col not in df.columns:
            df[db_col] = "" 

    # 7. Generate Unique ID
    def generate_unique_id(row):
        t_id = str(row.get('trip_id', '')).strip()
        e_id = str(row.get('employee_id', '')).strip()
        if t_id.lower() == 'nan': t_id = ''
        if e_id.lower() == 'nan': e_id = ''
        return f"{t_id}{e_id}"

    df["unique_id"] = df.apply(generate_unique_id, axis=1)
    df["data_source"] = "OPERATION_APP"
    df["trip_direction"] = "PICKUP"
    df["vendor"] = "UNITED FACILITIES"

    # 8. Text Formatting (All uppercase)
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    df[text_cols] = df[text_cols].apply(lambda col: col.astype(str).str.upper().str.strip())
    
    # 9. Dynamically filter columns based on the model
    columns_to_keep = [col for col in valid_model_columns if col in df.columns]
    df = df[columns_to_keep].fillna("").astype(str)

    print(f"✅ App Operation Cleaning Complete. Processed {len(df)} rows.")
    
    # 10. Generate output file
    return create_styled_excel(df, "Operation_App_Cleaned")
# ==========================================
# 2. MANUAL OPERATION DATA CLEANER (Optimized)
# ==========================================
def process_operation_manual_pickup_data(file_data):
    """
    Cleans Manual Operation Data and returns a formatted Excel file.
    file_data = [(filename, bytes_content)]
    """
    final_dfs = []

    for file_name, content in file_data:
        try:
            print(f"\n--- Processing Manual File: {file_name} ---")
            
            # 1. Read Excel (NO HEADER)
            df = pd.read_excel(io.BytesIO(content), header=None)
            df = df.dropna(how="all")

            # 2. Rename Columns by POSITION
            new_columns = [
                "route_no",          # 0
                "flight_number",    # 1
                "employee_id",      # 2
                "employee_name",    # 3
                "address",          # 4
                "contact_no",       # 5
                "cab_last_digit",   # 6
                "pickup_time",      # 7
                "shift_time",   # 8
                "mis_remark"        # 9
            ]

            if len(df.columns) < len(new_columns):
                print(f"⚠️ {file_name}: Column mismatch. Found {len(df.columns)}. Skipping.")
                continue

            df = df.iloc[:, :len(new_columns)]
            df.columns = new_columns

            # 3. Extract Date from Filename
            try:
                # Assumes format like "filename 24-02-2026.xlsx"
                date_str = file_name.split()[-1].replace(".xlsx", "").replace(".xls", "")
                file_date = datetime.strptime(date_str, "%d-%m-%Y").strftime('%d-%m-%Y')
            except Exception:
                file_date = ""

            df["shift_date"] = file_date

            # 4. Reporting Area (Office) Logic
            # Extract office from header rows and forward fill
            df["office"] = (
                df["address"]
                .astype(str)
                .str.extract(r'EMPLOYEE ADDRESS TO\s*"([^"]+)"', expand=False)
                .ffill()
            )

            # 5. Route No & Trip ID Formatting
            # Fix the .0 float issue before forward filling
            df["route_no"] = df["route_no"].apply(lambda x: int(x) if isinstance(x, float) and x.is_integer() else x)
            df["route_no"] = df["route_no"].ffill()
            
            # Keep a clean version of the trip ID for the unique_id generator later
            clean_route_no = df["route_no"].copy() 
            df["route_no"] = "Route No.:- " + df["route_no"].astype(str)

            # 6. Drop Invalid Employee Rows (Done AFTER ffill so data cascades correctly)
            df = df[
                df["employee_id"].notna()
                & df["employee_id"].astype(str).str.strip().ne("")
                & df["employee_id"].astype(str).str.upper().ne("EMP ID")
                & df["employee_id"].astype(str).str.upper().ne("NAN")
            ]
            
            df["trip_direction"] = "PICKUP" 
            df["vendor"] = "UNITED FACILITIES"
            
            # Attach the clean trip ID temporarily for hashing
            df["_clean_route_no"] = clean_route_no
            final_dfs.append(df)
            
        except Exception as e:
            print(f"[BREAKING ERROR] File {file_name}: {e}")
            traceback.print_exc()

    # 7. Merge All Files
    if not final_dfs:
        return None, None, None

    final_df = pd.concat(final_dfs, ignore_index=True)

    # 8. Add Missing Model Headers Dynamically
    valid_model_columns = list(TripDataFile.model_fields.keys())
    for db_col in valid_model_columns:
        if db_col not in final_df.columns:
            final_df[db_col] = ""
            
    
            

    def generate_trip_id(row):
        route_label = str(row.get('route_no', '')).strip().upper()
        shift_date_raw = str(row.get('shift_date', '')).strip()
        dir_id = str(row.get('trip_direction', '')).strip().upper()

        # --- Convert Date String to Excel Serial Number (e.g., 46076) ---
        serial_date = ""
        try:
            if shift_date_raw:
                # Parse the date string
                dt_obj = datetime.strptime(shift_date_raw, '%d-%m-%Y')
                # Excel's base date is December 30, 1899
                excel_base_date = datetime(1899, 12, 30)
                # Calculate the difference in days
                serial_date = str((dt_obj - excel_base_date).days)
        except Exception as e:
            print(f"Date conversion failed for {shift_date_raw}: {e}")
            serial_date = shift_date_raw.replace('-', '') # Fallback to digits

        if route_label.lower() == 'nan': route_label = ''
        
        # --- Combine to match image: 46055PICKUPROUTE NO.:- 7 ---
        return f"{serial_date}{dir_id}{route_label}"

    # Apply the updated function
    final_df["trip_id"] = final_df.apply(generate_trip_id, axis=1)

    # ---------------------------------------------------------
    # 🔥 GENERATE UNIQUE ID (Now uses the new Trip ID)
    # ---------------------------------------------------------
    def generate_unique_id(row):
        # We can now just use the 'trip_id' we generated directly above!
        t_id = str(row.get('trip_id', '')).strip() 
        e_id = str(row.get('employee_id', '')).strip()
        
        # Clean up any leftover .0 from floats
        if t_id.endswith(".0"): t_id = t_id[:-2]
        if e_id.endswith(".0"): e_id = e_id[:-2]
        
        if t_id.lower() == 'nan': t_id = ''
        if e_id.lower() == 'nan': e_id = ''
        
        return f"{t_id}{e_id}"

    final_df["unique_id"] = final_df.apply(generate_unique_id, axis=1)
    final_df["data_source"] = "OPERATION_MANUAL"
    
    # Standardize Office names (Optional, but keeps DB clean)
    office_mapping = {"DELHI IGI T3": "Terminal 3", "DELHI AIRPORT": "Terminal 3", "DELHI IGI T2": "Terminal-2"}
    final_df["office"] = final_df["office"].replace(office_mapping)

    # 10. Dynamically filter columns based on the model
    columns_to_keep = [col for col in valid_model_columns if col in final_df.columns]
    final_df = final_df[columns_to_keep]

    # Final sweep
    final_df = final_df.fillna("").astype(str)

    print(f"✅ Manual Operation Cleaning Complete. Processed {len(final_df)} rows.")

    # 11. Export via your custom styled helper
    return create_styled_excel(final_df, "Operation_Manual_Cleaned")

def process_operation_manual_drop_data(file_data_list):
    """
    Consolidated Manual Drop Sheet Processor.
    Handles multiple files, converts dates to serial numbers, and aligns to DB model.
    """
    try:
        print(f"🔹 Starting Drop Sheet Manual Processing for {len(file_data_list)} files...")
        final_dfs = []

        for filename, file_content in file_data_list:
            print(f"  --- Processing: {filename} ---")
            
            # 1. Read Excel without headers
            df = pd.read_excel(io.BytesIO(file_content), header=None)

            # 2. Cleanup: Remove unwanted rows (TRG TYPE and fully empty rows)
            df = df[df[0].astype(str).str.strip().str.upper() != "TRG TYPE"].reset_index(drop=True)
            df = df.dropna(how="all").reset_index(drop=True)

            # 3. Identify Metadata Rows (Route info lines)
            condition = (df[2].astype(str).str.strip().str.upper() == "VENDOR :- UNITED")

            # 4. Initialize Columns and Extract Metadata
            df["shift_date"] = None
            df["route_no"] = None
            df["vendor"] = None
            df["office"] = None

            df.loc[condition, "shift_date"] = df.loc[condition, 0]
            df.loc[condition, "route_no"] = df.loc[condition, 1]
            df.loc[condition, "vendor"] = "UNITED FACILITIES"
            df.loc[condition, "office"] = df.loc[condition, 3]

            # 5. Forward-fill metadata to employee rows
            cols = ["shift_date", "route_no", "vendor", "office"]
            df[cols] = df[cols].ffill()

            # 6. Drop the metadata rows
            df = df[~condition].reset_index(drop=True)

            # 7. Rename to DB headers
            rename_map = {
                0: "flight_number", 1: "employee_id", 2: "employee_name",
                3: "address", 4: "landmark", 6: "shift_time", 7: "mis_remark"
            }
            df = df.rename(columns=rename_map)
            df = df.drop(columns=[5], errors='ignore')

            df["trip_direction"] = "DROP"
            df["data_source"] = "DROP_SHEET_MANUAL"
            
            final_dfs.append(df)

        if not final_dfs:
            return None, None, None

        # 8. Merge all processed drop sheets
        merged_df = pd.concat(final_dfs, ignore_index=True)
        
        # ---------------------------------------------------------
        # 🔥 SHIFT DATE CLEANING LOGIC (Timestamp to DD-MM-YYYY)
        # ---------------------------------------------------------
        def clean_shift_date(row):
            raw_date = row.get('shift_date')
            
            if pd.isna(raw_date) or str(raw_date).strip() == "":
                return ""
            
            try:
                # 1. Parse the timestamp (handles '2026-02-20 00:00:00')
                dt_obj = pd.to_datetime(raw_date)
                
                # 2. Return strictly in DD-MM-YYYY format
                return dt_obj.strftime('%d-%m-%Y')
            except Exception:
                # Fallback for unexpected string formats
                return str(raw_date).split()[0]

        # Apply to your DataFrame
        merged_df["shift_date"] = merged_df.apply(clean_shift_date, axis=1)

        # ---------------------------------------------------------
        # 🔥 UPDATED ID GENERATION (Handles YYYY-MM-DD Timestamps)
        # ---------------------------------------------------------
        def generate_ids(row):
            route_label = str(row.get('route_no', '')).strip().upper()
            raw_date = str(row.get('shift_date', '')).strip()
            dir_id = str(row.get('trip_direction', '')).strip().upper()
            emp_id = str(row.get('employee_id', '')).strip()

            # Fix Date: Handles '2026-02-20 00:00:00' or '20-02-2026'
            serial_date = ""
            try:
                if raw_date:
                    # pd.to_datetime is much smarter than strptime for mixed formats
                    dt_obj = pd.to_datetime(raw_date, dayfirst=True)
                    # Excel Serial Number conversion
                    excel_base = datetime(1899, 12, 30)
                    serial_date = str((dt_obj - excel_base).days)
            except Exception:
                serial_date = raw_date.replace('-', '').split()[0]

            # Create Trip ID: 46076DROPROUTE 7
            t_id = f"{serial_date}{dir_id}{route_label}"
            
            # Create Unique ID: TripID + EmpID
            if emp_id.endswith(".0"): emp_id = emp_id[:-2]
            u_id = f"{t_id}{emp_id}"

            return pd.Series([t_id, u_id])

        merged_df[["trip_id", "unique_id"]] = merged_df.apply(generate_ids, axis=1)

        # 9. Final Model Alignment
        valid_model_columns = list(TripDataFile.model_fields.keys())
        for db_col in valid_model_columns:
            if db_col not in merged_df.columns:
                merged_df[db_col] = ""

        columns_to_keep = [col for col in valid_model_columns if col in merged_df.columns]
        df_final = merged_df[columns_to_keep].fillna("").astype(str)

        print(f"✅ Drop Sheet Cleaning Complete. Total Rows: {len(df_final)}")
        return create_styled_excel(df_final, "Drop_Sheet_Cleaned")

    except Exception as e:
        traceback.print_exc()
        return None, None, None