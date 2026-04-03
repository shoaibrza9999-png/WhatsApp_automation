import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional

load_dotenv()

# Setup Neon Postgres client
DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_ZlDvyOwNXx60@ep-cold-band-am40hnph-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

def get_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            # Create tables if they don't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id SERIAL PRIMARY KEY,
                    house_id INT,
                    base_rent NUMERIC,
                    active_tenant_id INT
                );

                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id SERIAL PRIMARY KEY,
                    name VARCHAR(255),
                    phone_number VARCHAR(50),
                    is_active BOOLEAN DEFAULT TRUE
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    txn_id SERIAL PRIMARY KEY,
                    tenant_id INT,
                    type VARCHAR(50),
                    amount NUMERIC,
                    note TEXT,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'pending_approval'
                );

                CREATE TABLE IF NOT EXISTS system_settings (
                    setting_name VARCHAR(100) PRIMARY KEY,
                    value VARCHAR(255)
                );
            """)
    except Exception as e:
        print(f"Error initializing DB: {e}")
    finally:
        conn.close()

# Initialize DB structure
init_db()

def get_tenant_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tenants WHERE phone_number = %s AND is_active = TRUE", (phone_number,))
            res = cur.fetchone()
            return dict(res) if res else None
    except Exception as e:
        print(f"Error fetching tenant: {e}")
        return None
    finally:
        conn.close()

def get_empty_rooms() -> List[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM rooms WHERE active_tenant_id IS NULL")
            res = cur.fetchall()
            return [dict(r) for r in res]
    except Exception as e:
        print(f"Error fetching empty rooms: {e}")
        return []
    finally:
        conn.close()

def add_tenant(room_id: int, name: str, phone_number: str) -> bool:
    conn = get_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO tenants (name, phone_number, is_active) VALUES (%s, %s, TRUE) RETURNING tenant_id", (name, phone_number))
            tenant_id = cur.fetchone()['tenant_id']
            cur.execute("UPDATE rooms SET active_tenant_id = %s WHERE room_id = %s", (tenant_id, room_id))
            return True
    except Exception as e:
        print(f"Error adding tenant: {e}")
        return False
    finally:
        conn.close()

def archive_tenant(room_id: int) -> bool:
    conn = get_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT active_tenant_id FROM rooms WHERE room_id = %s", (room_id,))
            res = cur.fetchone()
            if not res or not res['active_tenant_id']:
                return False
            tenant_id = res['active_tenant_id']

            cur.execute("UPDATE tenants SET is_active = FALSE WHERE tenant_id = %s", (tenant_id,))
            cur.execute("UPDATE rooms SET active_tenant_id = NULL WHERE room_id = %s", (room_id,))
            return True
    except Exception as e:
        print(f"Error archiving tenant: {e}")
        return False
    finally:
        conn.close()

def update_system_setting(setting_name: str, value: Any) -> bool:
    conn = get_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO system_settings (setting_name, value)
                VALUES (%s, %s)
                ON CONFLICT (setting_name)
                DO UPDATE SET value = EXCLUDED.value
            """, (setting_name, str(value)))
            return True
    except Exception as e:
        print(f"Error updating system setting: {e}")
        return False
    finally:
        conn.close()

def get_system_setting(setting_name: str) -> Any:
    conn = get_connection()
    if not conn: return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM system_settings WHERE setting_name = %s", (setting_name,))
            res = cur.fetchone()
            return res['value'] if res else None
    except Exception as e:
        return None
    finally:
        conn.close()

def update_room_rent(room_id: int, base_rent: float) -> bool:
    conn = get_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE rooms SET base_rent = %s WHERE room_id = %s", (base_rent, room_id))
            return True
    except Exception as e:
        print(f"Error updating room rent: {e}")
        return False
    finally:
        conn.close()

def log_transaction(tenant_id: int, txn_type: str, amount: float, note: str, status: str = "pending_approval") -> Dict[str, Any]:
    conn = get_connection()
    if not conn: return {}
    try:
        with conn.cursor() as cur:
            ts = datetime.now(timezone.utc).isoformat()
            cur.execute("""
                INSERT INTO transactions (tenant_id, type, amount, note, timestamp, status)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING txn_id
            """, (tenant_id, txn_type, amount, note, ts, status))
            txn_id = cur.fetchone()['txn_id']
            return {"txn_id": txn_id, "status": status}
    except Exception as e:
        print(f"Error logging transaction: {e}")
        return {}
    finally:
        conn.close()

def edit_transaction(txn_id: int, updates: Dict[str, Any]) -> bool:
    conn = get_connection()
    if not conn: return False
    if not updates: return False
    try:
        with conn.cursor() as cur:
            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            values = list(updates.values())
            values.append(txn_id)
            cur.execute(f"UPDATE transactions SET {set_clause} WHERE txn_id = %s", tuple(values))
            return True
    except Exception as e:
        print(f"Error editing transaction: {e}")
        return False
    finally:
        conn.close()

def get_global_history(limit: int = 15) -> List[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.*, tn.name as tenant_name, r.room_id
                FROM transactions t
                LEFT JOIN tenants tn ON t.tenant_id = tn.tenant_id
                LEFT JOIN rooms r ON tn.tenant_id = r.active_tenant_id
                ORDER BY t.timestamp DESC LIMIT %s
            """, (limit,))
            res = cur.fetchall()

            # format to match previous output shape
            formatted = []
            for r in res:
                d = dict(r)
                d['tenants'] = {
                    'name': d.get('tenant_name'),
                    'room': {'room_id': d.get('room_id')}
                }
                formatted.append(d)
            return formatted
    except Exception as e:
        print(f"Error fetching global history: {e}")
        return []
    finally:
        conn.close()

def get_tenant_ledger(tenant_id: int, limit: int = 8) -> List[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM transactions WHERE tenant_id = %s ORDER BY timestamp DESC LIMIT %s", (tenant_id, limit))
            res = cur.fetchall()
            return [dict(r) for r in res]
    except Exception as e:
        print(f"Error fetching tenant ledger: {e}")
        return []
    finally:
        conn.close()

def get_tenants_needing_reminders() -> List[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return []
    try:
        with conn.cursor() as cur:
            now = datetime.now(timezone.utc)
            start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()

            cur.execute("""
                SELECT t.*, r.base_rent
                FROM tenants t
                LEFT JOIN rooms r ON t.tenant_id = r.active_tenant_id
                WHERE t.is_active = TRUE AND t.tenant_id NOT IN (
                    SELECT tenant_id FROM transactions
                    WHERE type = 'rent' AND status = 'completed' AND timestamp >= %s
                )
            """, (start_of_month,))

            res = cur.fetchall()

            formatted = []
            for r in res:
                d = dict(r)
                d['rooms'] = {'base_rent': d.get('base_rent')}
                formatted.append(d)
            return formatted
    except Exception as e:
        print(f"Error fetching reminder tenants: {e}")
        return []
    finally:
        conn.close()
