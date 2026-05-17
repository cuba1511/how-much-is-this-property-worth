"""SQLite persistence for leads and valuations.

Single-file DB managed via stdlib `sqlite3` — no migrations engine, just
`CREATE TABLE IF NOT EXISTS` at startup. The DB file lives in
`backend/data/prophero.db` (gitignored).

Design goals:

- Zero new pip dependencies.
- WAL mode + busy_timeout so the FastAPI request handlers don't block each other.
- Connection-per-call (cheap with WAL, avoids the threading caveats of holding
  a single connection across async coroutines).
- Denormalized columns on `valuations` for funnel/property fields (intent,
  Catastro RC, m², etc.) plus full `request_json` / `response_json` snapshots.

Public surface:

- `init_db(path)` — call once at app startup.
- `insert_lead(...)` → lead_id.
- `insert_valuation(lead_id, request, response)` → valuation_id.
- `get_lead(lead_id)` / `get_valuation(valuation_id)` → typed records.
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

from models import LeadRecord, ValuationRecord, ValuationRequest

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "prophero.db"

_lock = threading.Lock()
_db_path: Optional[Path] = None

# Added via ALTER on existing DBs; included inline in CREATE for fresh installs.
_VALUATION_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("valuation_intent", "TEXT"),
    ("sell_reason", "TEXT"),
    ("sell_timeline", "TEXT"),
    ("cadastral_reference", "TEXT"),
    ("property_type", "TEXT"),
    ("property_condition", "TEXT"),
    ("m2", "INTEGER"),
    ("bedrooms", "INTEGER"),
    ("bathrooms", "INTEGER"),
)

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
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id             INTEGER REFERENCES leads(id) ON DELETE SET NULL,
        address             TEXT NOT NULL,
        municipio           TEXT,
        estimated_eur       INTEGER,
        valuation_intent    TEXT,
        sell_reason         TEXT,
        sell_timeline       TEXT,
        cadastral_reference TEXT,
        property_type       TEXT,
        property_condition  TEXT,
        m2                  INTEGER,
        bedrooms            INTEGER,
        bathrooms           INTEGER,
        request_json        TEXT NOT NULL,
        response_json       TEXT NOT NULL,
        email_sent          INTEGER NOT NULL DEFAULT 0,
        email_error         TEXT,
        created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_valuations_lead_id ON valuations(lead_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_valuations_created_at ON valuations(created_at)
    """,
)

_POST_MIGRATION_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_valuations_intent ON valuations(valuation_intent)",
    "CREATE INDEX IF NOT EXISTS idx_valuations_cadastral ON valuations(cadastral_reference)",
)


def _migrate_valuations_schema(conn: sqlite3.Connection) -> None:
    """ALTER TABLE for DBs created before denormalized valuation columns existed."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(valuations)").fetchall()}
    for column, sql_type in _VALUATION_EXTRA_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE valuations ADD COLUMN {column} {sql_type}")
            logger.info("SQLite migration: added valuations.%s", column)


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
            _migrate_valuations_schema(conn)
            for statement in _POST_MIGRATION_INDEXES:
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
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        yield conn
    finally:
        conn.close()


def _valuation_column_values(request: ValuationRequest) -> dict[str, Any]:
    unit = request.selected_cadastral_unit
    return {
        "valuation_intent": request.valuation_intent,
        "sell_reason": request.sell_reason,
        "sell_timeline": request.sell_timeline,
        "cadastral_reference": unit.cadastral_reference if unit else None,
        "property_type": request.property_type,
        "property_condition": request.property_condition,
        "m2": request.m2,
        "bedrooms": request.bedrooms,
        "bathrooms": request.bathrooms,
    }


def insert_lead(*, full_name: str, email: str, phone: str) -> int:
    """Insert a new lead. Always inserts a row — we don't dedupe by email on purpose."""
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
    request: ValuationRequest,
    response_payload: dict[str, Any],
    municipio: Optional[str],
    estimated_eur: Optional[int],
) -> int:
    """Persist valuation with denormalized columns + full JSON snapshots."""
    cols = _valuation_column_values(request)
    request_json = request.model_dump(mode="json")

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO valuations (
                lead_id, address, municipio, estimated_eur,
                valuation_intent, sell_reason, sell_timeline, cadastral_reference,
                property_type, property_condition, m2, bedrooms, bathrooms,
                request_json, response_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                request.address,
                municipio,
                estimated_eur,
                cols["valuation_intent"],
                cols["sell_reason"],
                cols["sell_timeline"],
                cols["cadastral_reference"],
                cols["property_type"],
                cols["property_condition"],
                cols["m2"],
                cols["bedrooms"],
                cols["bathrooms"],
                json.dumps(request_json, ensure_ascii=False),
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


def _row_to_lead(row: sqlite3.Row) -> LeadRecord:
    return LeadRecord.model_validate(dict(row))


def _row_to_valuation(row: sqlite3.Row) -> ValuationRecord:
    record = dict(row)
    record["email_sent"] = bool(record.get("email_sent"))
    for json_field in ("request_json", "response_json"):
        raw = record.get(json_field)
        try:
            record[json_field] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            logger.warning("Could not decode %s for valuation %s", json_field, record.get("id"))
            record[json_field] = {}
    return ValuationRecord.model_validate(record)


def get_lead(lead_id: int) -> Optional[LeadRecord]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return _row_to_lead(row) if row else None


def get_valuation(valuation_id: int) -> Optional[ValuationRecord]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM valuations WHERE id = ?", (valuation_id,)
        ).fetchone()
    return _row_to_valuation(row) if row else None


def recent_leads(limit: int = 50) -> list[LeadRecord]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
    return [_row_to_lead(r) for r in rows]
