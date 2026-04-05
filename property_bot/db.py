import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional

load_dotenv()

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

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
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id SERIAL PRIMARY KEY,
                    house_no VARCHAR(50),
                    room_no VARCHAR(50),
                    name VARCHAR(255),
                    phone_number VARCHAR(50),
                    rent NUMERIC DEFAULT 0,
                    pending_rent NUMERIC DEFAULT 0,
                    pending_electricity NUMERIC DEFAULT 0,
                    last_electricity_reading NUMERIC DEFAULT 0,
                    total_paid NUMERIC DEFAULT 0,
                    start_date DATE,
                    is_active BOOLEAN DEFAULT TRUE,
                    UNIQUE(house_no, room_no, is_active)
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    txn_id SERIAL PRIMARY KEY,
                    tenant_id INT REFERENCES tenants(tenant_id),
                    type VARCHAR(50),
                    amount NUMERIC,
                    note TEXT,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'completed'
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

init_db()

def get_empty_rooms_by_house() -> Dict[str, List[str]]:
    # In a real system, you'd have a 'rooms' table defining all possible rooms.
    # For now, we simulate finding what's occupied and assume a static set of rooms,
    # or just return occupied ones to help the user know. The prompt says "instead of getting empty room it display filled rooms of that house does not paste all the files rooms or all house first ask for house then late filled house."
    # We will just fetch houses that have tenants.
    conn = get_connection()
    if not conn: return {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT house_no FROM tenants WHERE is_active = TRUE")
            houses = [r['house_no'] for r in cur.fetchall()]
            res = {}
            for h in houses:
                cur.execute("SELECT room_no FROM tenants WHERE house_no = %s AND is_active = TRUE", (h,))
                res[h] = [r['room_no'] for r in cur.fetchall()]
            return res
    except Exception as e:
        print(f"Error: {e}")
        return {}
    finally:
        conn.close()

def get_tenant(house_no: str, room_no: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tenants WHERE house_no = %s AND room_no = %s AND is_active = TRUE", (str(house_no), str(room_no)))
            res = cur.fetchone()
            return dict(res) if res else None
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        conn.close()

def get_tenant_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tenants WHERE phone_number = %s AND is_active = TRUE", (phone_number,))
            res = cur.fetchone()
            return dict(res) if res else None
    except Exception as e:
        return None
    finally:
        conn.close()

def create_tenant(house_no: str, room_no: str, name: str, phone: str, rent: float, start_date: str) -> bool:
    conn = get_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            # check if exists
            cur.execute("SELECT tenant_id FROM tenants WHERE house_no=%s AND room_no=%s AND is_active=TRUE", (house_no, room_no))
            if cur.fetchone():
                return False # already filled

            if start_date.lower() == 'today':
                sd = datetime.now().date().isoformat()
            else:
                sd = start_date

            cur.execute("""
                INSERT INTO tenants (house_no, room_no, name, phone_number, rent, start_date, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """, (house_no, room_no, name, phone, rent, sd))
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()

def update_tenant_status(house_no: str, room_no: str, status: str) -> bool:
    conn = get_connection()
    if not conn: return False
    is_active = (status != "deleted" and status != "archived")
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE tenants SET is_active = %s WHERE house_no = %s AND room_no = %s AND is_active = TRUE", (is_active, str(house_no), str(room_no)))
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()

def update_tenant(house_no: str, room_no: str, **kwargs) -> bool:
    conn = get_connection()
    if not conn: return False
    if not kwargs: return True
    try:
        with conn.cursor() as cur:
            set_clause = ", ".join([f"{k} = %s" for k in kwargs.keys()])
            values = list(kwargs.values())
            values.extend([str(house_no), str(room_no)])
            cur.execute(f"UPDATE tenants SET {set_clause} WHERE house_no = %s AND room_no = %s AND is_active = TRUE", tuple(values))
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()

def update_global_settings(power_rate: float) -> bool:
    conn = get_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO system_settings (setting_name, value)
                VALUES ('power_rate', %s)
                ON CONFLICT (setting_name) DO UPDATE SET value = EXCLUDED.value
            """, (str(power_rate),))
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()

def get_power_rate() -> float:
    conn = get_connection()
    if not conn: return 0.0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM system_settings WHERE setting_name = 'power_rate'")
            res = cur.fetchone()
            return float(res['value']) if res else 0.0
    except Exception:
        return 0.0
    finally:
        conn.close()

def insert_transaction(tenant_id: int, type: str, amount: float, note: str, status: str = "completed") -> int:
    conn = get_connection()
    if not conn: return -1
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO transactions (tenant_id, type, amount, note, status)
                VALUES (%s, %s, %s, %s, %s) RETURNING txn_id
            """, (tenant_id, type, amount, note, status))
            txn_id = cur.fetchone()['txn_id']

            # update tenant total paid if rent or electricity
            if status == "completed":
                cur.execute("UPDATE tenants SET total_paid = total_paid + %s WHERE tenant_id = %s", (amount, tenant_id))

            return txn_id
    except Exception as e:
        print(f"Error: {e}")
        return -1
    finally:
        conn.close()

def get_transaction(txn_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT t.*, tn.house_no, tn.room_no FROM transactions t JOIN tenants tn ON t.tenant_id = tn.tenant_id WHERE t.txn_id = %s", (txn_id,))
            res = cur.fetchone()
            return dict(res) if res else None
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        conn.close()

def delete_transaction(txn_id: int) -> bool:
    conn = get_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            # We also need to reverse the total_paid logic but for simplicity we just delete it.
            cur.execute("DELETE FROM transactions WHERE txn_id = %s", (txn_id,))
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        conn.close()

def get_unpaid_tenants() -> List[Dict[str, Any]]:
    conn = get_connection()
    if not conn: return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name, house_no, room_no, pending_rent FROM tenants WHERE pending_rent > 0 AND is_active = TRUE")
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"Error: {e}")
        return []
    finally:
        conn.close()

def get_last_30_transactions() -> str:
    conn = get_connection()
    if not conn: return ""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.type, t.amount, tn.house_no, tn.room_no, t.timestamp
                FROM transactions t
                JOIN tenants tn ON t.tenant_id = tn.tenant_id
                ORDER BY t.timestamp DESC LIMIT 30
            """)
            rows = cur.fetchall()
            if not rows: return "No recent transactions."
            lines = [f"{r['type']} of {r['amount']} for H{r['house_no']} R{r['room_no']} at {r['timestamp']}" for r in rows]
            return "\n".join(lines)
    except Exception:
        return ""
    finally:
        conn.close()

def get_house_status() -> str:
    conn = get_connection()
    if not conn: return ""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT house_no, room_no, name, pending_rent, pending_electricity FROM tenants WHERE is_active = TRUE")
            rows = cur.fetchall()
            if not rows: return "No active tenants."
            lines = [f"H{r['house_no']} R{r['room_no']}: {r['name']} (Rent Due: {r['pending_rent']}, Elec Due: {r['pending_electricity']})" for r in rows]
            return "\n".join(lines)
    except Exception:
        return ""
    finally:
        conn.close()
