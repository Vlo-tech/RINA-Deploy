import os
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from supabase import create_client, Client

load_dotenv()

from .chat_service import get_bot_response
from .supabase_client import save_chat, _get_or_create, create_listing, save_trace_snapshot
from .tracing import start_trace, add_step, finish_trace

# Environment validation
FLASK_ENV = os.getenv("FLASK_ENV", "production").lower()
PRODUCTION = FLASK_ENV == "production"

# Validate required environment variables
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("RINA_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["http://localhost:3000"]

if not TWILIO_AUTH_TOKEN:
    print("Warning: TWILIO_AUTH_TOKEN not set - Twilio webhook validation disabled")
if not ADMIN_API_KEY:
    print("Warning: ADMIN_API_KEY not set - listing creation endpoint disabled")
if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("Warning: Supabase credentials not set - auth and other features may not work")

# Initialize validators and clients
validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else None

app = Flask(__name__)

# Allow frontend to access the /api/* routes (and health root) from configured origins
cors_resources = {
    r"/*": {
        "origins": ALLOWED_ORIGINS,
        "allow_headers": ["Content-Type", "Authorization"],
        "methods": ["GET", "POST", "OPTIONS", "PUT", "PATCH", "DELETE"],
        "max_age": 3600,
    }
}
CORS(app, resources=cors_resources, supports_credentials=True)

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "RINA webhook"}), 200

@app.route("/webhook", methods=["POST"])
def twilio_webhook():
    """Twilio WhatsApp sandbox integration endpoint"""
    if PRODUCTION and validator:
        sig = request.headers.get("X-Twilio-Signature", "")
        url = request.url
        params = request.form.to_dict()
        if not validator.validate(url, params, sig):
            return Response("Invalid signature", status=403)

    try:
        sender = request.values.get("From", "").strip().replace("whatsapp:", "")
        body = request.values.get("Body", "").strip()
        user_key = f"whatsapp:{sender.lstrip('+')}" or "anon"

        num_media = int(request.values.get("NumMedia", 0))
        if num_media > 0:
            # Placeholder for media handling
            pass

        reply = get_bot_response(body, user_id=user_key)
        save_chat(user_key, body, reply)

        twiml = MessagingResponse()
        twiml.message(reply)
        return Response(str(twiml), mimetype="text/xml")
    except Exception as e:
        app.logger.exception("Error in webhook")
        twiml = MessagingResponse()
        twiml.message("Sorry, something went wrong. Try again later.")
        return Response(str(twiml), mimetype="text/xml")

@app.route("/api/chat", methods=["POST"])
def chat_api():
    """API endpoint for the web chat frontend."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    jwt = auth_header.split(" ")[1]
    try:
        if not supabase:
            raise Exception("Supabase client not initialized")
        user_response = supabase.auth.get_user(jwt)
        user = user_response.user
        if not user:
            raise Exception("Invalid token")
        user_id = user.id
    except Exception as e:
        return jsonify({"error": f"Unauthorized: {e}"}), 401

    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "Invalid data"}), 400

    user_message = data["message"]

    try:
        # start trace (decompose goal)
        trace = start_trace(user_id=user_id, task="rent_search_or_portfolio", goal={"user_message": user_message})
        add_step(trace, {
            "step_no": 1,
            "step_type": "plan",
            "content": {
                "restated_goal": user_message,
                "substeps": [
                    "Classify intent (search/save/inquiry/fallback)",
                    "Call agent service to get response",
                    "Persist chat and trace",
                ]
            },
            "success": True
        })

        # act
        add_step(trace, {
            "step_no": 2,
            "step_type": "act",
            "content": {
                "tool": "chat_service.get_bot_response",
                "args": {"user_id": user_id, "message_excerpt": user_message[:120], "len": len(user_message)}
            },
            "success": True
        })

        bot_response = get_bot_response(user_message, user_id=user_id)

        # critique
        degraded_phrases = ["couldn't find", "trouble", "sorry", "try later"]
        ok = not any(p in bot_response.lower() for p in degraded_phrases)
        add_step(trace, {
            "step_no": 3,
            "step_type": "critique",
            "content": {
                "observation": bot_response[:200],
                "meets_goal": ok,
                "note": "Response contains apology/issue" if not ok else "Looks good"
            },
            "success": ok
        })

        # decision
        add_step(trace, {
            "step_no": 4,
            "step_type": "decision",
            "content": {
                "decision": "stop" if ok else "revise",
                "tradeoff": "Stop when response satisfies query; otherwise suggest broader search"
            },
            "success": True
        })

        # persist chat
        save_chat(user_id, user_message, bot_response)

        # outcome
        snapshot = finish_trace(trace, {"reply_preview": bot_response[:200]})
        save_trace_snapshot(snapshot)
        return jsonify({"reply": bot_response})
    except Exception as e:
        app.logger.exception("Error in chat API")
        return jsonify({"error": "Sorry, something went wrong."}), 500

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
    complex_data = data.get('complex')

    try:
        landlord_id = _get_or_create(
            'landlords',
            {'contact_number': f"eq.{landlord_data['contact_number']}"},
            landlord_data
        )

        complex_id = None
        if complex_data:
            complex_id = _get_or_create(
                'complexes',
                {'name': f"eq.{complex_data['name']}"},
                {**complex_data, 'landlord_id': landlord_id}
            )

        listing_data['landlord_id'] = landlord_id
        if complex_id:
            listing_data['complex_id'] = complex_id

        res = create_listing(listing_data)
        return jsonify({"message": "Listing created successfully", "listing": res}), 201

    except Exception as e:
        app.logger.exception("Error creating listing")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=not PRODUCTION)
