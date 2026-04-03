import os
import requests
import asyncio
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.environ.get("HF_TOKEN", "")

# Assume these are the URLs for the endpoints or spaces
WHISPER_URL = os.environ.get("HF_WHISPER_URL", "https://api-inference.huggingface.co/models/openai/whisper-large-v3-turbo")
LLAMA_SCOUT_URL = os.environ.get("HF_LLAMA_SCOUT_URL", "https://api-inference.huggingface.co/models/meta-llama/Llama-3.2-11B-Vision-Instruct")
MANIM_WORKER_URL = os.environ.get("HF_MANIM_WORKER_URL", "")

headers = {"Authorization": f"Bearer {HF_TOKEN}"}

async def process_audio(audio_bytes: bytes) -> str:
    """Send audio to Whisper-large-v3-turbo for transcription (Hindi/Hinglish/English)."""
    try:
        response = await asyncio.to_thread(
            requests.post,
            WHISPER_URL,
            headers=headers,
            data=audio_bytes
        )
        if response.status_code == 200:
            result = response.json()
            return result.get("text", "")
        else:
            print(f"Whisper Error: {response.text}")
            return ""
    except Exception as e:
        print(f"Exception processing audio: {e}")
        return ""

async def process_image(image_bytes: bytes, prompt: str = "Extract the details from this image.") -> str:
    """Send image to Llama-Scout for OCR and receipt extraction."""
    # Llama Vision typically requires specific payload structure for images
    # We'll use a placeholder implementation based on standard HF Inference API
    import base64
    b64_image = base64.b64encode(image_bytes).decode('utf-8')

    payload = {
        "inputs": prompt,
        "parameters": {
            "image": b64_image
        }
    }

    try:
        response = await asyncio.to_thread(
            requests.post,
            LLAMA_SCOUT_URL,
            headers=headers,
            json=payload
        )
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0].get("generated_text", "")
            return str(result)
        else:
            print(f"Vision Error: {response.text}")
            return ""
    except Exception as e:
        print(f"Exception processing image: {e}")
        return ""

async def trigger_video_generation(transaction_data: dict) -> bool:
    """Send a POST request to the custom Hugging Face Manim worker."""
    if not MANIM_WORKER_URL:
        print("MANIM_WORKER_URL not configured.")
        return False

    try:
        response = await asyncio.to_thread(
            requests.post,
            MANIM_WORKER_URL,
            headers=headers,
            json={"transaction": transaction_data}
        )
        if response.status_code == 200:
            return True
        else:
            print(f"Manim Worker Error: {response.text}")
            return False
    except Exception as e:
        print(f"Exception triggering video: {e}")
        return False
