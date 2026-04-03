import pandas as pd
import numpy as np
import pdfplumber
import io
import re
import xlrd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
import traceback
from .cleaner_helper import create_styled_excel # Make sure cleaner_helper.py is in the same folder

# ==========================================
# HELPER: CLEANING UTILS
# ==========================================
def clean_multiline_cells(df):
    """
    Cleans string columns and prevents the 'dtype' crash by ensuring column uniqueness.
    """
    # 1. Drop duplicated columns to prevent df[col] from returning a DataFrame
    df = df.loc[:, ~df.columns.duplicated()].copy()
    
    for col in df.columns:
        # 2. Now safe to check dtype
        if df[col].dtype == object:
            df[col] = (
                df[col].astype(str)
                .str.replace(r"[\n\t]", " ", regex=True)
                .str.replace(r"\s+", " ", regex=True)
                .str.strip()
            )
            df[col] = df[col].replace(["nan", "None", ""], np.nan)
    return df

def _clean_columns(columns):
    cleaned = (
        columns
        .astype(str)
        .str.replace(r"\n", " ", regex=True)
        .str.replace(r"\t", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.lower()
        .str.replace(r"[^\w\s]", "", regex=True)
        .str.replace(" ", "_")
    )
    return cleaned

def _clean_cell_value(x):
    if isinstance(x, str):
        x = x.replace("\n", " ").replace("\t", " ")
        x = re.sub(r"\s+", " ", x).strip()
        if x.lower() in ["na", "n/a", "null", "none", ""]:
            return np.nan
        return x
    return x

# ==========================================
# HELPER: BANK SPECIFIC CLEANERS
# ==========================================
# ==========================================
# HELPER: ICICI SPECIFIC CLEANER
# ==========================================
def _process_icici(pdf_obj):
    all_tables = []
    for page in pdf_obj.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_tables.append(pd.DataFrame(table))
    
    if not all_tables: return pd.DataFrame()

    df = pd.concat(all_tables, ignore_index=True)

    if len(df) > 12:
        df = df.drop(index=[0,1,2,3,4,5,6,7,8,9,10,11]).reset_index(drop=True)
    else:
        return pd.DataFrame()

    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)
    df.columns = _clean_columns(df.columns)
    df.columns = df.columns.str.strip()
    
    df = df.rename(columns={"date__time": "date_time"})

    if not df.empty and "date_time" in df.columns:
        try:
            raw_val = str(df.loc[0, "date_time"])
            vehicle_no = raw_val.split(" ")[0]
            df["vehicle_no"] = vehicle_no
            df = df.drop(index=[0]).reset_index(drop=True)
        except:
            df["vehicle_no"] = ""
    else:
        df["vehicle_no"] = ""

    df["plaza_id"] = ""

    replacements = {"drcr": "debit_credit", "rscr": "rupees_credit", "rsdr": "rupees_debit", "rs": "rupees", "amt": "amount", "bal": "balance"}
    for k, v in replacements.items():
        df.columns = df.columns.str.replace(k, v, regex=False)

    df = df.drop(columns=["nan", "amount_rupees_credit"], errors="ignore")

    # 🔥 THE FIX: Smarter Column Mapping
    col_map = {}
    for col in df.columns:
        c = str(col).lower()
        if "description" in c or "plaza" in c:
            col_map[col] = "plaza_name"
        elif "date" in c and "time" in c:
            col_map[col] = "travel_date_time"
        elif "debit" in c or ("amount" in c and "dr" in c):
            col_map[col] = "tag_debit_credit"
        elif "transaction" in c and "id" in c:
            col_map[col] = "unique_transaction_id"
        elif "rrn" in c:
            col_map[col] = "unique_transaction_id"
        elif "activity" in c:
            col_map[col] = "activity"
            
    df = df.rename(columns=col_map)
    df = df.rename(columns={"vehicle_no": "vehicle_number"})

    # Fallback in case ID was named something completely different
    if "unique_transaction_id" not in df.columns:
        for col in df.columns:
            if "id" in str(col) and "plaza" not in str(col) and "lane" not in str(col):
                df = df.rename(columns={col: "unique_transaction_id"})
                break

    subset_cols = ["vehicle_number", "travel_date_time", "unique_transaction_id", "plaza_name", "activity", "tag_debit_credit"]
    existing_subset = [c for c in subset_cols if c in df.columns]
    if existing_subset:
        df = df.dropna(subset=existing_subset)

    final_columns = ["vehicle_number", "travel_date_time", "unique_transaction_id", "plaza_name", "plaza_id", "activity", "tag_debit_credit"]
    for col in final_columns:
        if col not in df.columns:
            df[col] = ""

    df = df[final_columns]

    # Clean multi-line IDs and slashes out of the ICICI ID string
    df["unique_transaction_id"] = df["unique_transaction_id"].astype(str).str.replace(r"[\n\s/]+", "", regex=True)

    if "plaza_name" in df.columns:
        df = df[df["plaza_name"].astype(str).str.contains("transaction description", case=False, na=False) == False]

    df = clean_multiline_cells(df)

    final_title_map = {"vehicle_number": "Vehicle No", "travel_date_time": "Travel Date Time", "unique_transaction_id": "Unique Transaction ID", "plaza_name": "Plaza Name", "plaza_id": "Plaza ID", "activity": "Activity", "tag_debit_credit": "Tag Dr/Cr"}
    df.rename(columns=final_title_map, inplace=True)
    return df

