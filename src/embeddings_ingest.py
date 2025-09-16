
import os
import time
import json
from typing import List
from dotenv import load_dotenv
import requests
import openai

# local import of supabase_client module in repo
from . import supabase_client as sb

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

from openai import OpenAI
openai_client = OpenAI(api_key=OPENAI_API_KEY)

REST_URL = sb.REST_URL
HEADERS = sb.HEADERS
POST_HEADERS = sb.POST_HEADERS
REQUEST_TIMEOUT = getattr(sb, "REQUEST_TIMEOUT", 10.0)


def listing_text_for_embedding(listing: dict) -> str:
    # Compose a text blob from the listing to embed
    parts = []
    for k in ("title", "description", "location", "property_type", "furnishing", "utilities", "renovations"):
        val = listing.get(k)
        if val:
            parts.append(str(val))
    
    if listing.get('amenities'):
        parts.append(f"Amenities: {', '.join(listing.get('amenities'))}")

    # include price as token
    price = listing.get("price")
    if price:
        parts.append(f"Price: {price}")

    size_sqm = listing.get("size_sqm")
    if size_sqm:
        parts.append(f"Size: {size_sqm} sqm")

    return " | ".join(parts)[:16000]  # cap length


def compute_embedding(text: str, model: str = EMBEDDING_MODEL) -> List[float]:
    # Use OpenAI embeddings
    # model can be changed in env or param
    resp = openai_client.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def fetch_all_listings() -> list:
    url = f"{REST_URL}/listings"
    # optional: select specific fields
    params = {"select": "*"} 
    r = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
    sb._raise_for_resp(r)
    return r.json()


def upsert_embedding(listing_id: str, embedding: List[float]):
    url = f"{REST_URL}/listings_embeddings"
    body = {
        "listing_id": listing_id,
        # Supabase/postgREST accepts arrays for pgvector when JSON-encoded
        "embedding": embedding,
        "updated_at": "now()"
    }
    # Use on_conflict param to upsert by listing_id
    params = {"on_conflict": "listing_id"}
    r = requests.post(url, headers=POST_HEADERS, params=params, json=body, timeout=REQUEST_TIMEOUT)
    sb._raise_for_resp(r)
    return r.json()


def run_ingest(batch_wait: float = 0.35):
    print("Fetching listings...")
    listings = fetch_all_listings()
    print(f"Found {len(listings)} listings")
    for i, listing in enumerate(listings, start=1):
        lid = listing.get("id")
        if not lid:
            print("Skipping listing without id:", listing)
            continue
        text = listing_text_for_embedding(listing)
        try:
            emb = compute_embedding(text)
        except Exception as e:
            print("Embedding error for listing", lid, e)
            continue
        try:
            upsert_embedding(lid, emb)
            print(f"[{i}/{len(listings)}] Upserted embedding for {lid}")
        except Exception as e:
            print("Upsert error:", e)
        time.sleep(batch_wait)  # throttle to avoid token limits / rate limits


if __name__ == "__main__":
    run_ingest()