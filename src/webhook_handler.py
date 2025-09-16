import os
import requests
from flask import Flask, request, Response, jsonify
from dotenv import load_dotenv
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

load_dotenv()

from .chat_service import get_bot_response
from .supabase_client import save_chat, _get_or_create, create_listing

# Environment validation
FLASK_ENV = os.getenv("FLASK_ENV", "production").lower()
PRODUCTION = FLASK_ENV == "production"

# Validate required environment variables
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

if not TWILIO_AUTH_TOKEN:
    print("Warning: TWILIO_AUTH_TOKEN not set - Twilio webhook validation disabled")
if not META_VERIFY_TOKEN:
    print("Warning: META_VERIFY_TOKEN not set - Meta webhook validation disabled")
if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
    print("Warning: WhatsApp credentials not set - Cloud API will not work")
if not ADMIN_API_KEY:
    print("Warning: ADMIN_API_KEY not set - listing creation endpoint disabled")


# Initialize validators only if tokens exist
validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None
META_API_VERSION = os.getenv("META_API_VERSION", "v20.0")
CLOUD_API_BASE = f"https://graph.facebook.com/{META_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}" if WHATSAPP_PHONE_NUMBER_ID else ""

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return "RINA webhook OK", 200


@app.route("/webhook", methods=["POST"])
def twilio_webhook():
    """Twilio WhatsApp sandbox integration endpoint"""
    if PRODUCTION and validator:
        # verify Twilio signature
        sig = request.headers.get("X-Twilio-Signature", "")
        url = request.url
        params = request.form.to_dict()
        if not validator.validate(url, params, sig):
            return Response("Invalid signature", status=403)

    try:
        sender = request.values.get("From", "").strip().replace("whatsapp:", "")
        body = request.values.get("Body", "").strip()
        # Normalize sender (Twilio uses "whatsapp:+254...")
        user_key = f"whatsapp:{sender.lstrip('+')}" or "anon"

        # handle media with simple pass-through (not transcribing here)
        num_media = int(request.values.get("NumMedia", 0))
        if num_media > 0:
            media_url = request.values.get("MediaUrl0")
            media_type = request.values.get("MediaContentType0")
            if media_url and 'audio' in media_type:
                # TODO: Implement audio transcription here
                # 1. Download the audio file from media_url
                # 2. Transcribe the audio using OpenAI Whisper
                # 3. Update 'body' with the transcribed text
                pass

        reply = get_bot_response(body, user_id=user_key)
        # save to supabase
        try:
            save_chat(user_key, body, reply)
        except Exception:
            # Log but do not block response
            app.logger.exception("Failed to save chat")

        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), mimetype="text/xml")
    except Exception as e:
        app.logger.exception("Error in webhook")
        twiml = MessagingResponse()
        twiml.message("Sorry, something went wrong. Try again later.")
        return Response(str(twiml), mimetype="text/xml")


@app.route("/whatsapp_cloud", methods=["GET", "POST"])
def whatsapp_cloud():
    """Meta WhatsApp Cloud integration endpoint"""
    if request.method == "GET":
        challenge = request.args.get("hub.challenge")
        token = request.args.get("hub.verify_token")
        if token == META_VERIFY_TOKEN:
            return challenge, 200
        return "Forbidden", 403

    try:
        data = request.get_json(force=True)
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    from_num = msg.get("from")
                    text = msg.get("text", {}).get("body", "").strip()
                    if not from_num or not text:
                        continue
                    user_key = f"whatsapp:{from_num}"
                    reply = get_bot_response(text, user_id=user_key)
                    try:
                        save_chat(user_key, text, reply)
                    except Exception:
                        app.logger.exception("Failed to save chat")
                    # reply via cloud API
                    resp = requests.post(
                        f"{CLOUD_API_BASE}/messages",
                        headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
                        json={
                            "messaging_product": "whatsapp",
                            "to": from_num,
                            "type": "text",
                            "text": {"body": reply}
                        },
                        timeout=10.0
                    )
                    if resp.status_code not in (200, 201):
                        app.logger.warning("Cloud API error: %s %s", resp.status_code, resp.text)
        return "OK", 200
    except Exception:
        app.logger.exception("Error in whatsapp_cloud handler")
        return "Error", 500

@app.route("/listings", methods=["POST"])
def add_listing():
    """A secure endpoint to add a new listing."""
    if not ADMIN_API_KEY:
        return jsonify({"error": "API key not configured"}), 500

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    provided_key = auth_header.split(" ")[1]
    if provided_key != ADMIN_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data or "landlord" not in data or "listing" not in data:
        return jsonify({"error": "Invalid data"}), 400

    landlord_data = data['landlord']
    listing_data = data['listing']
    complex_data = data.get('complex') # complex is optional

    try:
        # Create or get landlord
        landlord_id = _get_or_create(
            'landlords',
            {'contact_number': f"eq.{landlord_data['contact_number']}"},
            landlord_data
        )

        # Create or get complex
        complex_id = None
        if complex_data:
            complex_id = _get_or_create(
                'complexes',
                {'name': f"eq.{complex_data['name']}"},
                {**complex_data, 'landlord_id': landlord_id}
            )

        # Create listing
        listing_data['landlord_id'] = landlord_id
        if complex_id:
            listing_data['complex_id'] = complex_id

        res = create_listing(listing_data)
        return jsonify({"message": "Listing created successfully", "listing": res}), 201

    except Exception as e:
        app.logger.exception("Error creating listing")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # debug mode when not production
    app.run(host="0.0.0.0", port=5000, debug=not PRODUCTION)