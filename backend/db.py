import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(os.getenv("CLIPCONTROL_DATA", "data")).resolve()
def now():
    return datetime.now(timezone.utc).isoformat()
def uid():
    return uuid.uuid4().hex
@contextmanager
def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATA / "clipcontrol.sqlite", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
def init():
    for folder in ("originals", "clips", "work"):
        (DATA / folder).mkdir(parents=True, exist_ok=True)
    with connection() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY)")
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            if not c.execute("SELECT 1 FROM migrations WHERE name=?", (path.name,)).fetchone():
                script = path.read_text()
                # Schema and ledger entry are atomic, including on an interrupted startup.
                c.executescript("BEGIN IMMEDIATE;\n" + script + "\nINSERT INTO migrations(name) VALUES('" + path.name + "');\nCOMMIT;")
def event(message, detail=None, conn=None):
    if conn is not None:
        conn.execute("INSERT INTO events(message,detail,created) VALUES(?,?,?)", (message, detail, now()))
    else:
        with connection() as c:
            event(message, detail, c)
def one(sql, params=()):
    with connection() as c:
        row = c.execute(sql, params).fetchone()
        return dict(row) if row else None
def rows(sql, params=()):
    with connection() as c:
        return [dict(r) for r in c.execute(sql, params)]
def decode(row):
    for key in ("metadata", "analysis", "plan", "payload"):
        if row.get(key):
            row[key] = json.loads(row[key])
    return row
