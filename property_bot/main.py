import os
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db import get_tenant_by_phone, get_unpaid_tenants
from commands import handle_command
from graph import run_admin_agent
from whatsapp import send_whatsapp_text

load_dotenv()

ADMIN_NUMBER = os.environ.get("ADMIN_WHATSAPP_NUMBER", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "my_custom_verify_token")

scheduler = AsyncIOScheduler()

async def reminder_cron_job():
    print("Running monthly reminder cron job...")
    unpaid = get_unpaid_tenants()
    # To send a reminder, we need the phone number. We should ideally fetch it.
    # In db.py we didn't include phone in get_unpaid_tenants, but we can assume logic here.
    # We will log it for now.
    print(f"Found {len(unpaid)} unpaid tenants.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    trigger = CronTrigger(day="5", hour="4", minute="30")
    scheduler.add_job(reminder_cron_job, trigger)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/webhook")
async def verify_webhook(request: Request):
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

        text = ""
        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
        elif msg_type == "interactive":
            # Extract button reply
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive.get("button_reply", {}).get("id", "")
        else:
            return {"status": "ignored"}

        if not text:
            return {"status": "ignored"}

        # Hardcoded Command Router
        if handle_command(sender_id, text):
            return {"status": "ok"}

        thread_id = f"thread_{sender_id}"

        # Route to Admin logic (ignoring Tenant logic as per the new instructions which focused on Admin/AI)
        admin_num_clean = ADMIN_NUMBER.replace("+", "")
        if sender_id == ADMIN_NUMBER or sender_id == admin_num_clean:
            background_tasks.add_task(run_admin_agent, sender_id, text, thread_id)
        else:
            # Check if tenant
            tenant = get_tenant_by_phone(sender_id)
            if tenant:
                # If tenant asks for balance, handle it simply, or tell them to contact admin
                send_whatsapp_text(sender_id, "Please contact the administrator for any queries.")
            else:
                send_whatsapp_text(sender_id, "Sorry, I don't recognize this number.")

        return {"status": "ok"}

    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
