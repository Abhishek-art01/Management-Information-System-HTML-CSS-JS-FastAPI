from sqlmodel import SQLModel, Field
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict

# Base model with dynamic column support
class DynamicSQLModel(SQLModel):
    """Base model that allows dynamic columns"""
    model_config = ConfigDict(extra='allow')
    _extra_fields: Dict[str, Any] = {}

# --- 1. USER & AUTH ---
class User(DynamicSQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str


class TripDataBase(DynamicSQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    unique_id: str = Field(index=True, unique=True)

    shift_date: Optional[str] = None
    trip_direction: Optional[str] = None
    route_no: Optional[str] = None
    trip_id: Optional[str] = None
    flight_number: Optional[str] = None
    employee_id: Optional[str] = None
    gender: Optional[str] = None
    emp_category: Optional[str] = None
    employee_name: Optional[str] = None
    address: Optional[str] = None
    landmark: Optional[str] = None
    shift_time: Optional[str] = None
    cab_last_digit: Optional[str] = None
    cab_reg_no: Optional[str] = None
    cab_type: Optional[str] = None
    marshall: Optional[str] = None
    vendor: Optional[str] = None
    office: Optional[str] = None
    mis_remark: Optional[str] = None

    trip_date: Optional[str] = None
    data_source: Optional[str] = None
    pickup_time: Optional[str] = None
    drop_time: Optional[str] = None
    ba_remark: Optional[str] = None
    route_status: Optional[str] = None
    clubbing_status: Optional[str] = None
    journey_start_location: Optional[str] = None
    journey_end_location: Optional[str] = None
    gps_time: Optional[str] = None
    gps_remark: Optional[str] = None
    claim_status: Optional[str] = None

    staff_count: Optional[int] = None
    billable_count: Optional[int] = None

    one_side: Optional[str] = None
    two_side: Optional[float] = None
    club_km: Optional[float] = None
    toll_km: Optional[float] = None
    total_km: Optional[float] = None

    unique_toll_id: Optional[str] = None
    unique_toll_trn_id: Optional[str] = None
    travel_date_time: Optional[str] = None

    toll_name: Optional[str] = None
    toll_amount: Optional[float] = None
    total_amount: Optional[float] = None

    b2b_deducted: Optional[float] = None

class TripDataFile(DynamicSQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)

    # ... (Your existing fields remain the same) ...
    shift_date: Optional[str] = None
    trip_direction: Optional[str] = None
    trip_id: Optional[str] = None
    flight_number: Optional[str] = None
    employee_id: Optional[str] = None
    gender: Optional[str] = None
    emp_category: Optional[str] = None
    employee_name: Optional[str] = None
    address: Optional[str] = None
    landmark: Optional[str] = None
    shift_time: Optional[str] = None
    cab_last_digit: Optional[str] = None
    cab_reg_no: Optional[str] = None
    vendor: Optional[str] = None
    office: Optional[str] = None
    mis_remark: Optional[str] = None
    
    # Special columns
    data_source : Optional[str] = None
    unique_id: str = Field(index=True, unique=True)
    ba_remark: Optional[str] = None
    route_status: Optional[str] = None
    clubbing_status: Optional[str] = None
    

# --- 3. CLIENT DATA ---
class ClientData(TripDataBase, table=True):
    __tablename__ = "clientdata"
    id: Optional[int] = Field(default=None, primary_key=True)

# --- 4. RAW TRIP DATA ---
class RawTripData(TripDataBase, table=True):
    __tablename__ = "rawtripdata"
    id: Optional[int] = Field(default=None, primary_key=True)

# --- 5.OPERATION DATA ---
class OperationData(TripDataBase, table=True):
    __tablename__ = "operationdata"
    id: Optional[int] = Field(default=None, primary_key=True)

# --- 5.trip Data ---
class TripData(TripDataBase, table=True):
    __tablename__ = "tripdata"
    id: Optional[int] = Field(default=None, primary_key=True)

# --- 6. BA ROW DATA ---
class BARowData(TripDataBase, table=True):
    __tablename__ = "barowdata"
    id: Optional[int] = Field(default=None, primary_key=True)

# --- 7. ZONE & KM TABLES (CRITICAL FIXES HERE) ---
class T3ZoneKm(DynamicSQLModel, table=True):
    __tablename__ = "t3_zone_km"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    # ✅ FIX 1: Added unique=True. Required because 'T3LocalityZone' references this column.
    zone: str = Field(index=True, unique=True) 
    km: str

class T3LocalityZone(DynamicSQLModel, table=True):
    __tablename__ = "t3_locality_zone"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    # ✅ FIX 2: Added unique=True. Required because 'T3AddressLocality' references this column.
    locality: str = Field(index=True, unique=True) 
    zone: Optional[str] = Field(default=None, foreign_key="t3_zone_km.zone")

class T3AddressLocality(DynamicSQLModel, table=True):
    __tablename__ = "t3_address_locality"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    address: str = Field(index=True, unique=True)
    locality: Optional[str] = Field(default=None, foreign_key="t3_locality_zone.locality")
    zone: Optional[str] = Field(default=None)
    km: Optional[str] = Field(default=None)

# --- 8. VEHICLE MASTER ---
class VehicleMaster(DynamicSQLModel, table=True):
    __tablename__ = "vehicle_master"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    vehicle_id: Optional[str] = None
    vehicle_no: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_registration_no: Optional[str] = None
    vehicle_owner_name: Optional[str] = None
    vehicle_owner_mobile: Optional[str] = None
    vehicle_driver_name: Optional[str] = None
    vehicle_driver_mobile: Optional[str] = None
    vehicle_rc: Optional[str] = None
    
#T3 running vehicle
class T3RunningVehicle(DynamicSQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    vehicle_id: Optional[str] = None
    vehicle_no: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_registration_no: Optional[str] = None
    vehicle_owner_name: Optional[str] = None
    vehicle_owner_mobile: Optional[str] = None
    vehicle_driver_name: Optional[str] = None
    vehicle_driver_mobile: Optional[str] = None
    mcd: Optional[str] = None
    fastag: Optional[str] = None

#T3 running vehicle
class T3RunningVehiclefeb2026(DynamicSQLModel, table=True):
    __tablename__ = "t3_running_vehicle_feb_2026"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    vehicle_id: Optional[str] = None
    vehicle_no: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_registration_no: Optional[str] = None
    vehicle_owner_name: Optional[str] = None
    vehicle_owner_mobile: Optional[str] = None
    vehicle_driver_name: Optional[str] = None
    vehicle_driver_mobile: Optional[str] = None
    mcd: Optional[str] = None
    fastag: Optional[str] = None
    
from typing import Optional
from sqlmodel import Field

class TollData(DynamicSQLModel, table=True):
    __tablename__ = "toll_data"

    # ID is a string primary key
    id: str = Field(primary_key=True, unique=True)

    veh: Optional[str] = None
    owner_type: Optional[str] = None
    date: Optional[str] = None
    travel_date_time: Optional[str] = None
    unique_transaction_id: Optional[str] = None
    transaction_description: Optional[str] = None
    activity: Optional[str] = None

    amount: Optional[float] = None

    toll_id: Optional[str] = None
    unique_id: Optional[str] = None
    remark: Optional[str] = None
    toll_una: Optional[str] = None

class Toll_locality(DynamicSQLModel, table=True):
    __tablename__ = "toll_locality"
    
    # User Request: ID is NOT an int, but is unique. 
    id: str = Field(primary_key=True, unique=True)
    
    toll_id: Optional[str] = None
    unique_id: Optional[str] = None
    toll_name: Optional[str] = None
    office: Optional[str] = None
    landmark: Optional[str] = None
    
    # Amount is best stored as a float to allow for calculations
    km: Optional[str] = None


# --- Pydantic Schemas ---
class LocalityMappingSchema(BaseModel):
    address_id: int
    locality_name: str

class BulkMappingSchema(BaseModel):
    address_ids: List[int]
    locality_name: str

class NewMasterSchema(BaseModel):
    locality_name: str
    zone_name: str

# --- Dynamic Column Management ---
class DynamicColumnSchema(BaseModel):
    model_name: str
    column_name: str
    column_type: str
    default_value: Optional[Any] = None
    is_nullable: bool = True

class TableSchemaResponse(BaseModel):
    table_name: str
    columns: List[Dict[str, Any]]
    row_count: Optional[int] = None

class TollRouteRule(DynamicSQLModel, table=True):
    __tablename__ = "toll_route_rules"

    id: Optional[int] = Field(default=None, primary_key=True)

    landmark:  Optional[str] = Field(default=None, index=True)
    office:    Optional[str] = Field(default=None, index=True)

    # toll_name = transaction_description from TollData (normalised UPPER)
    toll_name: Optional[str] = Field(default=None, index=True)

    # True  = confirmed toll route
    # False = NOT a toll route (hidden on load)
    is_toll_route: bool = Field(default=True)

    created_at: Optional[str] = Field(default=None)