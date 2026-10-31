"""Device API. Run separately from the Streamlit app:

    uvicorn api:app --host 0.0.0.0 --port 8000

Every device request must send  X-Device-ID  and  X-API-Key  headers.
"""
import time
from contextlib import asynccontextmanager
from collections import defaultdict, deque

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

import env_loader  # noqa: F401  (must come first)
import devices
from db import db, init_db


class RateLimiter:
    def __init__(self, limit, window):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def allow(self, key):
        now, q = time.monotonic(), self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


device_limiter = RateLimiter(limit=120, window=60)      # per device per minute
failed_limiter = RateLimiter(limit=20, window=60)       # bad credentials per client per minute


def reply(data, status=200):
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})


def authed(handler):
    async def wrapper(request):
        client = request.client.host if request.client else "?"
        did = request.headers.get("x-device-id", "")
        key = request.headers.get("x-api-key", "")
        if not failed_limiter.allow("probe:" + client) and not did:
            return reply({"error": "too_many_requests"}, 429)
        with db() as c:
            dev = devices.authenticate(c, did, key)
            if dev is None:
                if not failed_limiter.allow("fail:" + client):
                    return reply({"error": "too_many_requests"}, 429)
                return reply({"error": "unauthorized"}, 401)
            if not device_limiter.allow(did):
                return reply({"error": "too_many_requests"}, 429)
            return await handler(request, c, dev)
    return wrapper


async def _json(request):
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@authed
async def heartbeat(request, c, dev):
    body = await _json(request)
    rssi = body.get("rssi")
    rssi = rssi if isinstance(rssi, int) and -150 <= rssi <= 0 else None
    devices.touch(c, dev, rssi=rssi, heartbeat=True)
    devices.sweep(c)
    return reply({"ok": True})


@authed
async def latest(request, c, dev):
    devices.touch(c, dev)
    msg = devices.next_message(c, dev)
    return reply({"message": msg})


@authed
async def acknowledge(request, c, dev):
    body = await _json(request)
    mid = body.get("message_id")
    if not isinstance(mid, str) or not (1 <= len(mid) <= 40):
        return reply({"error": "bad_request"}, 400)
    displayed = body.get("displayed", True)
    if not isinstance(displayed, bool):
        return reply({"error": "bad_request"}, 400)
    devices.touch(c, dev)
    if not devices.acknowledge(c, dev, mid, displayed):
        return reply({"error": "unknown_message"}, 404)
    return reply({"ok": True})


async def health(request):
    return reply({"status": "ok"})


@asynccontextmanager
async def lifespan(app):
    init_db()
    import db as _db
    print("TruthSync API using database:", _db.DB_PATH, flush=True)
    yield


app = Starlette(lifespan=lifespan, routes=[
    Route("/api/health", health, methods=["GET"]),
    Route("/api/device/heartbeat", heartbeat, methods=["POST"]),
    Route("/api/device/messages/latest", latest, methods=["GET"]),
    Route("/api/device/messages/acknowledge", acknowledge, methods=["POST"]),
])
