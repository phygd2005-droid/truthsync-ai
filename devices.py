"""Device registration, authentication and the message-delivery state machine.

Delivery status:  pending -> sent -> displayed   (displayed ONLY after the ESP32 confirms)
                                  \\-> failed (too many attempts / device reported an error)
                  pending|sent -> expired (not confirmed before expires_at)
"""
import json
import re
import secrets
import textwrap
from datetime import datetime, timedelta, timezone

from db import TS_FMT, _local_tz, audit, notify, now, seconds_since
from security import check_key, hash_token, new_device_credentials

ONLINE_SECONDS = 45          # no contact for this long -> offline
MESSAGE_TTL_MINUTES = 30
MAX_ATTEMPTS = 5
REDELIVER_AFTER = 20         # seconds to wait for an acknowledgement before sending again
OLED_COLS = 21               # SSD1306 128x64, text size 1


# ------------------------------------------------------------------ registration
def register_device(c, user_id, name, device_type):
    name = re.sub(r"\s+", " ", name or "").strip()[:40]
    if not name:
        raise ValueError("Please give the device a name.")
    device_id, api_key, key_hash = new_device_credentials()
    first = c.execute("SELECT COUNT(*) FROM devices WHERE user_id=? AND revoked=0",
                      (user_id,)).fetchone()[0] == 0
    c.execute("INSERT INTO devices(user_id, device_id, name, device_type, key_hash, is_default,"
              " created_at) VALUES (?,?,?,?,?,?,?)",
              (user_id, device_id, name, device_type, key_hash, 1 if first else 0, now()))
    audit(c, user_id, "device_registered", device_id)
    return device_id, api_key


def authenticate(c, device_id, api_key):
    """Returns the device row, or None for unknown / wrong key / revoked (same answer for all)."""
    if not device_id or not api_key or len(device_id) > 40 or len(api_key) > 100:
        return None
    d = c.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
    if d is None:
        check_key(api_key, hash_token("dummy"))     # keep timing similar
        return None
    if not check_key(api_key, d["key_hash"]) or d["revoked"]:
        return None
    return d


def is_online(last_seen):
    s = seconds_since(last_seen)
    return s is not None and s <= ONLINE_SECONDS


def touch(c, device, rssi=None, heartbeat=False):
    c.execute("UPDATE devices SET last_seen=?, offline_notified=0 WHERE id=?", (now(), device["id"]))
    if heartbeat:
        c.execute("INSERT INTO heartbeats(device_pk, at, rssi) VALUES (?,?,?)",
                  (device["id"], now(), rssi))


# ------------------------------------------------------------------ OLED formatting

def ist_now():
    """Current India time for the OLED: ('31 Oct 2026', '05:12:08 AM IST')."""
    dt = datetime.now(timezone.utc).astimezone(_local_tz())
    return dt.strftime("%d %b %Y"), dt.strftime("%I:%M:%S %p") + " " + (dt.tzname() or "IST")

def _ascii(s):
    return re.sub(r"\s+", " ", str(s or "").encode("ascii", "ignore").decode()).strip()


def oled_pages(verdict, report_id, confidence=None, headline=""):
    """Pages of lines (max 21 chars each) for a 128x64 SSD1306."""
    label = {"INSUFFICIENT INFORMATION": "INSUFFICIENT INFO"}.get(verdict, verdict)
    conf = f"Conf: {confidence:.0f}%" if confidence is not None else "Conf: n/a"
    pages = [["TRUTHSYNC AI", "VERDICT:", label, conf, f"ID: {report_id}"]]
    h = _ascii(headline)
    if h:
        lines = textwrap.wrap(h, OLED_COLS, break_long_words=True)[:6]
        pages.append(lines)
    d, t = ist_now()
    pages.append(["TRUTHSYNC AI", "Sent (India time)", d, t])
    return [[ln[:OLED_COLS] for ln in p] for p in pages]


# ------------------------------------------------------------------ queueing
def _own_devices(c, user_id, device_pks):
    if not device_pks:
        return []
    q = ",".join("?" * len(device_pks))
    return c.execute(f"SELECT * FROM devices WHERE user_id=? AND revoked=0 AND id IN ({q})",
                     [user_id, *device_pks]).fetchall()


def queue_message(c, user_id, verification_id, device_pks):
    """Creates one delivery per authorised device. Returns list of message ids."""
    v = c.execute("SELECT * FROM verifications WHERE id=? AND user_id=?",
                  (verification_id, user_id)).fetchone()
    if v is None:
        raise PermissionError("Report not found.")
    pages = oled_pages(v["verdict"], v["report_id"], v["confidence"], v["content"])
    return _insert(c, user_id, _own_devices(c, user_id, device_pks), verification_id, "verdict",
                   {"verdict": v["verdict"], "report_id": v["report_id"], "pages": pages})


