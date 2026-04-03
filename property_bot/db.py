import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Dict, Any, List, Optional

load_dotenv()

# Setup Supabase client
url: str = os.environ.get("SUPABASE_URL", "")
key: str = os.environ.get("SUPABASE_KEY", "")

try:
    if url and key:
        supabase: Client = create_client(url, key)
    else:
        # Dummy client if env vars are missing
        supabase = None
except Exception as e:
    supabase = None

def get_tenant_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    """Retrieve tenant info by their WhatsApp phone number."""
    if not supabase:
        return None
    try:
        response = supabase.table("tenants").select("*").eq("phone_number", phone_number).eq("is_active", True).execute()
        data = response.data
        if data and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        print(f"Error fetching tenant: {e}")
        return None

def get_empty_rooms() -> List[Dict[str, Any]]:
    """Retrieve all rooms without an active tenant."""
    if not supabase:
        return []
    try:
        response = supabase.table("rooms").select("*").is_("active_tenant_id", "null").execute()
        return response.data
    except Exception as e:
        print(f"Error fetching empty rooms: {e}")
        return []

def add_tenant(room_id: int, name: str, phone_number: str) -> bool:
    """Insert a new tenant and assign them to a room."""
    if not supabase:
        return False
    try:
        # Insert new tenant
        tenant_data = {
            "name": name,
            "phone_number": phone_number,
            "is_active": True
        }
        res_tenant = supabase.table("tenants").insert(tenant_data).execute()
        if not res_tenant.data:
            return False

        tenant_id = res_tenant.data[0]["tenant_id"]

        # Update room with new tenant_id
        supabase.table("rooms").update({"active_tenant_id": tenant_id}).eq("room_id", room_id).execute()
        return True
    except Exception as e:
        print(f"Error adding tenant: {e}")
        return False

def archive_tenant(room_id: int) -> bool:
    """Soft delete tenant in a given room."""
    if not supabase:
        return False
    try:
        # Get active tenant in room
        res_room = supabase.table("rooms").select("active_tenant_id").eq("room_id", room_id).execute()
        if not res_room.data or not res_room.data[0].get("active_tenant_id"):
            return False

        tenant_id = res_room.data[0]["active_tenant_id"]

        # Soft delete tenant
        supabase.table("tenants").update({"is_active": False}).eq("tenant_id", tenant_id).execute()

        # Clear room assignment
        supabase.table("rooms").update({"active_tenant_id": None}).eq("room_id", room_id).execute()
        return True
    except Exception as e:
        print(f"Error archiving tenant: {e}")
        return False

def update_system_setting(setting_name: str, value: Any) -> bool:
    """Update system settings like power_rate_per_unit."""
    if not supabase:
        return False
    try:
        supabase.table("system_settings").update({"value": value}).eq("setting_name", setting_name).execute()
        return True
    except Exception as e:
        print(f"Error updating system setting: {e}")
        return False

def get_system_setting(setting_name: str) -> Any:
    if not supabase:
        return None
    try:
        res = supabase.table("system_settings").select("value").eq("setting_name", setting_name).execute()
        if res.data:
            return res.data[0].get("value")
        return None
    except Exception as e:
        return None

def update_room_rent(room_id: int, base_rent: float) -> bool:
    """Update base rent for a specific room."""
    if not supabase:
        return False
    try:
        supabase.table("rooms").update({"base_rent": base_rent}).eq("room_id", room_id).execute()
        return True
    except Exception as e:
        print(f"Error updating room rent: {e}")
        return False

def log_transaction(tenant_id: int, txn_type: str, amount: float, note: str, status: str = "pending_approval") -> Dict[str, Any]:
    """Log a transaction. Defaults to pending_approval."""
    if not supabase:
        return {}
    try:
        txn_data = {
            "tenant_id": tenant_id,
            "type": txn_type,
            "amount": amount,
            "note": note,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status
        }
        res = supabase.table("transactions").insert(txn_data).execute()
        if res.data:
            return res.data[0]
        return {}
    except Exception as e:
        print(f"Error logging transaction: {e}")
        return {}

def edit_transaction(txn_id: int, updates: Dict[str, Any]) -> bool:
    """Edit an existing transaction."""
    if not supabase:
        return False
    try:
        supabase.table("transactions").update(updates).eq("txn_id", txn_id).execute()
        return True
    except Exception as e:
        print(f"Error editing transaction: {e}")
        return False

def get_global_history(limit: int = 15) -> List[Dict[str, Any]]:
    """Fetch recent global transactions."""
    if not supabase:
        return []
    try:
        res = supabase.table("transactions").select("*, tenants(name, room:rooms(room_id))").order("timestamp", desc=True).limit(limit).execute()
        return res.data
    except Exception as e:
        print(f"Error fetching global history: {e}")
        return []

def get_tenant_ledger(tenant_id: int, limit: int = 8) -> List[Dict[str, Any]]:
    """Fetch recent transactions for a specific tenant."""
    if not supabase:
        return []
    try:
        res = supabase.table("transactions").select("*").eq("tenant_id", tenant_id).order("timestamp", desc=True).limit(limit).execute()
        return res.data
    except Exception as e:
        print(f"Error fetching tenant ledger: {e}")
        return []

def get_tenants_needing_reminders() -> List[Dict[str, Any]]:
    """Fetch tenants who haven't paid rent this month."""
    if not supabase:
        return []
    try:
        # Simplified query: assuming there's a field or logic. We will look up active tenants
        # and then check their transactions this month in the Python side, or assume a view exists.
        res = supabase.table("tenants").select("*, rooms(base_rent)").eq("is_active", True).execute()
        tenants = res.data

        # Check current month rent transactions
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()

        needing_reminders = []
        for t in tenants:
            tid = t["tenant_id"]
            # Look for completed rent payments this month
            tx_res = supabase.table("transactions").select("txn_id").eq("tenant_id", tid).eq("type", "rent").eq("status", "completed").gte("timestamp", start_of_month).execute()
            if not tx_res.data:
                needing_reminders.append(t)

        return needing_reminders
    except Exception as e:
        print(f"Error fetching reminder tenants: {e}")
        return []
