"""SQLite persistence for leads and valuations.

Single-file DB managed via stdlib `sqlite3` — no migrations engine, just
`CREATE TABLE IF NOT EXISTS` at startup. The DB file lives in
`backend/data/prophero.db` (gitignored).

Design goals:

- Zero new pip dependencies.
- WAL mode + busy_timeout so the FastAPI request handlers don't block each other.
- Connection-per-call (cheap with WAL, avoids the threading caveats of holding
  a single connection across async coroutines).
- JSON payloads are stored as TEXT — we don't need to query inside them yet, and
  this keeps the schema honest about the fact that the API contract may evolve.

Public surface:

- `init_db(path)` — call once at app startup.
- `insert_lead(...)` → lead_id.
- `insert_valuation(lead_id, request, response)` → valuation_id.
- `get_lead(lead_id)` / `get_valuation(valuation_id)` — for the report endpoint.
- `recent_leads(limit)` — for ops/debug.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "prophero.db"

_lock = threading.Lock()
_db_path: Optional[Path] = None


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS leads (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name   TEXT NOT NULL,
        email       TEXT NOT NULL,
        phone       TEXT NOT NULL,
        created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS valuations (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id       INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        address       TEXT NOT NULL,
        municipio     TEXT,
        estimated_eur INTEGER,
        request_json  TEXT NOT NULL,
        response_json TEXT NOT NULL,
        email_sent    INTEGER NOT NULL DEFAULT 0,
        email_error   TEXT,
        created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_valuations_lead_id ON valuations(lead_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_valuations_created_at ON valuations(created_at)
    """,
)


def init_db(path: Optional[Path] = None) -> Path:
    """Create the DB file and tables if missing. Idempotent — safe to call on every startup."""
    global _db_path

    target = Path(path) if path else DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    with _lock:
        _db_path = target
        with _connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA foreign_keys = ON")
            for statement in SCHEMA_STATEMENTS:
                conn.execute(statement)
            conn.commit()

    logger.info("SQLite ready at %s", target)
    return target


def db_path() -> Path:
    if _db_path is None:
        return init_db()
    return _db_path


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Yield a short-lived connection with sensible pragmas + row_factory."""
    conn = sqlite3.connect(
        db_path(),
        timeout=10.0,
        isolation_level=None,  # autocommit off — we use explicit `conn.commit()`
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        yield conn
    finally:
        conn.close()


def insert_lead(*, full_name: str, email: str, phone: str) -> int:
    """Insert a new lead. Always inserts a row — we don't dedupe by email on purpose
    (the same person may request multiple valuations and that's legitimate data)."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO leads (full_name, email, phone) VALUES (?, ?, ?)",
            (full_name, email, phone),
        )
        conn.commit()
        return int(cur.lastrowid)


def insert_valuation(
    *,
    lead_id: Optional[int],
    address: str,
    municipio: Optional[str],
    estimated_eur: Optional[int],
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
) -> int:
    """Persist a full valuation request + response (as JSON blobs)."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO valuations
                (lead_id, address, municipio, estimated_eur, request_json, response_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                address,
                municipio,
                estimated_eur,
                json.dumps(request_payload, ensure_ascii=False),
                json.dumps(response_payload, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def mark_email_sent(valuation_id: int, *, error: Optional[str] = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE valuations SET email_sent = ?, email_error = ? WHERE id = ?",
            (0 if error else 1, error, valuation_id),
        )
        conn.commit()


def get_lead(lead_id: int) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row) if row else None


def get_valuation(valuation_id: int) -> Optional[dict[str, Any]]:
    """Hydrates JSON columns back into dicts for caller convenience."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM valuations WHERE id = ?", (valuation_id,)
        ).fetchone()
    if not row:
        return None
    record = dict(row)
    for json_field in ("request_json", "response_json"):
        try:
            record[json_field] = json.loads(record[json_field]) if record[json_field] else None
        except json.JSONDecodeError:
            logger.warning("Could not decode %s for valuation %s", json_field, valuation_id)
            record[json_field] = None
    return record


def recent_leads(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [dict(r) for r in rows]
