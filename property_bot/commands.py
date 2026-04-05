from typing import Dict, Any
from datetime import datetime
from db import (
    get_empty_rooms_by_house, create_tenant, update_tenant_status,
    update_tenant, update_global_settings, get_unpaid_tenants, get_tenant
)
from whatsapp import send_whatsapp_text

SESSION_STORE: Dict[str, Dict[str, Any]] = {}

def format_list(unpaid_list):
    if not unpaid_list: return "No unpaid tenants."
    res = []
    for t in unpaid_list:
        res.append(f"Name: {t['name']}, House: {t['house_no']}, Room: {t['room_no']}, Pending Rent: {t['pending_rent']}")
    return "\n".join(res)

def handle_command(sender_id: str, text: str) -> bool:
    text = text.strip()

    if sender_id in SESSION_STORE:
        return process_session(sender_id, text)

    if not text.startswith("/"):
        return False

    cmd = text.split(" ")[0].lower()

    if cmd == "/add" and "tenant" in text.lower():
        return start_add_tenant(sender_id)

    elif cmd == "/delete" and "tenant" in text.lower():
        SESSION_STORE[sender_id] = {"command": "/deletetenant", "step": "ask_house_room"}
        send_whatsapp_text(sender_id, "Enter House No and Room No to delete (e.g., '1 101'):")
        return True

    elif cmd == "/setbase" and "rent" in text.lower():
        SESSION_STORE[sender_id] = {"command": "/setbaserent", "step": "ask_house_room"}
        send_whatsapp_text(sender_id, "Enter House No and Room No (e.g., '1 101'):")
        return True

    elif cmd == "/set" and "rate" in text.lower():
        SESSION_STORE[sender_id] = {"command": "/setpowerrate", "step": "ask_rate"}
        send_whatsapp_text(sender_id, "Enter new electricity cost per unit:")
        return True

    elif cmd == "/unpaid":
        unpaid_list = get_unpaid_tenants()
        msg = format_list(unpaid_list)
        send_whatsapp_text(sender_id, msg)
        return True

    elif cmd == "/balance":
        parts = text.split(" ")
        if len(parts) >= 3:
            house_no = parts[1]
            room_no = parts[2]
            tenant = get_tenant(house_no, room_no)
            if tenant:
                data = (
                    f"Due Rent: {tenant['pending_rent']}\n"
                    f"Due Bill: {tenant['pending_electricity']}\n"
                    f"Last Reading: {tenant['last_electricity_reading']}\n"
                    f"Paid: {tenant['total_paid']}\n"
                    f"Not Paid: {tenant['pending_rent'] + tenant['pending_electricity']}"
                )
                send_whatsapp_text(sender_id, data)
            else:
                send_whatsapp_text(sender_id, "Tenant not found.")
        else:
            send_whatsapp_text(sender_id, "Usage: /Balance [house] [room]")
        return True

    elif cmd == "/edit" and "tenant" in text.lower():
        SESSION_STORE[sender_id] = {"command": "/edittenant", "step": "ask_target"}
        send_whatsapp_text(sender_id, "Enter House and Room No (e.g., '1 101'):")
        return True

    elif cmd == "/cancel":
        if sender_id in SESSION_STORE:
            del SESSION_STORE[sender_id]
        send_whatsapp_text(sender_id, "Session closed. Process interrupted.")
        return True

    elif cmd == "/help":
        menu = (
            "/Add tenant - Registers new tenant\n"
            "/Delete tenant - Archives a tenant\n"
            "/Setbase rent - Change monthly rent\n"
            "/Set per rate - Change electricity unit price\n"
            "/Unpaid - View pending dues\n"
            "/Balance [house] [room] - View specific room data\n"
            "/Edit tenant - Modify tenant details\n"
            "/Cancel - Interrupt in process\n"
        )
        send_whatsapp_text(sender_id, menu)
        return True

    return False

def start_add_tenant(sender_id: str) -> bool:
    houses_dict = get_empty_rooms_by_house()
    houses = list(houses_dict.keys())

    if not houses:
        send_whatsapp_text(sender_id, "Which house? (No houses currently have active tenants, but you can enter a new house number)")
    else:
        h_str = ", ".join(houses)
        send_whatsapp_text(sender_id, f"Which house? (Active houses: {h_str})")

    SESSION_STORE[sender_id] = {"command": "/addtenant", "step": "ask_house"}
    return True