# ==========================================
# HELPER: IDFC SPECIFIC CLEANER
# ==========================================
def _process_idfc(pdf_obj):
    all_tables = []
    for page in pdf_obj.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_tables.append(pd.DataFrame(table))
    
    if not all_tables:
        print("⚠️ IDFC: No tables found.")
        return pd.DataFrame()

    df = pd.concat(all_tables, ignore_index=True)

    # 1. Drop known junk rows
    if len(df) > 5:
        df = df.drop(index=[0,1,2,3,4]).reset_index(drop=True)
    else:
        return pd.DataFrame()

    # 2. Set Headers
    df.columns = df.iloc[0]
    df = df[1:].reset_index(drop=True)
    df.columns = _clean_columns(df.columns)

    # 3. Clean Headers & Values
    cols_to_drop = ["processed_date_time", "pool_drcr", "closing_pool_balance_rs", "closing_tag_balance_rs"]
    df = df.drop(columns=cols_to_drop, errors="ignore")

    replacements = {"drcr": "debit_credit", "rs": "rupees", "amt": "amount", "bal": "balance"}
    for k, v in replacements.items():
        df.columns = df.columns.str.replace(k, v, regex=False)

    for col in df.columns:
        df[col] = df[col].apply(_clean_cell_value)

    # 4. REPAIR SPLIT ROWS (Merging wrapped IDs)
    if "travel_date_time" in df.columns and "unique_transaction_id" in df.columns:
        rows_to_drop = []
        for i in range(1, len(df)):
            curr_date = str(df.loc[i, "travel_date_time"])
            curr_id_frag = str(df.loc[i, "unique_transaction_id"])
            
            is_invalid_date = (curr_date == "" or curr_date.lower() == "nan" or "nan" in curr_date.lower())
            has_fragment = (curr_id_frag != "" and curr_id_frag.lower() != "nan")
            
            if is_invalid_date and has_fragment:
                prev_idx = i - 1
                while prev_idx in rows_to_drop and prev_idx > 0:
                    prev_idx -= 1
                
                if prev_idx >= 0:
                    current_val = str(df.loc[prev_idx, "unique_transaction_id"])
                    if "HR" not in curr_id_frag and "DL" not in curr_id_frag: 
                         df.at[prev_idx, "unique_transaction_id"] = current_val + curr_id_frag
                         rows_to_drop.append(i)

        if rows_to_drop:
            df = df.drop(rows_to_drop).reset_index(drop=True)

    # 5. Extract Vehicle No from Header Rows
    if "travel_date_time" in df.columns:
        if "vehicle_number" not in df.columns:
            df["vehicle_number"] = None

        current_vehicle = None
        rows_to_drop = []

        for idx, row in df.iterrows():
            val = str(row["travel_date_time"]).strip()
            match = re.search(r'([A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4})', val.replace(" ", ""))
            is_date = re.search(r'\d{2}-\d{2}-\d{4}', val)
            
            if match and not is_date:
                current_vehicle = match.group(1)
                rows_to_drop.append(idx)
            else:
                existing_veh = str(row.get("vehicle_number", "")).strip()
                if current_vehicle and (existing_veh == "" or existing_veh.lower() == "nan"):
                    df.at[idx, "vehicle_number"] = current_vehicle

        if rows_to_drop:
            df = df.drop(rows_to_drop).reset_index(drop=True)

    # 6. Cleaning Helpers
    def _clean_vehicle_no(x):
        return x.replace(" ", "").strip() if isinstance(x, str) else x

    def _clean_datetime(x):
        if not isinstance(x, str): return x
        x = re.sub(r"\s+", " ", x).strip()
        x = re.sub(r"(\d{2})-(\d)\s(\d{3})", r"\1-\2\3", x)
        x = re.sub(r"(\d{2}):(\d)\s(\d):(\d{2})", r"\1:\2\3:\4", x)
        return x

    def _clean_reference_id(x):
        return x.replace(" ", "") if isinstance(x, str) else x

    if "vehicle_number" in df.columns:
        df["vehicle_number"] = df["vehicle_number"].apply(_clean_vehicle_no)
    
    if "travel_date_time" in df.columns:
        df["travel_date_time"] = df["travel_date_time"].apply(_clean_datetime)
    
    if "unique_transaction_id" in df.columns:
        df["unique_transaction_id"] = df["unique_transaction_id"].apply(_clean_reference_id)
        def safe_convert(x):
            try:
                if pd.isna(x): return ""
                x_str = str(x).strip()
                if x_str.replace('.', '', 1).isdigit():
                    return format(float(x_str), ".0f")
                return x_str
            except:
                return str(x)
        df["unique_transaction_id"] = df["unique_transaction_id"].apply(safe_convert)

    if "activity" in df.columns:
        df["activity"] = df["activity"].astype(str).str.strip()
        df = df[~df["activity"].str.lower().isin(["recharge", "", "nan", "none"])]

    df = clean_multiline_cells(df)

    # Smart Column Mapping
    final_map = {}
    for col in df.columns:
        c = col.lower()
        if "vehicle" in c:
            final_map[col] = "Vehicle No"
        elif "date" in c and "time" in c:
            final_map[col] = "Travel Date Time"
        elif "unique" in c or ("transaction" in c and "id" in c):
            final_map[col] = "Unique Transaction ID"
        elif "activity" in c:
            final_map[col] = "Activity"
        elif "debit" in c or "amount" in c:
            final_map[col] = "Tag Dr/Cr"
        elif ("plaza" in c and "id" in c) or ("lane" in c and "id" in c):
             final_map[col] = "Plaza ID"
        elif "plaza" in c or "description" in c or "toll" in c:
             if "id" not in c:
                 final_map[col] = "Plaza Name"

    df.rename(columns=final_map, inplace=True)
    return df