def queue_test_message(c, user_id, device_pk):
    d, t = ist_now()
    pages = [["TRUTHSYNC AI", "TEST MESSAGE", "Device is connected", d, t]]
    return _insert(c, user_id, _own_devices(c, user_id, [device_pk]), None, "test",
                   {"verdict": "TEST", "report_id": "TEST", "pages": pages})


def _insert(c, user_id, devices, verification_id, kind, payload):
    ids = []
    exp = (datetime.now(timezone.utc) + timedelta(minutes=MESSAGE_TTL_MINUTES)).strftime(TS_FMT)
    for d in devices:
        mid = "m_" + secrets.token_hex(8)
        c.execute("INSERT INTO deliveries(message_id, device_pk, verification_id, kind,"
                  " payload_json, created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
                  (mid, d["id"], verification_id, kind, json.dumps(payload), now(), exp))
        ids.append(mid)
    if ids:
        audit(c, user_id, "message_queued", f"{kind} -> {len(ids)} device(s)")
    return ids


# ------------------------------------------------------------------ device side
def sweep(c):
    """Expires old messages and raises notifications. Safe to call often."""
    t = now()
    rows = c.execute("SELECT dl.id, dl.status, d.user_id, d.name FROM deliveries dl "
                     "JOIN devices d ON d.id=dl.device_pk "
                     "WHERE dl.status IN ('pending','sent') AND dl.expires_at < ?", (t,)).fetchall()
    for r in rows:
        c.execute("UPDATE deliveries SET status='expired' WHERE id=?", (r["id"],))
        if r["status"] == "sent":
            notify(c, r["user_id"], "ack_timeout",
                   f"{r['name']} never confirmed a message it was sent (timed out).")
        else:
            notify(c, r["user_id"], "delivery_failed",
                   f"A message for {r['name']} expired before the device collected it.")
    for d in c.execute("SELECT * FROM devices WHERE revoked=0 AND last_seen IS NOT NULL "
                       "AND offline_notified=0").fetchall():
        if not is_online(d["last_seen"]):
            c.execute("UPDATE devices SET offline_notified=1 WHERE id=?", (d["id"],))
            notify(c, d["user_id"], "device_offline", f"{d['name']} went offline.")


def next_message(c, device):
    """Returns the next message for this device only, or None."""
    sweep(c)
    rows = c.execute("SELECT * FROM deliveries WHERE device_pk=? AND status IN ('pending','sent')"
                     " ORDER BY id", (device["id"],)).fetchall()
    for r in rows:
        if r["status"] == "sent":
            if r["attempts"] >= MAX_ATTEMPTS:
                c.execute("UPDATE deliveries SET status='failed' WHERE id=?", (r["id"],))
                notify(c, device["user_id"], "delivery_failed",
                       f"{device['name']} did not confirm a message after {MAX_ATTEMPTS} attempts.")
                continue
            if (seconds_since(r["sent_at"]) or 0) < REDELIVER_AFTER:
                return None             # give the device time to show it and acknowledge
        c.execute("UPDATE deliveries SET status='sent', sent_at=?, attempts=attempts+1 WHERE id=?",
                  (now(), r["id"]))
        p = json.loads(r["payload_json"])
        return {"message_id": r["message_id"], "report_id": p.get("report_id"),
                "verdict": p.get("verdict"), "pages": p["pages"], "expires_at": r["expires_at"]}
    return None


def acknowledge(c, device, message_id, displayed=True):
    """Marks 'displayed' only when the device says it really showed it."""
    r = c.execute("SELECT * FROM deliveries WHERE message_id=? AND device_pk=?",
                  (message_id, device["id"])).fetchone()
    if r is None:
        return False
    if r["status"] == "displayed":
        return True                      # repeated acknowledgement: fine
    if r["status"] not in ("sent", "pending"):
        return False
    if displayed:
        c.execute("UPDATE deliveries SET status='displayed', acked_at=? WHERE id=?", (now(), r["id"]))
        notify(c, device["user_id"], "delivered", f"Message displayed on {device['name']}.")
    else:
        c.execute("UPDATE deliveries SET status='failed' WHERE id=?", (r["id"],))
        notify(c, device["user_id"], "delivery_failed",
               f"{device['name']} reported it could not display a message.")
    return True
