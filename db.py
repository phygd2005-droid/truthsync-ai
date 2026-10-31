"""SQLite database layer (standard library only).

All timestamps are stored as UTC text 'YYYY-MM-DD HH:MM:SS'.
Set TRUTHSYNC_DB to change the database file location.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("TRUTHSYNC_DB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "truthsync.db")
# Absolute path: the web app and the device API always share ONE database, wherever they are started from.
TS_FMT = "%Y-%m-%d %H:%M:%S"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    reset_hash TEXT,
    reset_expires TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_id TEXT,
    input_type TEXT NOT NULL,
    content TEXT NOT NULL,
    source_url TEXT,
    verdict TEXT NOT NULL,
    basis TEXT,
    confidence REAL,
    method TEXT,
    reason TEXT,
    claims_json TEXT,
    evidence_json TEXT,
    limitations_json TEXT,
    retrieved_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ver_user ON verifications(user_id, created_at);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    device_type TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    is_default INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT,
    offline_notified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    device_pk INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    verification_id INTEGER REFERENCES verifications(id) ON DELETE SET NULL,
    kind TEXT NOT NULL DEFAULT 'verdict',
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    acked_at TEXT,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_del_dev ON deliveries(device_pk, status);

CREATE TABLE IF NOT EXISTS heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_pk INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    at TEXT NOT NULL,
    rssi INTEGER
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).strftime(TS_FMT)


def _local_tz():
    """Display timezone. Default India (IST). Change with APP_TZ=Asia/Kolkata in .env."""
    import os
    from datetime import timedelta
    name = os.environ.get("APP_TZ", "Asia/Kolkata")
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:                       # Windows without tzdata
        return timezone(timedelta(hours=5, minutes=30), "IST") if name == "Asia/Kolkata" else timezone.utc


def local_ts(s):
    """Stored UTC text 'YYYY-MM-DD HH:MM:SS' -> local time text with zone name. Storage stays UTC."""
    try:
        dt = datetime.strptime(str(s)[:19], TS_FMT).replace(tzinfo=timezone.utc).astimezone(_local_tz())
        return dt.strftime(TS_FMT) + " " + (dt.tzname() or "")
    except Exception:
        return s


def parse_ts(s):
    return datetime.strptime(s, TS_FMT).replace(tzinfo=timezone.utc) if s else None


def seconds_since(s):
    d = parse_ts(s)
    return None if d is None else (datetime.now(timezone.utc) - d).total_seconds()


def connect():
    c = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return c


@contextmanager
def db():
    c = connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    with db() as c:
        c.executescript(SCHEMA)


def audit(c, user_id, action, detail=""):
    c.execute("INSERT INTO audit_events(user_id, action, detail, created_at) VALUES (?,?,?,?)",
              (user_id, action, str(detail)[:500], now()))


def notify(c, user_id, kind, message):
    c.execute("INSERT INTO notifications(user_id, kind, message, created_at) VALUES (?,?,?,?)",
              (user_id, kind, str(message)[:300], now()))