# ==========================================
# HELPER: IDFCB SPECIFIC CLEANER
# ==========================================
def _process_idfcb(pdf_obj):
    all_tables = []
    for page in pdf_obj.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_tables.append(pd.DataFrame(table))
    
    if not all_tables: 
        return pd.DataFrame()

    df = pd.concat(all_tables, ignore_index=True)
    df = df.dropna(how="all").reset_index(drop=True)

    # Extract Vehicle Number
    vehicle_val = ""
    try:
        if df.shape[0] > 1 and df.shape[1] > 3:
            raw_val = str(df.iat[1, 3])
            if raw_val and raw_val.lower() != 'nan':
                vehicle_val = raw_val.replace("\n", "").replace(" ", "").strip()
    except Exception:
        pass

    if len(df) > 5:
        df = df.drop(index=[0,1,2,3,4]).reset_index(drop=True)
    else:
        return pd.DataFrame()

    # ── FIX: skip the corrupted header row entirely ──────────────────────────
    # IDFCB always has exactly 9 columns in a fixed order regardless of OCR quality.
    # Assign names positionally so corrupted text ("dae tme", "Transacton") is ignored.
    IDFCB_COLS = [
        "Travel Date Time",        # col 0 – Reader date time
        "processed_date_time",     # col 1 – Processed date time (internal, dropped later)
        "Unique Transaction ID",   # col 2
        "Plaza Name",              # col 3
        "Plaza ID",                # col 4
        "Activity",                # col 5
        "credit",                  # col 6
        "Tag Dr/Cr",               # col 7 – Debit amount
        "closing_tag_balance",     # col 8 – dropped later
    ]

    # Skip the first row (it's the header we no longer need)
    df = df.iloc[1:].reset_index(drop=True)

    if df.shape[1] == len(IDFCB_COLS):
        df.columns = IDFCB_COLS
    elif df.shape[1] > len(IDFCB_COLS):
        # Extra columns possible on some extractions – assign what we can, drop rest
        df = df.iloc[:, :len(IDFCB_COLS)]
        df.columns = IDFCB_COLS
    else:
        # Unexpected shape – fall back gracefully
        df.columns = _clean_columns(df.columns)
    # ─────────────────────────────────────────────────────────────────────────

    # Clean numeric columns
    for c in ["Tag Dr/Cr", "credit", "closing_tag_balance"]:
        if c in df.columns:
            df[c] = (df[c].astype(str)
                         .str.replace("Dr", "", regex=False)
                         .str.replace("Cr", "", regex=False)
                         .str.replace(",", "", regex=False)
                         .str.strip())

    # Drop recharge / non-toll rows
    if "Activity" in df.columns:
        df["Activity"] = df["Activity"].astype(str).str.strip()
        act_lower = df["Activity"].str.lower()
        mask_junk = (
            act_lower.str.contains("recharge", na=False) |
            act_lower.str.contains("ccavenue", na=False) |
            act_lower.str.contains("rec harge", na=False) |
            act_lower.isin(["none", "nan", ""])
        )
        df = df[~mask_junk]

    df = clean_multiline_cells(df)

    df["Vehicle No"] = vehicle_val
    df = df[df.isna().sum(axis=1) <= 2]

    # Drop internal-only columns
    df.drop(columns=["processed_date_time", "closing_tag_balance", "credit"],
            errors="ignore", inplace=True)

    # Robust date parsing
    if "Travel Date Time" in df.columns:
        df["Travel Date Time"] = (df["Travel Date Time"]
            .astype(str)
            .str.replace(r'\s*\n+\s*', ' ', regex=True)
            .str.strip()
            .replace({"NA": "", "nan": "", "None": ""}))
        df["Travel Date Time"] = pd.to_datetime(df["Travel Date Time"], errors='coerce')

    return df
