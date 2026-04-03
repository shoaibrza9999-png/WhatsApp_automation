from langchain_core.tools import tool
from typing import Optional
from db import log_transaction, edit_transaction, get_global_history, get_tenant_ledger

@tool
def LogRent(tenant_id: int, amount: float, note: str = "") -> str:
    """Log a rent payment from a tenant. Returns a transaction ID.
    Args:
        tenant_id: The ID of the tenant.
        amount: The amount of rent paid.
        note: Optional note about the transaction.
    """
    txn = log_transaction(tenant_id, "rent", amount, note)
    if txn:
        return f"Logged rent payment. Transaction ID: {txn.get('txn_id')}. Awaiting approval."
    return "Failed to log rent payment."

@tool
def LogPowerBill(tenant_id: int, amount: float, note: str = "") -> str:
    """Log an electricity/power bill payment.
    Args:
        tenant_id: The ID of the tenant.
        amount: The amount paid for electricity.
        note: Optional note.
    """
    txn = log_transaction(tenant_id, "electricity", amount, note)
    if txn:
        return f"Logged power bill payment. Transaction ID: {txn.get('txn_id')}. Awaiting approval."
    return "Failed to log power bill payment."

@tool
def UpdateMeter(tenant_id: int, reading: float, note: str = "") -> str:
    """Log a new electricity meter reading.
    Args:
        tenant_id: The ID of the tenant.
        reading: The current meter reading.
        note: Optional note.
    """
    txn = log_transaction(tenant_id, "meter_reading", reading, note)
    if txn:
        return f"Logged meter reading. Transaction ID: {txn.get('txn_id')}. Awaiting approval."
    return "Failed to log meter reading."

@tool
def EditTxn(txn_id: int, new_amount: Optional[float] = None, new_note: Optional[str] = None) -> str:
    """Edit an existing pending transaction.
    Args:
        txn_id: The ID of the transaction to edit.
        new_amount: The new amount.
        new_note: The new note.
    """
    updates = {}
    if new_amount is not None:
        updates["amount"] = new_amount
    if new_note is not None:
        updates["note"] = new_note

    if not updates:
        return "No updates provided."

    success = edit_transaction(txn_id, updates)
    if success:
        return f"Transaction {txn_id} updated successfully."
    return f"Failed to update transaction {txn_id}."

@tool
def GetGlobalHistory() -> str:
    """Fetch the last 15 system-wide transactions with timestamps in IST. Useful for checking recent payments."""
    history = get_global_history(15)
    if not history:
        return "No recent transactions found."

    result = []
    for h in history:
        tenant_name = h.get("tenants", {}).get("name", "Unknown")
        room_id = h.get("tenants", {}).get("room", {}).get("room_id", "Unknown")
        ts = h.get("timestamp")
        # Could parse and format to IST, keeping raw for now
        result.append(f"Txn {h.get('txn_id')}: {h.get('type')} of {h.get('amount')} by {tenant_name} (Room {room_id}) on {ts} [{h.get('status')}]")

    return "\n".join(result)

@tool
def GetMyLedger(tenant_id: int) -> str:
    """Fetch the last 7-8 transactions for the requesting tenant. Use this to explain their balance."""
    ledger = get_tenant_ledger(tenant_id, 8)
    if not ledger:
        return "No transactions found for your account."

    result = []
    for h in ledger:
        ts = h.get("timestamp")
        result.append(f"Txn {h.get('txn_id')}: {h.get('type')} of {h.get('amount')} on {ts} [{h.get('status')}]")

    return "\n".join(result)
