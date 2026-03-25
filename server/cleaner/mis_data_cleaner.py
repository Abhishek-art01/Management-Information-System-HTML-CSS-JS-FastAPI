import pandas as pd
import numpy as np
import pdfplumber
import io
import re
import xlrd
import hashlib
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
import traceback
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from datetime import datetime, timedelta
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
# 1. CLIENT DATA CLEANER (Fully Optimized)
# ==========================================
def process_client_data(file_content):
    """
    Cleans Client Data (CSV/Excel) and returns a formatted Excel file.
    Does NOT save to the database.
    """
    try:
        # 1. Define Mapping (CSV Headers -> DB Headers)
        COLUMN_MAPPING = {
            "Trip ID": "trip_id",
            "Billing period": "shift_date", 
            "Employee ID": "employee_id",
            "Gender": "gender",
            "Employee Name": "employee_name",
            "Shift Time": "shift_time",
            "Pickup Time": "pickup_time",
            "Drop time": "drop_time",
            "Trip direction": "trip_direction",
            "Cab reg no": "cab_reg_no",
            "Vendor": "vendor",
            "Office": "office",
            "Landmark": "landmark",
            "Address": "address",
            "Flight Number": "flight_number",
        }

        # 2. Read File (Try CSV, fallback to Excel)
        # Adding dtype=str prevents pandas from deleting leading zeros on IDs
        try:
            df = pd.read_csv(io.BytesIO(file_content), dtype=str)
            print("🔹 Processed as CSV")
        except:
            try:
                df = pd.read_excel(io.BytesIO(file_content), dtype=str)
                print("🔹 Processed as Excel")
            except Exception as e:
                print(f"❌ Error reading file: {e}")
                return None, None, None

        # 3. Rename to Database Columns
        df = df.rename(columns=COLUMN_MAPPING)

        # 4. Standardize 'office' column names
        office_mapping = {
            "Delhi IGI T3": "Terminal-3",
            "Delhi Airport": "Terminal-3",
            "Delhi IGI T2": "Terminal-2"
        }
        if "office" in df.columns:
            df["office"] = df["office"].replace(office_mapping)
        
        # 5. Add Missing Model Headers Dynamically
        valid_model_columns = list(TripDataFile.model_fields.keys())
        for db_col in valid_model_columns:
            if db_col not in df.columns:
                df[db_col] = "" 

        # 6. Cleaning Logic
        # Clean Cab Reg No
        if "cab_reg_no" in df.columns:
            df["cab_reg_no"] = (
                df["cab_reg_no"]
                .astype(str)
                .str.replace("-", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.upper()
                .replace("NAN", "")
            )

        # Clean Trip Direction
        if "trip_direction" in df.columns:
            df["trip_direction"] = (
                df["trip_direction"]
                .astype(str)
                .str.strip()
                .str.title()
                .replace({"Login": "Pickup", "Logout": "Drop"})
            )

        # 7. Generate Unique ID (Trip ID + Employee ID)
        def generate_unique_id(row):
            t_id = str(row.get('trip_id', '')).strip()
            e_id = str(row.get('employee_id', '')).strip()
            
            if t_id.lower() == 'nan': t_id = ''
            if e_id.lower() == 'nan': e_id = ''

            return f"{t_id}{e_id}"

        df["unique_id"] = df.apply(generate_unique_id, axis=1)
        df["data_source"] = "CLIENT_DATA"
        df["clubbing_status"] = "Pay"
        df["route_status"] = "Pay"

        # 8. DYNAMICALLY FILTER USING THE MODEL 
        # (This automatically drops all those 40+ extra columns)
        columns_to_keep = [col for col in valid_model_columns if col in df.columns]
        df = df[columns_to_keep]
        
        # 9. Final safety sweep (Removes stray NaNs)
        df = df.fillna("").astype(str)

        print(f"✅ Client Cleaning Complete. Returning Excel with {len(df)} rows.")
        return create_styled_excel(df, "Client_Cleaned")

    except Exception as e:
        print(f"❌ Client Cleaner Error: {e}")
        traceback.print_exc()
        return None, None, None
# ==========================================
# 2. RAW DATA CLEANER (Fully Updated)
# ==========================================
def _clean_single_raw_df(df):

    try:

        # Standardize NaN values

        df = df.replace({np.nan: None, "nan": None})

       

        # Trip ID Logic

        df["Trip_ID"] = np.where(df.iloc[:, 10].astype(str).str.startswith("T"), df.iloc[:, 10], np.nan)

        df["Trip_ID"] = df["Trip_ID"].ffill()



        # Identify Row Types

        is_header = df.iloc[:, 1].astype(str).str.contains("UNITED FACILITIES", na=False)

        is_passenger = df.iloc[:, 0].astype(str).str.match(r"^[0-9]+$")



        # Extraction Maps

        h_map = {0: 'TRIP_DATE', 1: 'AGENCY_NAME', 2: 'D_LOGIN', 3: 'VEHICLE_NO', 4: 'DRIVER_NAME', 6: 'DRIVER_MOBILE', 7: 'MARSHALL', 8: 'DISTANCE', 9: 'EMP_COUNT', 10: 'TRIP_COUNT'}

        p_map = {0: 'PAX_NO', 1: 'REPORTING_TIME', 2: 'EMPLOYEE_ID', 3: 'EMPLOYEE_NAME', 4: 'GENDER', 5: 'EMP_CATEGORY', 6: 'FLIGHT_NO.', 7: 'ADDRESS', 8: 'REPORTING_LOCATION', 9: 'LANDMARK', 10: 'PASSENGER_MOBILE'}



        df_h = df[is_header].rename(columns=h_map)

        df_p = df[is_passenger].rename(columns=p_map)

       

        if df_h.empty or df_p.empty:

            return pd.DataFrame()



        cols_h = [c for c in h_map.values() if c in df_h.columns] + ['Trip_ID']

        cols_p = [c for c in p_map.values() if c in df_p.columns] + ['Trip_ID']

       

        merged = pd.merge(df_p[cols_p], df_h[cols_h], on='Trip_ID', how='left')



        # Cleaning Logic

        if 'Trip_ID' in merged.columns:

            merged['TRIP_ID'] = merged['Trip_ID'].astype(str).str.replace('T', '', regex=False)

            merged = merged.drop(columns=['Trip_ID'])



        if 'AGENCY_NAME' in merged.columns:

            merged['AGENCY_NAME'] = merged['AGENCY_NAME'].apply(lambda x: "UNITED FACILITIES" if "UNITED FACILITIES" in str(x).upper() else x)



        if 'VEHICLE_NO' in merged.columns:

            merged['VEHICLE_NO'] = merged['VEHICLE_NO'].astype(str).str.replace('-', '', regex=False)



        if 'D_LOGIN' in merged.columns:

            login = merged['D_LOGIN'].astype(str).str.strip().str.split(' ', n=1, expand=True)

            if len(login.columns) > 0: merged['DIRECTION'] = login[0].str.upper().replace({'LOGIN': 'PICKUP', 'LOGOUT': 'DROP'})

            if len(login.columns) > 1: merged['SHIFT_TIME'] = login[1]



        # Explicit Removal

        cols_to_remove = ['PAX_NO', 'D_LOGIN', 'MARSHALL', 'DISTANCE', 'EMP_COUNT', 'TRIP_COUNT']

        merged = merged.drop(columns=cols_to_remove, errors='ignore')



        # Clean string columns

        for col in merged.select_dtypes(include=['object']):

            merged[col] = merged[col].astype(str).str.upper().str.strip()



        return merged

    except Exception as e:

        print(f"Error in _clean_single_raw_df: {e}")

        return pd.DataFrame()

def process_raw_data(file_list_bytes):
    all_dfs = []
    
    # 1. Process files
    for filename, content in file_list_bytes:
        try:
            print(f"Processing file: {filename}")
            df_raw = pd.read_excel(io.BytesIO(content), header=None, dtype=str).dropna(how="all").reset_index(drop=True)
            cleaned = _clean_single_raw_df(df_raw)
            if not cleaned.empty: 
                all_dfs.append(cleaned)
        except Exception as e:
            print(f"FAILED processing file {filename}: {e}")
            continue

    if not all_dfs: 
        return None, None, None
        
    final_df = pd.concat(all_dfs, ignore_index=True)

    # 2. Map and Format
    DB_MAP = {
        'TRIP_DATE': 'shift_date', 'TRIP_ID': 'trip_id', 'AGENCY_NAME': 'vendor', 
        'FLIGHT_NO.': 'flight_number', 'EMPLOYEE_ID': 'employee_id', 'EMPLOYEE_NAME': 'employee_name', 
        'GENDER': 'gender', 'EMP_CATEGORY': 'emp_category', 'ADDRESS': 'address', 
        'PASSENGER_MOBILE': 'passenger_mobile', 'LANDMARK': 'landmark', 'VEHICLE_NO': 'cab_reg_no',
        'DRIVER_NAME': 'driver_name', 'DRIVER_MOBILE': 'driver_mobile', 'DIRECTION': 'trip_direction',
        'SHIFT_TIME': 'shift_time', 'REPORTING_TIME': 'pickup_time', 'REPORTING_LOCATION': 'office'    
    }

    final_db = final_df.rename(columns=DB_MAP).fillna("")
    
    if 'shift_date' in final_db.columns:
        final_db['shift_date'] = pd.to_datetime(final_db['shift_date'], errors='coerce').dt.strftime('%d-%m-%Y')
        final_db['trip_date'] = final_db['shift_date']
    
    if 'shift_time' in final_db.columns:
        final_db['shift_time'] = pd.to_datetime(final_db['shift_time'], errors='coerce', format='mixed').dt.strftime('%H:%M')

    # 3. Add Missing Mandatory Headers
    mandatory_cols = get_mandatory_columns() 
    target_cols = list(mandatory_cols.values()) if isinstance(mandatory_cols, dict) else list(mandatory_cols)

    for db_col in target_cols:
        if db_col not in final_db.columns:
            final_db[db_col] = ""

   # 2. Generate Unique ID (Trip ID + Employee ID)
    def generate_unique_id(row):
        t_id = str(row.get('trip_id', '')).strip()
        e_id = str(row.get('employee_id', '')).strip()
        
        # Handle pandas 'nan' artifacts
        if t_id.lower() == 'nan': t_id = ''
        if e_id.lower() == 'nan': e_id = ''

        # Directly combine them: 1234 + 3456 = "12343456"
        return f"{t_id}{e_id}"

    final_db["unique_id"] = final_db.apply(generate_unique_id, axis=1)
    final_db["data_source"] = "RAW_DATA"
    # Standardize 'office' column names
    office_mapping = {
        "DELHI IGI T3": "Terminal-3",
        "DELHI AIRPORT": "Terminal-3",
        "DELHI IGI T2": "Terminal-2"
    }
    
    if "office" in final_db.columns:
        final_db["office"] = final_db["office"].replace(office_mapping)
    
    # 5. Safely Filter Columns
    valid_model_columns = list(TripDataFile.model_fields.keys())
    
    # Keep only the columns that exist in BOTH the dataframe and the model
    columns_to_keep = [col for col in valid_model_columns if col in final_db.columns]
    final_db = final_db[columns_to_keep]

    # 6. Final safety sweep (removes any stray NaNs that bypass Pandas filters)
    final_db = final_db.fillna("").astype(str)

    print(f"✅ Raw Cleaning Complete. Returning Excel with {len(final_db)} rows.")
    
    # 🔥 FIX: Use create_styled_excel to return the proper tuple and avoid the Worksheet crash
    return create_styled_excel(final_db, "Raw_Cleaned")


# ==========================================
# 3. BA ROW DATA CLEANER (Aligned to Actual CSV)
# ==========================================


def process_ba_row_data(file_content):
    try:
        print("🔹 Starting BA Row Data Processing...")
        
        # 1. READ CSV (Force everything to string to prevent auto-parsing dates)
        df = pd.read_csv(io.BytesIO(file_content), low_memory=False, dtype=str)
        df.columns = df.columns.str.strip()

        # 🔥 FIX 1: Drop Escort Team Rows immediately
        if "Team" in df.columns:
            df = df[df["Team"].astype(str).str.upper() != "ESCORT"]

        # 2. ACTUAL CSV MAPPING
        MAPPING = {
            "EmpId": "employee_id",
            "Trip ID": "trip_id",
            "Name": "employee_name",
            "Gender": "gender",
            "Crew Type": "emp_category",
            "Selected Destination": "address",
            "Billing Zone": "landmark",
            "Flight Number": "flight_number",
            "Flight Type": "flight_type",
            "Trip Office": "office",
            "Vendor ID": "vendor",
            "Shift Type/Time": "shift_time",
            "Trip Sheet Comment": "mis_remark",
            "Not Boarding Reason": "ba_remark"
        }
        df = df.rename(columns=MAPPING)

        # 🔥 FIX 2: Office Standardization
        office_mapping = {
            "Delhi IGI T3": "Terminal-3",
            "Delhi Airport": "Terminal-3",
            "Delhi IGI T2": "Terminal-2"
        }
        if "office" in df.columns:
            # We use .strip() to ensure no hidden spaces prevent a match
            df["office"] = df["office"].str.strip().replace(office_mapping)

        # ---------------------------------------------------------
        # 🔥 THE RECONSTRUCTION FIX: YYYY-MM-DD to DD-MM-YYYY
        # ---------------------------------------------------------
        if "Date" in df.columns:
            def manual_date_reformat(date_val):
                if pd.isna(date_val) or str(date_val).strip() == "":
                    return ""
                
                # Ensure it's a string and clean it
                ds = str(date_val).strip().replace("/", "-")
                
                try:
                    # Split the string (Expects YYYY-MM-DD)
                    parts = ds.split("-")
                    
                    if len(parts) == 3:
                        # If the first part is 4 digits, it's YYYY-MM-DD
                        if len(parts[0]) == 4:
                            year = parts[0]
                            month = parts[1].zfill(2)
                            day = parts[2].zfill(2)
                        # If the last part is 4 digits, it's DD-MM-YYYY
                        else:
                            day = parts[0].zfill(2)
                            month = parts[1].zfill(2)
                            year = parts[2]
                            
                        return f"{day}-{month}-{year}"
                except:
                    pass
                return ds

            df["shift_date"] = df["Date"].apply(manual_date_reformat)
            df["trip_date"] = df["shift_date"]

        # 3. Direction Logic
        if "Direction" in df.columns:
            df["trip_direction"] = df["Direction"].str.upper().map({
                "LOGIN": "PICKUP", "LOGOUT": "DROP"
            }).fillna("")
        else:
            df["trip_direction"] = ""

        # 4. Registration Cleaning
        if "Registration" in df.columns:
            df["cab_reg_no"] = (
                df["Registration"].astype(str)
                .str.replace("-", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.upper()
                .replace("NAN", "")
            )

        # 5. Generate Unique ID
        def generate_unique_id(row):
            t_id = str(row.get('trip_id', '')).strip()
            e_id = str(row.get('employee_id', '')).strip() 
            
            if t_id.endswith(".0"): t_id = t_id[:-2]
            if e_id.endswith(".0"): e_id = e_id[:-2]
            
            if t_id.lower() == 'nan': t_id = ''
            if e_id.lower() == 'nan': e_id = ''
            
            return f"{t_id}{e_id}"

        df["unique_id"] = df.apply(generate_unique_id, axis=1)
        df["data_source"] = "BA_ROW_DATA"

        # 6. Final Model Alignment
        valid_model_columns = list(TripDataFile.model_fields.keys())
        for db_col in valid_model_columns:
            if db_col not in df.columns:
                df[db_col] = ""

        columns_to_keep = [col for col in valid_model_columns if col in df.columns]
        df_final = df[columns_to_keep].fillna("").astype(str)

        print(f"✅ BA Row Cleaning Complete. Returning {len(df_final)} rows.")
        return create_styled_excel(df_final, "BA_Row_Data_Cleaned")

    except Exception as e:
        traceback.print_exc()
        print(f"❌ BA Row Data Cleaner Error: {e}")
        return None, None, None