# ==========================================
# HELPER: INDUS SPECIFIC CLEANER
# ==========================================
# ==========================================
# HELPER: INDUS SPECIFIC CLEANER (UNIFIED FORMATS)
# ==========================================
def _process_indus(pdf_obj):
    all_tables = []
    for page in pdf_obj.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_tables.append(pd.DataFrame(table))
    
    if not all_tables: 
        return pd.DataFrame()

    df = pd.concat(all_tables, ignore_index=True)
    df = df.dropna(how="all").reset_index(drop=True)

    # 1. Dynamically Locate Header Row (Works for both formats)
    header_idx = -1
    for i in range(min(30, len(df))):
        row_str = "".join([str(x).lower() for x in df.iloc[i] if pd.notna(x)])
        # Indus tables always have 'debit' and either 'vehicle' or 'description' or 'dtstamp'
        if "debit" in row_str and ("vehicle" in row_str or "description" in row_str or "dtstamp" in row_str):
            header_idx = i
            break

    if header_idx == -1:
        return pd.DataFrame()

    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    # 2. Aggressive Column Cleanup
    df.columns = [re.sub(r"[^a-zA-Z0-9]", "", str(c)).lower() for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()].copy()

    # 3. Smart Column Mapping
    col_map = {}
    for col in df.columns:
        c = str(col)
        if "unique" in c or "dtstamp" in c or "stamp" in c:
            col_map[col] = "Unique Transaction ID"
        elif "vehicleno" in c or "vehicle" in c:
            col_map[col] = "Vehicle No"
        elif "datetime" in c or "date" in c or "time" in c or c == "transaction":
            # Only map the first one found to avoid overwriting
            if "Travel Date Time" not in col_map.values():
                col_map[col] = "Travel Date Time"
        elif "description" in c:
            col_map[col] = "Plaza Name"
        elif "type" in c or "activity" in c:
            col_map[col] = "Activity"
        elif "debit" in c or "amount" in c:
            if "credit" not in c and "bal" not in c:
                col_map[col] = "Tag Dr/Cr"

    df.rename(columns=col_map, inplace=True)

    # Enforce exact final columns
    for col in ["Unique Transaction ID", "Travel Date Time", "Plaza Name", "Vehicle No", "Tag Dr/Cr", "Activity", "Plaza ID"]:
        if col not in df.columns:
            df[col] = ""

    # 4. Handle "AM"/"PM" split rows (Common when pdfplumber misreads Indus PDFs)
    for i in range(1, len(df)):
        dt_val = str(df.at[i, "Travel Date Time"]).strip().upper()
        if dt_val in ["AM", "PM"]:
            prev_dt = str(df.at[i - 1, "Travel Date Time"]).strip()
            df.at[i - 1, "Travel Date Time"] = f"{prev_dt} {dt_val}"
            df.at[i, "Travel Date Time"] = np.nan

    # 5. Initial Junk Filtering
    df["Activity"] = df["Activity"].astype(str).str.strip()
    mask_junk = df["Activity"].str.lower().isin(
        ["recharge", "reload", "type", "type_of_transaction", "none", "nan", ""]
    )
    df = df[~mask_junk].reset_index(drop=True)

    # 6. Validate Vehicle Number
    # Drop rows where Vehicle No doesn't look like a standard Indian plate (e.g. headers bleeding over)
    df = df[df["Vehicle No"].astype(str).str.replace(r"\s+", "", regex=True).str.upper().str.match(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$", na=False)]

    # 7. Extract Exact Plaza Name
    def extract_plaza(val):
        if pd.isna(val): return ""
        s = str(val).replace("\n", " ").strip()
        # Format B: "Plaza Name : Bijwasan"
        if ":" in s:
            s = s.split(":", 1)[-1].strip()
        # Format A: "Toll Debit-Bijwasan"
        elif "-" in s:
            s = s.split("-", 1)[-1].strip()
        return s
    df["Plaza Name"] = df["Plaza Name"].apply(extract_plaza)

    # 8. Clean IDs
    # Removes leading apostrophes (e.g. '536647013...), spaces, and newlines
    df["Unique Transaction ID"] = df["Unique Transaction ID"].astype(str).str.replace(r"['\n\s]+", "", regex=True)

    # 9. Clean Amounts and Filter Valid Tolls
    df["Tag Dr/Cr"] = pd.to_numeric(df["Tag Dr/Cr"].astype(str).str.replace(r"[^\d\.]", "", regex=True), errors='coerce').fillna(0)
    df = df[df["Tag Dr/Cr"] > 0] # Strict filter for Debits only

    # 10. Clean Date Formatting (Stitch split date and time back together)
    df["Travel Date Time"] = df["Travel Date Time"].astype(str).str.replace(r"[\n\s]+", " ", regex=True).str.strip()

    df["Activity"] = "Toll Payment"

    df = df.dropna(subset=["Unique Transaction ID"])
    df = df[(df["Unique Transaction ID"] != "") & (df["Unique Transaction ID"].str.lower() != "nan")]

    return df[["Vehicle No", "Travel Date Time", "Unique Transaction ID", "Plaza Name", "Plaza ID", "Activity", "Tag Dr/Cr"]]

# ==========================================
# HELPER: SBI SPECIFIC CLEANER (Smart Extractor)
# ==========================================
def _process_sbi(pdf_obj):
    """
    Robust extractor for SBI Fastag PDFs.
    Handles 'squashed' rows where multiple transactions are merged into single cells.
    """
    all_tables = []
    for page in pdf_obj.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_tables.append(pd.DataFrame(table))
    
    if not all_tables: 
        return pd.DataFrame()

    df = pd.concat(all_tables, ignore_index=True)
    df = df.dropna(how='all').reset_index(drop=True)

    # 1. Locate the Header Row
    header_idx = -1
    for i in range(min(20, len(df))):
        # Flatten row to a single string for keyword searching
        row_str = "".join(str(x).lower() for x in df.iloc[i] if pd.notna(x))
        if "transactionid" in row_str or "amountinrs" in row_str:
            header_idx = i
            break

    if header_idx != -1:
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx+1:].reset_index(drop=True)

    # Clean column names heavily to ensure safe mapping (removes spaces, \n, \t)
    df.columns = df.columns.astype(str).str.replace(r"[^a-zA-Z0-9]", "", regex=True).str.lower()

    # 2. "Explode" Squashed Rows
    # The PDF merges multiple records into single cells separated by blank lines (\n\n).
    for col in df.columns:
        if df[col].dtype == object:
            # Split cells by 2 or more newlines into a list
            df[col] = df[col].astype(str).apply(
                lambda x: re.split(r'\n\s*\n+', x.strip()) if pd.notna(x) and x.strip() != "" and x.lower() != "nan" else [x]
            )

    # Safely explode the lists so each item gets its own row.
    # We pad lists to the same length in case the PDF parser missed a newline in one column.
    max_len = df.apply(lambda row: max([len(x) if isinstance(x, list) else 1 for x in row]), axis=1)
    for col in df.columns:
        df[col] = df.apply(
            lambda row: row[col] + [np.nan] * (max_len[row.name] - len(row[col])) if isinstance(row[col], list) else [row[col]] * max_len[row.name],
            axis=1
        )
    df = df.explode(list(df.columns)).reset_index(drop=True)

    # 3. Clean the text inside the un-squashed cells
    for col in df.columns:
        if df[col].dtype == object:
            if 'id' in col or 'date' in col or 'time' in col or 'amount' in col or 'vehicle' in col:
                # IDs and Amounts should have NO spaces or newlines (e.g. merging 720022-\n5366)
                df[col] = df[col].astype(str).str.replace(r"[\n\t\s]+", "", regex=True)
            else:
                # Descriptions and Names get spaces instead of newlines
                df[col] = df[col].astype(str).str.replace(r"[\n\t]+", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
            
            df[col] = df[col].replace(["nan", "None", ""], np.nan)

    # 4. Map to Final Columns
    # SBI splits Date and Time. We merge them here for the main pipeline.
    date_col = next((c for c in df.columns if 'date' in c), None)
    time_col = next((c for c in df.columns if 'time' in c), None)

    if date_col and time_col:
        df["Travel Date Time"] = df[date_col].astype(str) + " " + df[time_col].astype(str)
    elif date_col:
        df["Travel Date Time"] = df[date_col]
    else:
        df["Travel Date Time"] = ""

    # Clean up any leftover NaN strings from the merge
    df["Travel Date Time"] = df["Travel Date Time"].str.replace("nan nan", "").str.replace("nan", "").str.strip()

    rename_map = {}
    for col in df.columns:
        if 'transactionid' in col:
            rename_map[col] = "Unique Transaction ID"
        elif 'amount' in col:
            rename_map[col] = "Tag Dr/Cr"
        elif 'vehicleno' in col:
            rename_map[col] = "Vehicle No"
        elif 'plazaname' in col:
            rename_map[col] = "Plaza Name"
        elif 'plazaid' in col:
            rename_map[col] = "Plaza ID"

    df.rename(columns=rename_map, inplace=True)

    # 5. Finalize Schema
    if "Activity" not in df.columns:
        df["Activity"] = "Toll Payment" # Default for SBI

    final_cols = ["Vehicle No", "Travel Date Time", "Unique Transaction ID", "Plaza Name", "Plaza ID", "Activity", "Tag Dr/Cr"]
    
    for c in final_cols:
        if c not in df.columns:
            df[c] = ""
            
    df = df[final_cols]

    # Drop any remaining empty junk rows based on the ID
    df = df.dropna(subset=["Unique Transaction ID"], how="all")
    df = df[(df["Unique Transaction ID"] != "") & (df["Unique Transaction ID"].str.lower() != "nan")]

    return df


import re

# ==========================================
# HELPER: AMAZON PAY SPECIFIC CLEANER (FLATTENED REGEX)
# ==========================================
def _process_amazon(pdf_obj):
    all_rows = []
    
    full_text = ""
    for page in pdf_obj.pages:
        page_text = page.extract_text()
        if page_text:
            full_text += " " + page_text
    
    clean_text = re.sub(r'\s+', ' ', full_text)

    # ── FIX: dynamic VRN pattern instead of hardcoded "HR84A9525" ──────────
    # Indian VRN format: 2 letters + 2 digits + 1-2 letters + 4 digits  (e.g. HR38AK8732, HR84A9525)
    VRN_PATTERN = r"[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}"
    anchor_pattern = rf"(\d{{1,2}}\s+[A-Za-z]{{3}}\s+\d{{4}}\s+\d{{2}}:\d{{2}}\s+[APM]{{2}}\s+{VRN_PATTERN})"
    # ────────────────────────────────────────────────────────────────────────

    blocks = re.split(anchor_pattern, clean_text)
    
    for i in range(1, len(blocks), 2):
        header  = blocks[i]
        content = blocks[i+1] if i+1 < len(blocks) else ""
        
        header_parts = re.search(
            rf"(\d{{1,2}}\s+[A-Za-z]{{3}}\s+\d{{4}})\s+(\d{{2}}:\d{{2}}\s+[APM]{{2}})\s+({VRN_PATTERN})",
            header
        )
        if not header_parts:
            continue
            
        date_str, time_str, vehicle = header_parts.groups()

        id_match     = re.search(r"(P04-\d{7}-\d{7})", content)
        txn_id       = id_match.group(1) if id_match else "N/A"
        
        amount_match = re.search(r"Rs\.?\s*([\d\.]+)", content)
        amount       = amount_match.group(1) if amount_match else "0.0"

        # Skip Rs. 0.0 rows (no Charge ID = failed/free trip)
        if float(amount) == 0.0 or txn_id == "N/A":
            continue

        plaza_raw = re.split(r"P04-|Rs\.", content)[0].strip()

        all_rows.append({
            "Vehicle No":           vehicle,
            "Travel Date Time":     f"{date_str} {time_str}",
            "Unique Transaction ID": txn_id,
            "Plaza Name":           plaza_raw,
            "Plaza ID":             "",
            "Activity":             "Toll Payment",
            "Tag Dr/Cr":            amount
        })

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    return df[["Vehicle No", "Travel Date Time", "Unique Transaction ID",
               "Plaza Name", "Plaza ID", "Activity", "Tag Dr/Cr"]]
# ==========================================
# HELPER: AXIS BANK SPECIFIC CLEANER
# ==========================================
import re
import pandas as pd

def _process_axis(pdf_obj):
    all_tables = []
    for page in pdf_obj.pages:
        # Standard table extraction works best here, we will handle the newlines in Pandas
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_tables.append(pd.DataFrame(table))
    
    if not all_tables: 
        return pd.DataFrame()

    df = pd.concat(all_tables, ignore_index=True)
    df = df.dropna(how='all').reset_index(drop=True)

    # 1. Locate the Header Row dynamically
    header_idx = -1
    for i in range(min(30, len(df))):
        # Flatten row to a single string for keyword searching
        row_str = "".join([str(x).lower() for x in df.iloc[i] if pd.notna(x)])
        if "licence" in row_str and "account" in row_str:
            header_idx = i
            break

    if header_idx != -1:
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx+1:].reset_index(drop=True)

    # 2. Aggressive Column Cleanup
    # Removes ALL spaces, newlines, and brackets so 'Amount (Rs.)(DR)' becomes 'amountrsdr'
    df.columns = [re.sub(r"[^a-zA-Z0-9]", "", str(c)).lower() for c in df.columns]
    
    df = df.loc[:, ~df.columns.duplicated()].copy()
    df = df.dropna(how="all")

    # 3. Column Mapping
    col_map = {}
    for col in df.columns:
        c = str(col)
        if "transactiondate" in c:
            col_map[col] = "Travel Date Time"
        elif "uniquetransactionid" in c or "refno" in c:
            if "Unique Transaction ID" not in col_map.values():
                col_map[col] = "Unique Transaction ID"
        elif "licenceplate" in c or "vehicle" in c:
            col_map[col] = "Vehicle No"
        elif "transactiondescription" in c or "description" in c:
            col_map[col] = "Plaza Name" # We will parse the exact name from this block next
        elif "amountrsdr" in c or ("amount" in c and "dr" in c):
            col_map[col] = "Tag Dr/Cr"

    df.rename(columns=col_map, inplace=True)

    # Enforce standard columns
    for col in ["Unique Transaction ID", "Travel Date Time", "Plaza Name", "Vehicle No", "Tag Dr/Cr", "Activity", "Plaza ID"]:
        if col not in df.columns:
            df[col] = ""

    df["Activity"] = "Toll Payment"

    # 4. Clean Cell Values
    # Axis Bank formats IDs and Dates across multiple lines. This flattens them.
    df["Unique Transaction ID"] = df["Unique Transaction ID"].astype(str).str.replace(r"[\n\s/]+", "", regex=True)
    df["Vehicle No"] = df["Vehicle No"].astype(str).str.replace(r"[\n\s]+", "", regex=True)
    df["Travel Date Time"] = df["Travel Date Time"].astype(str).str.replace(r"[\n\s]+", " ", regex=True).str.strip()

    # Extract Plaza Name from the messy description sentence
    def extract_plaza(desc):
        if pd.isna(desc) or str(desc).lower() == "nan":
            return ""
        desc_str = str(desc).replace("\n", " ")
        # Looks for "at Plaza Bijwasan."
        match = re.search(r"at Plaza\s+([\w\s\-]+?)(?:\.|\s\s|$)", desc_str, re.IGNORECASE)
        return match.group(1).strip() if match else desc_str.strip()

    df["Plaza Name"] = df["Plaza Name"].apply(extract_plaza)

    # Filter only valid Toll Payments (Debits > 0)
    df["Tag Dr/Cr"] = df["Tag Dr/Cr"].astype(str).str.replace(r"[^\d\.]", "", regex=True)
    df["Tag Dr/Cr"] = pd.to_numeric(df["Tag Dr/Cr"], errors='coerce').fillna(0)
    
    # This filters out Recharges and Rs 0.00 Trip postings
    df = df[df["Tag Dr/Cr"] > 0] 

    # 5. Final Formatting
    df = clean_multiline_cells(df)
    df = df.dropna(subset=["Unique Transaction ID"])
    df = df[(df["Unique Transaction ID"] != "") & (df["Unique Transaction ID"].str.lower() != "nan")]

    return df[["Vehicle No", "Travel Date Time", "Unique Transaction ID", "Plaza Name", "Plaza ID", "Activity", "Tag Dr/Cr"]]

# ==========================================
# HELPER: UNITED SPECIFIC CLEANER
# ==========================================
def _process_united(pdf_obj):
    all_tables = []

    # 1. Extract tables from PDF object
    for page in pdf_obj.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_tables.append(pd.DataFrame(table))

    if not all_tables:
        return pd.DataFrame()

    # 2. Merge tables
    df = pd.concat(all_tables, ignore_index=True)
    df = df.dropna(how="all").reset_index(drop=True)

    # 3. Clean cell values using your robust logic
    def clean_cell_value(x):
        if isinstance(x, str):
            x = x.replace("\n", " ").replace("\t", " ")
            x = re.sub(r"\s+", " ", x)
            x = x.strip()
            if x.lower() in ["na", "n/a", "null", "none", ""]:
                return np.nan
        return x

    # Try map first (newer Pandas), fallback to applymap (older Pandas)
    try:
        df = df.map(clean_cell_value)
    except AttributeError:
        df = df.applymap(clean_cell_value)

    # 4. Locate actual transaction header row dynamically
    header_idx = -1
    for i in range(min(150, len(df))):
        row_str = "".join([str(x).lower() for x in df.iloc[i] if pd.notna(x)])
        if "date" in row_str and "activity" in row_str and "unique" in row_str:
            header_idx = i
            break

    if header_idx == -1:
        return pd.DataFrame()

    # 5. Slice transaction table
    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    # Clean final column names (strict alphanumeric)
    df.columns = [re.sub(r"[^a-zA-Z0-9]", "", str(c)).lower() for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()].copy()

    # 6. Extract Vehicle Number using Forward Fill (Your Logic)
    vehicle_pattern = r"\b[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}\b"
    
    def find_vehicle(row):
        for val in row:
            if isinstance(val, str):
                match = re.search(vehicle_pattern, val)
                if match:
                    return match.group()
        return np.nan

    df["Vehicle No"] = df.apply(find_vehicle, axis=1)
    df["Vehicle No"] = df["Vehicle No"].ffill()

    # 7. Identify columns safely for filtering
    date_col = next((c for c in df.columns if "date" in c and "time" in c), None)
    id_col = next((c for c in df.columns if "unique" in c and "id" in c), None)
    act_col = next((c for c in df.columns if "activity" in c), None)

    # 8. Filter out sub-headers and adjustments
    sub_header_pattern = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}\s*-"
    if date_col and id_col:
        df = df[
            ~(
                df[date_col].astype(str).str.match(sub_header_pattern, na=False) &
                df[id_col].isna()
            )
        ]
        
    if act_col:
        df = df[df[act_col].astype(str).str.lower() != "adjustment"].reset_index(drop=True)
        df = df[df[act_col].astype(str).str.lower() != "activity"].reset_index(drop=True)

    # 9. Map to Final Schema
    col_map = {}
    for col in df.columns:
        c = str(col)
        if "uniquetransactionid" in c: col_map[col] = "Unique Transaction ID"
        elif "date" in c and "time" in c: col_map[col] = "Travel Date Time"
        elif "transactiondescription" in c: col_map[col] = "Plaza Name"
        elif "amountrsdr" in c or ("amount" in c and "dr" in c): col_map[col] = "Tag Dr/Cr"
        elif "activity" in c: col_map[col] = "Activity"

    df.rename(columns=col_map, inplace=True)

    # Enforce exact final columns
    for col in ["Unique Transaction ID", "Travel Date Time", "Plaza Name", "Vehicle No", "Tag Dr/Cr", "Activity", "Plaza ID"]:
        if col not in df.columns:
            df[col] = ""

    # 10. Final Value Formatting
    
    # A. Apply your ID Cleaner
    def clean_slash_id(x):
        if pd.isna(x) or str(x).lower() == "nan": return ""
        return re.sub(r"\s+", "", str(x))
    df["Unique Transaction ID"] = df["Unique Transaction ID"].apply(clean_slash_id)

    # B. Clean up Plaza Name (Extracting just the toll name)
    def parse_plaza(desc):
        if pd.isna(desc): return ""
        match = re.search(r"Plaza Name:\s*(.*?)(?:-\s*Lane|$)", str(desc), re.IGNORECASE)
        return match.group(1).strip() if match else str(desc).strip()
    df["Plaza Name"] = df["Plaza Name"].apply(parse_plaza)
    
    # C. Default Activity to Toll Payment
    df["Activity"] = "Toll Payment"

    # 11. Final Cleanup
    df = df.dropna(subset=["Unique Transaction ID"])
    df = df[(df["Unique Transaction ID"] != "") & (df["Unique Transaction ID"].str.lower() != "nan")]

    return df[["Vehicle No", "Travel Date Time", "Unique Transaction ID", "Plaza Name", "Plaza ID", "Activity", "Tag Dr/Cr"]]
