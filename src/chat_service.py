import os
import json
import re
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

from openai import OpenAI

from .intent_classifier import IntentClassifier
from .lang_detect import detect_language
from .retrieval import retrieve_listings
from . import supabase_client as sb

# set OpenAI key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is required")

OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=15.0)

# instantiate classifier (loads model if present)
INTENT = IntentClassifier()

# small helper to format listing nicely for WhatsApp/Chat
def format_listing_msg(listing: Dict) -> str:
    lines = []
    lines.append(f"🏠 {listing.get('title','(no title)')}")
    loc = listing.get('location')
    if loc:
        lines.append(f"📍 {loc}")
    price = listing.get('price')
    if price:
        lines.append(f"💰 KES {price}")
    rt = listing.get('room_type')
    if rt:
        lines.append(f"🛏 {rt}")
    contact = listing.get('landlord_contact') or listing.get('contact_number') or "No contact"
    lines.append(f"📞 {contact}")
    # add id so users can save it
    lines.append(f"🔖 ID: {listing.get('id')}")
    return "\n".join(lines)


def save_chat(user_phone: str, user_message: str, bot_response: str):
    try:
        return sb.save_chat(user_phone, user_message, bot_response)
    except Exception as e:
        print("Warning: save_chat failed:", e)
        return None


def _handle_search(user_input: str, user_id: str, lang: str) -> str:
    # Use retrieval pipeline
    try:
        results = retrieve_listings(user_input, top_k=5)
    except Exception as e:
        print("Retrieval error:", e)
        results = []

    if not results:
        if lang == 'sw' or lang == 'sheng':
            return "😔 Samahani, sina matoleo yanayolingana kwa sasa. Je, nitafute eneo pana zaidi au nikujulishe kitu kikitokea?"
        else:
            return "😔 Sorry, I couldn't find any matching listings right now. Can I broaden the search or notify you when something appears?"

    # Build response listing top 3
    pieces = []
    if lang == 'sw' or lang == 'sheng':
        pieces.append("Hapa kuna baadhi ya matoleo niliyopata:")
    else:
        pieces.append("Here are some of the listings I found:")

    for r in results[:3]:
        pieces.append(format_listing_msg(r))
    
    if lang == 'sw' or lang == 'sheng':
        pieces.append("\nJibu 'save <ID>' kuhifadhi listing, au 'zaidi' kuona zaidi.")
    else:
        pieces.append("\nReply with 'save <ID>' to save a listing, or 'more' to see more options.")
        
    return "\n\n".join(pieces)


def _handle_save_listing(user_input: str, user_phone: str) -> str:
    # expect user to write: "save <id>" or "save listing <id>"
    m = re.search(r"([0-9a-fA-F\-]{8,})", user_input)
    if not m:
        return "I couldn't find a listing ID in your message. Reply with 'save <LISTING_ID>'."
    listing_id = m.group(1)
    try:
        sb.save_listing_to_favorites(user_phone, listing_id)
        return f"✅ Saved listing {listing_id} to your favorites."
    except Exception as e:
        print("Save listing error:", e)
        return "Sorry, I couldn't save that listing right now. Please try later."

def _handle_inquiry(user_input: str, user_phone: str) -> str:
    # simplistic extraction of listing id + a short message
    m = re.search(r"([0-9a-fA-F\-]{8,})", user_input)
    if not m:
        return "Please include the listing ID you want to inquire about (reply with the ID)."
    listing_id = m.group(1)
    # optional message is everything after the id
    parts = user_input.split(listing_id, 1)
    message = parts[1].strip() if len(parts) > 1 else "Hi, I am interested in this listing. Please contact me."
    try:
        sb.create_inquiry(user_phone, listing_id, message)
        return f"✅ Your inquiry for listing {listing_id} has been submitted. The landlord will get back to you."
    except Exception as e:
        print("Inquiry error:", e)
        return "Sorry, I couldn't create the inquiry right now. Try again later."

def get_bot_response(user_input: str, user_id: str = "anon") -> str:
    """
    Primary interface used by webhook handler.
    user_id here is a phone number string (Twilio format) e.g. 'whatsapp:+2547...'
    """
    if not user_input or not user_input.strip():
        return "Hi — how can I help you find housing today?"

    # language detection
    try:
        lang = detect_language(user_input)
    except Exception as e:
        print(f"Warning: Language detection failed: {e}")
        lang = "en"  # fallback to English
    # obtain intent
    try:
        intent, conf = INTENT.predict(user_input)
    except Exception as e:
        print("Intent classifier error:", e)
        intent, conf = "fallback", 0.0

    print(f"Detected intent={intent} conf={conf} lang={lang}")

    # handle core intents
    if intent == "search_listings" or (intent == "fallback" and ("rent" in user_input.lower() or "bedsitter" in user_input.lower() or "room" in user_input.lower())):
        reply = _handle_search(user_input, user_id, lang)
    elif intent == "save_listing" or user_input.lower().startswith("save "):
        reply = _handle_save_listing(user_input, user_id)
    elif intent == "create_inquiry" or user_input.lower().startswith("inquire") or "book viewing" in user_input.lower():
        reply = _handle_inquiry(user_input, user_id)
    elif intent == "greeting":
        if lang == "sw" or lang == "sheng":
            reply = "Habari! Ninaweza kukusaidia kutafuta nyumba au kupeleka ujumbe kwa mwenye nyumba. Unaambiwa nini?"
        else:
            reply = "Hi! I can help you find student housing — tell me the area, budget, and room type."
    else:
        # fallback LLM answer (short)
        prompt = f"You are RINA, a Kenyan student housing assistant. The user said: '{user_input}'. Give a concise helpful reply in the user's language ({lang})."
        try:
            resp = openai_client.chat.completions.create(
                model=OPENAI_MODEL_NAME,
                messages=[{"role":"system","content":"You are RINA, a helpful assistant for student housing in Nairobi."},
                          {"role":"user","content":prompt}],
                max_tokens=250,
                temperature=0.7
            )
            reply = resp.choices[0].message.content.strip()
        except Exception as e:
            print("LLM fallback error:", e)
            reply = "Sorry, I'm having trouble right now. Can I help you find a room or save a listing?"

    # save final bot response to DB (update previous saved chat)
    try:
        save_chat(user_id, user_input, reply)
    except Exception as e:
        print(f"Warning: Failed to save chat for user {user_id}: {e}")
        # Continue functioning even if chat saving fails

    return reply