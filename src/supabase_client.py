import os
import requests
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SERVICE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment")

# Base REST endpoint for PostgREST
REST_URL = SUPABASE_URL.rstrip("/") + "/rest/v1"

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
POST_HEADERS = HEADERS.copy()
POST_HEADERS["Prefer"] = "return=representation"

REQUEST_TIMEOUT = 10.0


def _raise_for_resp(resp: requests.Response):
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        # include snippet of body for debugging
        text = resp.text.strip()
        raise RuntimeError(f"Supabase REST error {resp.status_code}: {text[:2000]}") from e


def _get_or_create(table: str, match_params: Dict[str, Any], create_params: Dict[str, Any]) -> str:
    """Generic function to get or create a record in a table."""
    q = {**match_params, "select": "id"}
    resp = requests.get(f"{REST_URL}/{table}", params=q, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    data = resp.json()
    if data and isinstance(data, list) and data:
        return data[0]["id"]

    # create record
    resp = requests.post(f"{REST_URL}/{table}", json=create_params, params={"select": "id"}, headers=POST_HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    data = resp.json()
    if isinstance(data, list) and data:
        return data[0]["id"]
    raise RuntimeError(f"Failed to create record in {table}")


def _get_or_create_user(phone_number: str) -> str:
    """Map a WhatsApp phone number to a Supabase users table id. Create if missing."""
    # Use an 'upsert' to avoid race conditions
    body = {"phone_number": phone_number}
    # Add 'on_conflict' to the query params to specify the unique column
    params = {"on_conflict": "phone_number", "select": "id"}
    # Change the headers to specify 'merge-duplicates'
    upsert_headers = POST_HEADERS.copy()
    upsert_headers["Prefer"] = "return=representation,resolution=merge-duplicates"

    resp = requests.post(f"{REST_URL}/users", json=body, params=params, headers=upsert_headers, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    data = resp.json()
    if isinstance(data, list) and data:
        return data[0]["id"]
    raise RuntimeError("Failed to get or create user")


def _get_or_create_landlord(user_phone: str) -> str:
    user_id = _get_or_create_user(user_phone)
    return _get_or_create("landlords", {"user_id": f"eq.{user_id}"}, {"user_id": user_id})


# Chat saving and retrieval
def save_chat(user_phone: str, user_message: str, bot_response: str) -> Optional[List[Dict[str, Any]]]:
    if user_phone == "anon":
        return None
    user_id = _get_or_create_user(user_phone)
    body = {
        "user_id": user_id,
        "user_message": user_message,
        "bot_response": bot_response,
    }
    resp = requests.post(f"{REST_URL}/chats", json=body, headers=POST_HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    try:
        return resp.json()
    except Exception:
        return None


def get_recent_chats(user_phone: str, limit: int = 10):
    if user_phone == "anon":
        return []
    user_id = _get_or_create_user(user_phone)
    resp = requests.get(
        f"{REST_URL}/chats",
        params={"user_id": f"eq.{user_id}", "select": "user_message,bot_response", "order": "created_at.asc", "limit": str(limit)},
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    _raise_for_resp(resp)
    rows = resp.json() or []
    history = []
    for row in rows:
        history.append({"role": "user", "content": row.get("user_message", "")})
        history.append({"role": "assistant", "content": row.get("bot_response", "")})
    return history


# Listings & search helpers
def create_listing(listing: Dict[str, Any]):
    resp = requests.post(f"{REST_URL}/listings", json=listing, headers=POST_HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    return resp.json()


def search_listings(location: Optional[str] = None, max_price: Optional[int] = None, room_type: Optional[str] = None):
    query = {"select": "*", "limit": "100"}
    if location:
        query["location"] = f"ilike.%{location}%"
    if max_price is not None:
        query["price"] = f"lte.{max_price}"
    if room_type:
        query["room_type"] = f"ilike.%{room_type}%"

    resp = requests.get(f"{REST_URL}/listings", params=query, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    return resp.json()


def get_complexes(user_phone: str):
    landlord_id = _get_or_create_landlord(user_phone)
    resp = requests.get(f"{REST_URL}/complexes", params={"landlord_id": f"eq.{landlord_id}"}, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    return resp.json()


def get_units(user_phone: str, complex_id: Optional[str] = None):
    landlord_id = _get_or_create_landlord(user_phone)
    query = {"select": "*,complexes!inner(landlord_id)", "complexes.landlord_id": f"eq.{landlord_id}"}
    if complex_id:
        query["complex_id"] = f"eq.{complex_id}"

    resp = requests.get(f"{REST_URL}/units", params=query, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    return resp.json()


def save_listing_to_favorites(user_phone: str, listing_id: str):
    user_app_id = _get_or_create_user(user_phone)
    body = {"user_id": user_app_id, "listing_id": listing_id}
    resp = requests.post(f"{REST_URL}/favorites", json=body, headers=POST_HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    return resp.json()


def create_inquiry(user_phone: str, listing_id: str, message: str):
    user_app_id = _get_or_create_user(user_phone)
    body = {
        "listing_id": listing_id,
        "user_id": user_app_id,
        "message": message
    }
    resp = requests.post(f"{REST_URL}/inquiries", json=body, headers=POST_HEADERS, timeout=REQUEST_TIMEOUT)
    _raise_for_resp(resp)
    return resp.json()


# Frontier data traces
def save_trace_snapshot(snapshot: Dict[str, Any]):
    """Persist a full agent trace snapshot to Supabase if a table exists.
    Expects a table named 'agent_traces' with columns: id (uuid), payload (jsonb), created_at (timestamptz).
    """
    try:
        body = {"payload": snapshot}
        resp = requests.post(f"{REST_URL}/agent_traces", json=body, headers=POST_HEADERS, timeout=REQUEST_TIMEOUT)
        # allow 404 if table doesn't exist
        if resp.status_code == 404:
            return None
        _raise_for_resp(resp)
        return resp.json()
    except Exception:
        # swallow errors so chat flow never breaks
        return None

