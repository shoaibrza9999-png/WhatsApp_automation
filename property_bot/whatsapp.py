import os
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
GRAPH_API_VERSION = "v22.0"

def send_whatsapp_text(recipient_number: str, text: str) -> bool:
    """Send a plain text message via WhatsApp."""
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_number,
        "type": "text",
        "text": {
            "body": text
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return True
        else:
            print(f"Error sending WhatsApp message: {response.json()}")
            return False
    except Exception as e:
        print(f"Exception sending WhatsApp message: {e}")
        return False

def send_whatsapp_interactive(recipient_number: str, header_text: str, body_text: str, footer_text: str, buttons: list) -> bool:
    """
    Send an interactive button message.
    buttons = [{"id": "btn_yes", "title": "Yes"}, ...] (Max 3 buttons, title max 20 chars)
    """
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    action_buttons = []
    for btn in buttons:
        action_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn["id"],
                "title": btn["title"]
            }
        })

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "header": {
                "type": "text",
                "text": header_text
            } if header_text else None,
            "body": {
                "text": body_text
            },
            "footer": {
                "text": footer_text
            } if footer_text else None,
            "action": {
                "buttons": action_buttons
            }
        }
    }

    # Remove None keys
    if not payload["interactive"]["header"]:
        del payload["interactive"]["header"]
    if not payload["interactive"]["footer"]:
        del payload["interactive"]["footer"]

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return True
        else:
            print(f"Error sending WhatsApp interactive message: {response.json()}")
            return False
    except Exception as e:
        print(f"Exception sending WhatsApp interactive message: {e}")
        return False
