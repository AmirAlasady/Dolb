import requests
import json
import logging

# Configure logger for this tool
logger = logging.getLogger(__name__)

def send_whatsapp_message(to: str, message: str) -> dict:
    """
    Sends a WhatsApp message using the Meta Graph API.
    
    Args:
        to: The recipient's phone number in E.164 format (e.g., "+1234567890").
        message: The text content of the message.
        
    Returns:
        A dictionary containing the API response or an error message.
    """
    # These should ideally be set in your MS7 .env file
    # For now, we use placeholders. Replace with your actual credentials.
    ACCESS_TOKEN = "YOUR_WHATSAPP_ACCESS_TOKEN"
    PHONE_NUMBER_ID = "YOUR_WHATSAPP_PHONE_NUMBER_ID"
    VERSION = "v17.0"
    
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Normalize phone number (strip '+' if present, as Meta expects digits only)
    clean_to = to.lstrip('+')
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message
        }
    }
    
    logger.info(f"EXECUTING WHATSAPP TOOL: Sending message to '{clean_to}'")
    
    if ACCESS_TOKEN == "YOUR_WHATSAPP_ACCESS_TOKEN":
        logger.warning("WhatsApp tool is called but no ACCESS_TOKEN is configured.")
        return {"error": "WhatsApp service is not configured. Please set the ACCESS_TOKEN."}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        logger.info(f"SUCCESS: WhatsApp message sent to {clean_to}. Message ID: {data.get('messages', [{}])[0].get('id')}")
        return {
            "status": "success",
            "message_id": data.get('messages', [{}])[0].get('id'),
            "recipient": clean_to
        }

    except requests.exceptions.HTTPError as e:
        error_data = e.response.json() if e.response else {}
        error_msg = error_data.get('error', {}).get('message', str(e))
        logger.error(f"WhatsApp API Error: {error_msg}")
        return {"error": f"WhatsApp API error: {error_msg}"}
    except Exception as e:
        logger.error(f"Unexpected error in WhatsApp tool: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}"}
