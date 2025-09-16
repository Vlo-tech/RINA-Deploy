import os
import time
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Connect to Redis
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping()
    print("Connected to Redis.")
except redis.exceptions.ConnectionError as e:
    print(f"Could not connect to Redis: {e}. Rate limiting will not work.")
    redis_client = None

# allow N requests per window seconds
DEFAULT_MAX = 6
DEFAULT_WINDOW = 15  # seconds

def allow_request(user_id: str, max_requests: int = DEFAULT_MAX, window_seconds: int = DEFAULT_WINDOW) -> bool:
    if not redis_client:
        return True # Fail open if Redis is not available

    key = f"ratelimit:{user_id}"
    
    # Use a transaction to ensure atomicity
    with redis_client.pipeline() as pipe:
        try:
            pipe.multi()
            pipe.incr(key, 1)
            pipe.expire(key, window_seconds)
            requests = pipe.execute()[0]

            if requests <= max_requests:
                return True
        except redis.exceptions.RedisError as e:
            print(f"Redis error in allow_request: {e}")
            return True # Fail open on Redis error

    return False

def time_until_reset(user_id: str) -> float:
    if not redis_client:
        return 0.0

    key = f"ratelimit:{user_id}"
    try:
        ttl = redis_client.ttl(key)
        return float(ttl) if ttl > 0 else 0.0
    except redis.exceptions.RedisError as e:
        print(f"Redis error in time_until_reset: {e}")
        return 0.0