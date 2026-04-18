import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Initialize Supabase client
if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

def init_db():
    # Since Supabase python client doesn't support raw SQL execution easily without RPC,
    # the tables are typically created via the Supabase dashboard or migrations.
    # We will assume they exist based on schema.sql provided.
    pass

def get_tenant_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    if not supabase: return None
    try:
        response = supabase.table("tenants").select("*").eq("phone_number", phone_number).eq("is_active", True).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error fetching tenant by phone: {e}")
        return None

def get_tenant_by_room(house_no: str, room_no: str) -> Optional[Dict[str, Any]]:
    if not supabase: return None
    try:
        # First get house id
        house_resp = supabase.table("houses").select("id").eq("house_no", house_no).execute()
        if not house_resp.data:
            return None
        house_id = house_resp.data[0]["id"]

        response = supabase.table("tenants").select("*").eq("house_id", house_id).eq("room_no", room_no).eq("is_active", True).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error fetching tenant by room: {e}")
        return None

def add_tenant(house_no: str, room_no: str, name: str, phone_number: str, rent_amount: float, current_meter_reading: float, billing_cycle_date: int) -> bool:
    if not supabase: return False
    try:
        # Get or create house
        house_resp = supabase.table("houses").select("id").eq("house_no", house_no).execute()
        if house_resp.data:
            house_id = house_resp.data[0]["id"]
        else:
            new_house = supabase.table("houses").insert({"house_no": house_no}).execute()
            house_id = new_house.data[0]["id"]

        data = {
            "house_id": house_id,
            "room_no": room_no,
            "name": name,
            "phone_number": phone_number,
            "rent_amount": rent_amount,
            "last_meter_reading": current_meter_reading,
            "billing_cycle_date": billing_cycle_date,
            "is_active": True
        }
        supabase.table("tenants").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error adding tenant: {e}")
        return False

def update_tenant_balances(tenant_id: str, updates: Dict[str, Any]) -> bool:
    if not supabase: return False
    try:
        supabase.table("tenants").update(updates).eq("id", tenant_id).execute()
        return True
    except Exception as e:
        print(f"Error updating tenant balances: {e}")
        return False

def archive_tenant(tenant_id: str) -> bool:
    if not supabase: return False
    try:
        supabase.table("tenants").update({"is_active": False}).eq("id", tenant_id).execute()
        return True
    except Exception as e:
        print(f"Error archiving tenant: {e}")
        return False

def log_transaction(tenant_id: str, txn_type: str, amount: float, description: str) -> Optional[str]:
    if not supabase: return None
    try:
        data = {
            "tenant_id": tenant_id,
            "transaction_type": txn_type,
            "amount": amount,
            "description": description
        }
        resp = supabase.table("transactions").insert(data).execute()
        return resp.data[0]["id"] if resp.data else None
    except Exception as e:
        print(f"Error logging transaction: {e}")
        return None

def get_tenant_ledger(tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    if not supabase: return []
    try:
        resp = supabase.table("transactions").select("*").eq("tenant_id", tenant_id).order("created_at", desc=True).limit(limit).execute()
        return resp.data
    except Exception as e:
        print(f"Error fetching tenant ledger: {e}")
        return []

def get_tenants_needing_reminders(today_date: int) -> List[Dict[str, Any]]:
    if not supabase: return []
    try:
        resp = supabase.table("tenants").select("*").eq("is_active", True).eq("billing_cycle_date", today_date).execute()
        return resp.data
    except Exception as e:
        print(f"Error fetching reminder tenants: {e}")
        return []