# ==========================================
# MAIN FASTAG DATA CLEANER (PDF)
# ==========================================
def process_fastag_data(file_data_list):
    try:
        print(f"🔹 Starting Fastag Processing for {len(file_data_list)} files...")
        processed_dfs = []

        for filename, content in file_data_list:
            try:
                fname_lower = filename.lower()
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    df_temp = None
                    
                    if "idfc.pdf" in fname_lower:
                        df_temp = _process_idfc(pdf)
                    elif "icici.pdf" in fname_lower:
                        df_temp = _process_icici(pdf)
                    elif "idfcb.pdf" in fname_lower:
                        df_temp = _process_idfcb(pdf)
                    elif "indus.pdf" in fname_lower:
                        df_temp = _process_indus(pdf)
                    elif "sbi.pdf" in fname_lower:
                        df_temp = _process_sbi(pdf)
                    elif "amaz" in fname_lower:
                        df_temp = _process_amazon(pdf)
                    elif "axis" in fname_lower:
                        df_temp = _process_axis(pdf)
                    elif "united" in fname_lower:
                        df_temp = _process_united(pdf)
                    else:
                        print(f"⚠️ File '{filename}' -> No Bank Name found.")
                        # You can use _process_united as a great default fallback since it is highly dynamic
                    if df_temp is not None and not df_temp.empty:
                        processed_dfs.append(df_temp)
                        print(f"✅ Successfully extracted {len(df_temp)} rows from {filename}")

            except Exception as e:
                print(f"⚠️ Error reading file {filename}: {e}")
                continue
        
        if not processed_dfs:
            print("❌ No valid data extracted.")
            return None, None, None

        cleaned_dfs = []
        for d in processed_dfs:
            d = d.loc[:, ~d.columns.duplicated()]
            d = d.reset_index(drop=True)
            cleaned_dfs.append(d)

        final_df = pd.concat(cleaned_dfs, ignore_index=True)

        desired_columns = ["Vehicle No", "Travel Date Time", "Unique Transaction ID", "Activity", "Plaza Name", "Tag Dr/Cr"]
        for col in desired_columns:
            if col not in final_df.columns:
                final_df[col] = ""

        final_df = final_df[desired_columns]

        if "Unique Transaction ID" in final_df.columns:
            final_df["Unique Transaction ID"] = (
                final_df["Unique Transaction ID"]
                .astype(str)
                .str.replace("\n", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.strip()
            )
            final_df = final_df[
                (final_df["Unique Transaction ID"] != "") & 
                (final_df["Unique Transaction ID"].str.lower() != "nan")
            ]


        if "Travel Date Time" in final_df.columns:
            mask = final_df["Travel Date Time"].astype(str).str.lower().str.contains("date|total|page", na=False)
            final_df = final_df[~mask]
            final_df["Travel Date Time"] = final_df["Travel Date Time"].astype(str).str.replace("/", "-", regex=False)
            
            # 🔥 THE FIX: Smarter Date Parser to prevent month/day flipping
            def safe_parse_date(val):
                if pd.isna(val) or str(val).strip() in ["", "nan", "None", "NaT"]:
                    return "" # Return empty string instead of NaT
                
                val_str = str(val).strip()
                
                try:
                    # If a helper already formatted it as YYYY-MM-DD, parse it normally
                    if re.match(r"^\d{4}-\d{2}-\d{2}", val_str):
                        dt = pd.to_datetime(val_str) # No dayfirst=True here!
                    else:
                        # If it's a raw Indian format (DD-MM-YYYY), enforce dayfirst
                        dt = pd.to_datetime(val_str, dayfirst=True)
                    
                    # Format the date right here, inside the function
                    return dt.strftime('%d-%m-%Y %H:%M:%S')
                except:
                    return ""

            # Apply the function. It now directly returns perfectly formatted strings!
            final_df["Travel Date Time"] = final_df["Travel Date Time"].apply(safe_parse_date)
            

        final_df["Vehicle No"] = (
            final_df["Vehicle No"].astype(str)
            .str.replace(" ", "", regex=False)
            .str.replace("-", "", regex=False)
            .str.upper()
            .replace("NAN", "")
            .replace("NONE", "")
        )

        final_df = final_df.rename(columns={"Tag Dr/Cr": "Amount"})
        final_df["Amount"] = pd.to_numeric(final_df["Amount"].astype(str).str.replace(",", ""), errors='coerce').fillna(0)
        final_df["Amount"] = final_df["Amount"].abs()
        final_df = final_df.fillna("")

        print(f"🔹 Processing complete. Final shape: {final_df.shape}")
        
        return create_styled_excel(final_df, "Fastag_Cleaned")

    except Exception as e:
        traceback.print_exc()
        print(f"❌ Fastag Cleaner Error: {e}")
        return None, None, None