import os
import io
import asyncio
import re
import requests
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db import get_tenants_needing_reminders, update_tenant_balances, log_transaction, supabase
from graph import run_admin_agent
from whatsapp import send_whatsapp_text

load_dotenv()

ADMIN_NUMBER = os.environ.get("ADMIN_WHATSAPP_NUMBER", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "my_custom_verify_token")

scheduler = AsyncIOScheduler()

async def reminder_cron_job():
    """Runs daily to check if rent is due for active tenants."""
    print("Running daily cron job for rent charges...")
    today_date = datetime.now(timezone.utc).day

    tenants = get_tenants_needing_reminders(today_date)
    for t in tenants:
        tenant_id = t["id"]
        phone = t.get("phone_number")
        rent_amount = t.get("rent_amount", 0)
        current_balance = t.get("rent_balance", 0)

        # 1. Update rent balance
        new_balance = current_balance + rent_amount
        update_tenant_balances(tenant_id, {"rent_balance": new_balance})

        # 2. Insert transaction
        log_transaction(tenant_id, "RENT_CHARGE", rent_amount, "Monthly Rent")

        # 3. Send message
        msg = f"Monthly Rent reminder: Your rent of {rent_amount} has been generated."
        if phone:
            send_whatsapp_text(phone, msg)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup cron job on startup
    # Run daily at 00:00 UTC
    trigger = CronTrigger(hour="0", minute="0")
    scheduler.add_job(reminder_cron_job, trigger)
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "service": "Property Bot Active"}

@app.get("/webhook")
async def verify_webhook(request: Request):
    """WhatsApp webhook verification."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            return int(challenge)
        raise HTTPException(status_code=403, detail="Verification failed")
    raise HTTPException(status_code=400, detail="Missing parameters")

@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming WhatsApp messages."""
    data = await request.json()

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ignored"}

        message = messages[0]
        sender_id = message.get("from")
        msg_type = message.get("type")

        # 1. Check if it's the Owner
        # Normalize ADMIN_NUMBER
        admin_num = ADMIN_NUMBER.replace("+", "")
        if sender_id != admin_num:
            return {"status": "ignored"}

        if msg_type not in ["text", "interactive"]:
            return {"status": "ignored"}

        text = ""
        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
        elif msg_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive.get("button_reply", {}).get("id", "") # Assuming ID holds the answer like 'yes'

        thread_id = f"thread_{sender_id}"

        # Context Injection
        tenant_context = ""
        # Check if text mentions house and room
        house_match = re.search(r'house\s*(\S+)', text, re.IGNORECASE)
        room_match = re.search(r'room\s*(\S+)', text, re.IGNORECASE)

        if house_match and room_match:
            house_no = house_match.group(1)
            room_no = room_match.group(1)

            # Fetch tenant id
            try:
                house_resp = supabase.table("houses").select("id").eq("house_no", house_no).execute()
                if house_resp.data:
                    house_id = house_resp.data[0]["id"]
                    tenant_resp = supabase.table("tenants").select("id").eq("house_id", house_id).eq("room_no", room_no).execute()
                    if tenant_resp.data:
                        tenant_id = tenant_resp.data[0]["id"]

                        # Query transactions
                        txns_resp = supabase.table("transactions").select("created_at, transaction_type, amount, description").eq("tenant_id", tenant_id).order("created_at", desc=True).limit(20).execute()

                        if txns_resp.data:
                            tenant_context = f"### Recent Transactions for House {house_no}, Room {room_no}\n"
                            tenant_context += "| Date | Type | Amount | Description |\n"
                            tenant_context += "| :--- | :--- | :--- | :--- |\n"
                            for txn in txns_resp.data:
                                date = txn.get("created_at", "")[:10]
                                txn_type = txn.get("transaction_type", "")
                                amt = txn.get("amount", 0)
                                desc = txn.get("description", "")
                                tenant_context += f"| {date} | {txn_type} | {amt:.2f} | {desc} |\n"
            except Exception as e:
                print(f"Error injecting context: {e}")

        # Route to Admin Agent
        background_tasks.add_task(run_admin_agent, sender_id, text, thread_id, tenant_context)

        return {"status": "ok"}

    except Exception as e:
        print(f"Error handling webhook: {e}")
        return {"status": "error"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
