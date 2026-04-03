from typing import Dict, Any
from db import get_empty_rooms, add_tenant, archive_tenant, update_system_setting, update_room_rent
from whatsapp import send_whatsapp_text

# In-memory session store for multi-step commands
# Format: { user_id: { "command": "/addtenant", "step": 1, "data": {} } }
SESSION_STORE: Dict[str, Dict[str, Any]] = {}

def handle_command(sender_id: str, text: str) -> bool:
    """Handle hardcoded slash commands. Returns True if a command was handled, False otherwise."""
    text = text.strip()

    # Check if user is in an active session
    if sender_id in SESSION_STORE:
        return process_session(sender_id, text)

    if not text.startswith("/"):
        return False

    parts = text.split(" ")
    cmd = parts[0].lower()

    if cmd == "/addtenant":
        return start_add_tenant(sender_id)

    elif cmd == "/archivetenant":
        if len(parts) < 2:
            send_whatsapp_text(sender_id, "Usage: /archivetenant <room_id>")
            return True
        try:
            room_id = int(parts[1])
            success = archive_tenant(room_id)
            msg = "Tenant archived successfully." if success else "Failed to archive tenant. Check room ID."
            send_whatsapp_text(sender_id, msg)
        except ValueError:
            send_whatsapp_text(sender_id, "Invalid room ID format.")
        return True

    elif cmd == "/setbaserent":
        if len(parts) < 3:
            send_whatsapp_text(sender_id, "Usage: /setbaserent <room_id> <amount>")
            return True
        try:
            room_id = int(parts[1])
            amount = float(parts[2])
            success = update_room_rent(room_id, amount)
            msg = "Base rent updated successfully." if success else "Failed to update base rent."
            send_whatsapp_text(sender_id, msg)
        except ValueError:
            send_whatsapp_text(sender_id, "Invalid numbers provided.")
        return True

    elif cmd == "/setpowerrate":
        if len(parts) < 2:
            send_whatsapp_text(sender_id, "Usage: /setpowerrate <rate>")
            return True
        try:
            rate = float(parts[1])
            success = update_system_setting("power_rate_per_unit", rate)
            msg = f"Power rate updated to {rate} successfully." if success else "Failed to update power rate."
            send_whatsapp_text(sender_id, msg)
        except ValueError:
            send_whatsapp_text(sender_id, "Invalid rate provided.")
        return True

    elif cmd == "/cancel":
        if sender_id in SESSION_STORE:
            del SESSION_STORE[sender_id]
            send_whatsapp_text(sender_id, "Current operation cancelled.")
        else:
            send_whatsapp_text(sender_id, "No active operation to cancel.")
        return True

    return False

def start_add_tenant(sender_id: str) -> bool:
    """Start the /addtenant workflow."""
    rooms = get_empty_rooms()
    if not rooms:
        send_whatsapp_text(sender_id, "No empty rooms available. Cannot add tenant.")
        return True

    room_str = ", ".join([str(r["room_id"]) for r in rooms])
    send_whatsapp_text(sender_id, f"Empty rooms: {room_str}. Please enter the Room No you want to assign:")

    SESSION_STORE[sender_id] = {
        "command": "/addtenant",
        "step": "ask_room",
        "data": {"available_rooms": [r["room_id"] for r in rooms]}
    }
    return True

def process_session(sender_id: str, text: str) -> bool:
    """Process the next step in an active session."""
    session = SESSION_STORE[sender_id]
    cmd = session["command"]
    step = session["step"]

    if text.lower() == "/cancel":
        del SESSION_STORE[sender_id]
        send_whatsapp_text(sender_id, "Operation cancelled.")
        return True

    if cmd == "/addtenant":
        if step == "ask_room":
            try:
                room_id = int(text)
                if room_id not in session["data"]["available_rooms"]:
                    send_whatsapp_text(sender_id, "Invalid room ID. Please enter an available empty room.")
                    return True

                session["data"]["room_id"] = room_id
                session["step"] = "ask_name"
                send_whatsapp_text(sender_id, "Room selected. Please enter the tenant's full name:")
            except ValueError:
                send_whatsapp_text(sender_id, "Please enter a valid numeric room ID.")

        elif step == "ask_name":
            session["data"]["name"] = text
            session["step"] = "ask_phone"
            send_whatsapp_text(sender_id, "Name saved. Please enter the tenant's WhatsApp phone number (with country code, e.g. 919876543210):")

        elif step == "ask_phone":
            session["data"]["phone"] = text
            session["step"] = "confirm"

            summary = f"Please confirm the details:\nRoom: {session['data']['room_id']}\nName: {session['data']['name']}\nPhone: {session['data']['phone']}\n\nReply 'yes' to confirm or '/cancel' to abort."
            send_whatsapp_text(sender_id, summary)

        elif step == "confirm":
            if text.lower() == "yes":
                d = session["data"]
                success = add_tenant(d["room_id"], d["name"], d["phone"])
                if success:
                    send_whatsapp_text(sender_id, "Tenant added successfully!")
                else:
                    send_whatsapp_text(sender_id, "Error adding tenant to the database. Please try again.")
                del SESSION_STORE[sender_id]
            else:
                send_whatsapp_text(sender_id, "Reply 'yes' to confirm or '/cancel' to abort.")

        return True

    return False
