import os
import io
import asyncio
import requests
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db import get_tenant_by_phone, get_tenants_needing_reminders
from commands import handle_command
from graph import run_admin_agent, run_tenant_agent
from hf_client import process_audio, process_image
from whatsapp import send_whatsapp_text

load_dotenv()

ADMIN_NUMBER = os.environ.get("ADMIN_WHATSAPP_NUMBER", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "my_custom_verify_token")

# Setup Scheduler for Cron Jobs
scheduler = AsyncIOScheduler()

async def reminder_cron_job():
    """Runs on the 5th of every month at 10:00 AM IST to send rent reminders."""
    print("Running monthly reminder cron job...")
    tenants = get_tenants_needing_reminders()
    for t in tenants:
        phone = t.get("phone_number")
        name = t.get("name")
        rent = t.get("rooms", {}).get("base_rent", "Unknown")

        msg = f"Hello {name}, this is a gentle reminder that your rent for this month (Base: {rent}) is due. Please clear the dues at your earliest convenience."
        if phone:
            send_whatsapp_text(phone, msg)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup cron job on startup
    # 10:00 AM IST is 04:30 AM UTC
    trigger = CronTrigger(day="5", hour="4", minute="30")
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
        # Extract message data from standard WhatsApp webhook payload
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ignored"}

        message = messages[0]
        sender_id = message.get("from")
        msg_type = message.get("type")

        if msg_type not in ["text", "audio", "image"]:
            return {"status": "ignored"}

        # Determine text content based on message type
        text = ""
        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
        elif msg_type == "audio":
            # In real implementation: download media using media_id, pass to HF Whisper
            # media_id = message.get("audio", {}).get("id")
            # audio_bytes = download_whatsapp_media(media_id)
            # text = await process_audio(audio_bytes)
            text = "Simulated transcribed audio text"
        elif msg_type == "image":
            # media_id = message.get("image", {}).get("id")
            # image_bytes = download_whatsapp_media(media_id)
            # caption = message.get("image", {}).get("caption", "Extract details")
            # text = await process_image(image_bytes, caption)
            text = "Simulated extracted image text"

        # 1. Routing: Check if Hardcoded Command
        if handle_command(sender_id, text):
            return {"status": "ok"}

        # Thread ID for memory (one per user)
        thread_id = f"thread_{sender_id}"

        # 2. Routing: Role-Based Access Control
        if sender_id == ADMIN_NUMBER or sender_id == ADMIN_NUMBER.replace("+", ""):
            # Route to Admin Agent
            background_tasks.add_task(run_admin_agent, sender_id, text, thread_id)
        else:
            # Route to Tenant Agent
            tenant = get_tenant_by_phone(sender_id)
            if tenant:
                tenant_id = tenant["tenant_id"]
                background_tasks.add_task(run_tenant_agent, sender_id, tenant_id, text, thread_id)
            else:
                # Unknown user
                send_whatsapp_text(sender_id, "Sorry, I don't recognize this number. Please contact the administrator.")

        return {"status": "ok"}

    except Exception as e:
        print(f"Error handling webhook: {e}")
        return {"status": "error"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
