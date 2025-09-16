
import os
import math
import numpy as np
from typing import List, Dict
from dotenv import load_dotenv
import requests
from openai import OpenAI

from . import supabase_client as sb

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY missing")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

openai_client = OpenAI(api_key=OPENAI_API_KEY)

REST_URL = sb.REST_URL
HEADERS = sb.HEADERS
REQUEST_TIMEOUT = getattr(sb, "REQUEST_TIMEOUT", 10.0)


def embed_text(text: str, model: str = EMBEDDING_MODEL) -> List[float]:
    resp = openai_client.embeddings.create(model=model, input=text)
    return resp.data[0].embedding


def retrieve_listings(query: str, top_k: int = 5) -> List[Dict]:
    """
    Returns top_k listing dicts sorted by similarity desc using pgvector.
    """
    print("Embedding query for retrieval...")
    query_embedding = embed_text(query)

    print("Calling Supabase vector search...")
    url = f"{REST_URL}/rpc/match_listings"
    body = {
        "query_embedding": query_embedding,
        "match_threshold": 0.5,
        "match_count": top_k,
    }
    r = requests.post(url, headers=HEADERS, json=body, timeout=REQUEST_TIMEOUT)
    sb._raise_for_resp(r)
    return r.json()