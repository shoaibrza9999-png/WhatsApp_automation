import os
from langchain_core.tools import tool
from typing import Optional
from db import add_tenant as db_add_tenant
from db import get_tenant_by_room, update_tenant_balances, log_transaction, archive_tenant
from whatsapp import send_whatsapp_text

@tool
def add_tenant(house_no: str, room_no: str, name: str, phone_number: str, rent_amount: float, current_meter_reading: float, billing_cycle_date: int) -> str:
    """Register a new tenant.
    Args:
        house_no: The house number.
        room_no: The room number.
        name: Name of the tenant.
        phone_number: Phone number of the tenant.
        rent_amount: The monthly rent amount.
        current_meter_reading: Current electricity meter reading.
        billing_cycle_date: The day of the month rent is due (1-28).
    """
    success = db_add_tenant(house_no, room_no, name, phone_number, rent_amount, current_meter_reading, billing_cycle_date)
    if success:
        send_whatsapp_text(phone_number, f"Welcome! You have been registered in House {house_no}, Room {room_no} by the landlord.")
        return "Tenant successfully added."
    return "Failed to add tenant."

@tool
def electricity_increase(house_no: str, room_no: str, current_unit: float) -> str:
    """Charge a tenant for electricity based on the current meter reading. Requires HITL.
    Args:
        house_no: The house number.
        room_no: The room number.
        current_unit: The current meter reading.
    """
    # This tool merely sets up the intent and returns a string indicating HITL is needed.
    # The actual execution happens in the HITL confirmation node in graph.py.
    return f"PENDING_CONFIRMATION: electricity_increase | {house_no} | {room_no} | {current_unit}"

@tool
def fill_rent(house_no: str, room_no: str, amount: float) -> str:
    """Record a rent payment from a tenant.
    Args:
        house_no: The house number.
        room_no: The room number.
        amount: The amount of rent paid.
    """
    tenant = get_tenant_by_room(house_no, room_no)
    if not tenant:
        return "Tenant not found."

    tenant_id = tenant["id"]
    current_balance = tenant.get("rent_balance", 0)
    new_balance = current_balance - amount

    update_tenant_balances(tenant_id, {"rent_balance": new_balance})
    log_transaction(tenant_id, "RENT_PAYMENT", amount, "Rent payment received")

    send_whatsapp_text(tenant["phone_number"], f"We have received your rent payment of Rs{amount}. Thank you!")
    return f"Rent payment of {amount} processed for House {house_no}, Room {room_no}."

@tool
def fill_electricity(house_no: str, room_no: str, amount: float) -> str:
    """Record an electricity payment from a tenant.
    Args:
        house_no: The house number.
        room_no: The room number.
        amount: The amount of electricity paid.
    """
    tenant = get_tenant_by_room(house_no, room_no)
    if not tenant:
        return "Tenant not found."

    tenant_id = tenant["id"]
    current_balance = tenant.get("electricity_balance", 0)
    new_balance = current_balance - amount

    update_tenant_balances(tenant_id, {"electricity_balance": new_balance})
    log_transaction(tenant_id, "ELEC_PAYMENT", amount, "Electricity payment received")

    send_whatsapp_text(tenant["phone_number"], f"Electricity payment of Rs{amount} received. Thank you!")
    return f"Electricity payment of {amount} processed for House {house_no}, Room {room_no}."

@tool
def remove_tenant(house_no: str, room_no: str) -> str:
    """Remove a tenant from the system. Requires HITL.
    Args:
        house_no: The house number.
        room_no: The room number.
    """
    # Requires HITL confirmation before archiving
    return f"PENDING_CONFIRMATION: remove_tenant | {house_no} | {room_no}"

