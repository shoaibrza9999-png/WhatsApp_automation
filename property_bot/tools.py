from langchain_core.tools import tool
from typing import Optional

@tool
def log_rent(house_no: str, room_no: str, amount: float, note: str = "") -> str:
    """Log a rent payment from a tenant.
    Args:
        house_no: The house number.
        room_no: The room number.
        amount: The amount of rent paid.
        note: Optional note about the transaction.
    """
    # The actual business logic (HITL, DB insert, messaging) will be intercepted by the LangGraph Node.
    # The tool definition here is just for the LLM to know the schema and output a ToolCall.
    return "PENDING_APPROVAL_RENT"

@tool
def updatemeter(house_no: str, room_no: str, current_reading: float, note: str = "") -> str:
    """Log a new electricity meter reading.
    Args:
        house_no: The house number.
        room_no: The room number.
        current_reading: The current meter reading.
        note: Optional note.
    """
    return "PENDING_APPROVAL_METER"

@tool
def logpowerbill(house_no: str, room_no: str, amount: float, note: str = "") -> str:
    """Log an electricity/power bill payment.
    Args:
        house_no: The house number.
        room_no: The room number.
        amount: The amount paid for electricity.
        note: Optional note.
    """
    return "PENDING_APPROVAL_POWER"

@tool
def deletetransection(txn_id: int) -> str:
    """Delete an existing transaction from the ledger.
    Args:
        txn_id: The ID of the transaction to delete.
    """
    return "PENDING_APPROVAL_DELETE"

@tool
def balance(house_no: str, room_no: str) -> str:
    """View specific room balance data.
    Args:
        house_no: The house number.
        room_no: The room number.
    """
    from db import get_tenant
    tenant = get_tenant(house_no, room_no)
    if not tenant:
        return "Tenant not found."

    data = (
        f"Due Rent: {tenant['pending_rent']}\n"
        f"Due Bill: {tenant['pending_electricity']}\n"
        f"Last Reading: {tenant['last_electricity_reading']}\n"
        f"Paid: {tenant['total_paid']}\n"
        f"Not Paid: {tenant['pending_rent'] + tenant['pending_electricity']}"
    )
    return data