def process_session(sender_id: str, text: str) -> bool:
    session = SESSION_STORE[sender_id]
    cmd = session["command"]
    step = session["step"]

    if text.lower() == "/cancel":
        del SESSION_STORE[sender_id]
        send_whatsapp_text(sender_id, "Session closed. Process interrupted.")
        return True

    if cmd == "/addtenant":
        if step == "ask_house":
            session["data"] = {"house_no": text}

            # Now show filled rooms for this house
            houses_dict = get_empty_rooms_by_house()
            filled = houses_dict.get(text, [])

            if filled:
                r_str = ", ".join(filled)
                send_whatsapp_text(sender_id, f"Which room? (Currently filled rooms in house {text}: {r_str})")
            else:
                send_whatsapp_text(sender_id, f"Which room? (No filled rooms in house {text} yet)")

            session["step"] = "ask_room"

        elif step == "ask_room":
            session["data"]["room_no"] = text
            session["step"] = "ask_name"
            send_whatsapp_text(sender_id, "Name?")

        elif step == "ask_name":
            session["data"]["name"] = text
            session["step"] = "ask_phone"
            send_whatsapp_text(sender_id, "Phone no?")

        elif step == "ask_phone":
            session["data"]["phone"] = text
            session["step"] = "ask_rent"
            send_whatsapp_text(sender_id, "Monthly rent?")

        elif step == "ask_rent":
            try:
                session["data"]["rent"] = float(text)
                session["step"] = "ask_date"
                send_whatsapp_text(sender_id, "Starting date? (Format: DD-MM-YYYY, or type 'today')")
            except ValueError:
                send_whatsapp_text(sender_id, "Please enter a valid number for rent.")

        elif step == "ask_date":
            d = session["data"]
            date_input = text.lower()
            if date_input == "today":
                start_date = datetime.now().strftime("%Y-%m-%d")
            else:
                # Basic validation, but accept as is for robustness
                start_date = text

            success = create_tenant(d["house_no"], d["room_no"], d["name"], d["phone"], d["rent"], start_date)
            if success:
                send_whatsapp_text(sender_id, "Tenant added successfully.")
            else:
                send_whatsapp_text(sender_id, "Failed to add tenant (room might be filled).")
            del SESSION_STORE[sender_id]

    elif cmd == "/deletetenant":
        if step == "ask_house_room":
            parts = text.split(" ")
            if len(parts) >= 2:
                house_no, room_no = parts[0], parts[1]
                update_tenant_status(house_no, room_no, status="deleted")
                send_whatsapp_text(sender_id, "Tenant archived/deleted.")
                del SESSION_STORE[sender_id]
            else:
                send_whatsapp_text(sender_id, "Invalid format. Enter House No and Room No (e.g., '1 101').")

    elif cmd == "/setbaserent":
        if step == "ask_house_room":
            parts = text.split(" ")
            if len(parts) >= 2:
                session["data"] = {"house_no": parts[0], "room_no": parts[1]}
                session["step"] = "ask_amount"
                send_whatsapp_text(sender_id, "Enter new rent amount:")
            else:
                send_whatsapp_text(sender_id, "Invalid format. Enter House No and Room No (e.g., '1 101').")
        elif step == "ask_amount":
            try:
                amount = float(text)
                d = session["data"]
                update_tenant(d["house_no"], d["room_no"], rent=amount, pending_rent=amount)
                send_whatsapp_text(sender_id, "Rent updated for current month.")
                del SESSION_STORE[sender_id]
            except ValueError:
                send_whatsapp_text(sender_id, "Please enter a valid number.")

    elif cmd == "/setpowerrate":
        if step == "ask_rate":
            try:
                rate = float(text)
                update_global_settings(rate)
                send_whatsapp_text(sender_id, "Cost per unit updated.")
                del SESSION_STORE[sender_id]
            except ValueError:
                send_whatsapp_text(sender_id, "Please enter a valid number.")

    elif cmd == "/edittenant":
        if step == "ask_target":
            parts = text.split(" ")
            if len(parts) >= 2:
                session["data"] = {"house_no": parts[0], "room_no": parts[1]}
                session["step"] = "ask_field"
                send_whatsapp_text(sender_id, "What to edit? (Name, Phone, Rent)")
            else:
                send_whatsapp_text(sender_id, "Invalid format. Enter House No and Room No (e.g., '1 101').")
        elif step == "ask_field":
            field = text.lower()
            if field in ["name", "phone", "rent"]:
                session["data"]["field"] = field
                session["step"] = "ask_value"
                send_whatsapp_text(sender_id, "Enter new value:")
            else:
                send_whatsapp_text(sender_id, "Invalid field. Choose Name, Phone, or Rent.")
        elif step == "ask_value":
            d = session["data"]
            field_map = {"name": "name", "phone": "phone_number", "rent": "rent"}
            db_field = field_map[d["field"]]

            val = text
            if d["field"] == "rent":
                val = float(text)

            update_tenant(d["house_no"], d["room_no"], **{db_field: val})
            send_whatsapp_text(sender_id, "Tenant updated.")
            del SESSION_STORE[sender_id]

    return True
