import json
import os
import time
import uuid
from typing import Any, Dict, List


TRACE_DIR = os.path.join(os.path.dirname(__file__), '..', 'traces')
TRACE_PATH = os.path.abspath(os.path.join(TRACE_DIR, 'traces.jsonl'))


def _ensure_dir():
    os.makedirs(TRACE_DIR, exist_ok=True)


def start_trace(user_id: str, task: str, goal: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_dir()
    trace = {
        "trace_id": str(uuid.uuid4()),
        "ts": int(time.time() * 1000),
        "actor": "ai",
        "user_id": user_id,
        "session_id": f"{user_id}-{int(time.time())}",
        "task": task,
        "goal": goal,
        "steps": [],
    }
    return trace


def add_step(trace: Dict[str, Any], step: Dict[str, Any]):
    trace.setdefault("steps", []).append(step)


def finish_trace(trace: Dict[str, Any], result: Dict[str, Any]):
    trace["result"] = result
    # append to local jsonl
    try:
        with open(TRACE_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return trace

