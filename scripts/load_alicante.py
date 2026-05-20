#!/usr/bin/env python3
"""Load the Alicante .xlsx dataset into the SQLite DB.

Hoja `Listing_Semanal`                 → tabla `alicante_listings`
Hoja `Indicadores_Transacciones_Reale` → tabla `alicante_transactions`

Pure stdlib — no `openpyxl` or `pandas` dependency. The .xlsx format is just a
ZIP of XML files, so we read sharedStrings + each sheet's row tags directly.
This keeps the runtime venv lean (only one place reads Excel: this script).

Usage
-----
    make load-alicante FILE=~/Downloads/Alicante.xlsx

Or directly:

    backend/.venv/bin/python scripts/load_alicante.py /path/to/Alicante.xlsx

The loader is idempotent: rows are upserted by `gsraw_id` (listings) and
`table_id` (transactions). Re-running with a newer snapshot updates in place.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from xml.etree import ElementTree as ET

# Allow running from anywhere — we need to import modules that live in
# `backend/`. Adding it to sys.path keeps the script callable from project root.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Intentional late imports after sys.path tweak.
import db  # noqa: E402
from alicante import storage as alicante_storage  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("load_alicante")

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

LISTING_SHEET_NAMES = ("Listing_Semanal",)
# Excel truncates sheet names at 31 chars; the source name is
# "Indicadores_Transacciones_Reales" which gets cut to ...Reale.
TXN_SHEET_NAMES = (
    "Indicadores_Transacciones_Reales",
    "Indicadores_Transacciones_Reale",
)

LISTING_BOOL_COLUMNS = {
    "is_agency", "is_exact_address", "is_vertical", "has_storage",
    "has_garage", "has_garage_included", "has_common_zones", "has_pool",
    "has_air_conditioner", "has_elevator", "has_terrace", "is_exterior",
    "has_racket_zone", "has_security", "is_bank", "flag_nuda",
    "flag_hipoteca_inversa", "flag_renta_antigua", "flag_ocupado", "is_vpo",
}
LISTING_INT_COLUMNS = {
    "local_price", "area", "n_rooms", "n_baths", "boundary_id",
    "year_of_construction",
}
LISTING_FLOAT_COLUMNS = {"lat", "lon"}

# Subset of headers we actually persist. Anything else in the .xlsx is ignored.
LISTING_PERSISTED_COLUMNS = {
    "gsraw_id", "origin_id", "source_name", "operation_type_name",
    "usage_name", "property_type_name", "build_status_name",
    "conservation_name", "local_price", "area", "n_rooms", "n_baths",
    "n_floor", "lat", "lon", "full_address", "is_exact_address",
    "admin2", "admin3", "admin4", "admin5", "admin6", "boundary_id",
    "has_storage", "has_garage", "has_pool", "has_air_conditioner",
    "has_elevator", "has_terrace", "has_common_zones", "is_exterior",
    "energy_cert_name", "year_of_construction", "first_appearance",
    "last_appearance", "delivery_week", "title", "first_image_url",
    "ine_code",
}

TXN_INT_COLUMNS = {
    "boundary_type", "boundary_id", "operation_type_id", "indicator_id",
    "segment_id",
}
TXN_FLOAT_COLUMNS = {"calculated_value", "estimated_value"}
TXN_PERSISTED_COLUMNS = {
    "table_id", "boundary_type", "boundary_id", "operation_type_id",
    "period_id", "indicator_id", "segment_id", "calculated_value",
    "estimated_value", "execution_datetime",
}


# ────────────────────────────────────────────────────────────────────────
# XLSX → row dict streaming
# ────────────────────────────────────────────────────────────────────────


def _col_letters_to_index(letters: str) -> int:
    """A→0, B→1, ..., AA→26."""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _parse_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        info = zf.getinfo("xl/sharedStrings.xml")
    except KeyError:
        return []

    strings: list[str] = []
    with zf.open(info) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag == f"{NS}si":
                text = "".join(
                    (t.text or "") for t in elem.iter(f"{NS}t")
                )
                strings.append(text)
                elem.clear()
    return strings


def _list_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Returns [(sheet_name, sheet_xml_path), …] in workbook order."""
    sheet_files = sorted(
        n for n in zf.namelist()
        if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    )
    sheet_files.sort(key=lambda p: int(re.search(r"sheet(\d+)\.xml", p).group(1)))

    with zf.open("xl/workbook.xml") as fh:
        tree = ET.parse(fh)
    names = [sh.get("name") for sh in tree.getroot().iter(f"{NS}sheet")]
    return list(zip(names, sheet_files))


def _iter_rows(
    zf: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> Iterator[list[Optional[str]]]:
    """Yield rows as lists of string-or-None values, one per column index."""
    with zf.open(sheet_path) as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != f"{NS}row":
                continue
            cells: dict[int, str] = {}
            max_idx = -1
            for c in elem.iter(f"{NS}c"):
                ref = c.get("r") or ""
                letters = re.match(r"[A-Z]+", ref)
                if not letters:
                    continue
                idx = _col_letters_to_index(letters.group(0))
                cell_type = c.get("t")
                value_node = c.find(f"{NS}v")
                inline = c.find(f"{NS}is")

                if cell_type == "s" and value_node is not None:
                    try:
                        cells[idx] = shared_strings[int(value_node.text or 0)]
                    except (IndexError, ValueError):
                        cells[idx] = ""
                elif cell_type == "inlineStr" and inline is not None:
                    cells[idx] = "".join(
                        (t.text or "") for t in inline.iter(f"{NS}t")
                    )
                elif value_node is not None:
                    cells[idx] = value_node.text or ""
                else:
                    cells[idx] = ""
                max_idx = max(max_idx, idx)
            if max_idx < 0:
                elem.clear()
                continue
            yield [cells.get(i) for i in range(max_idx + 1)]
            elem.clear()


# ────────────────────────────────────────────────────────────────────────
# Value coercion
# ────────────────────────────────────────────────────────────────────────


def _coerce_bool(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    norm = str(value).strip().lower()
    if norm in {"true", "1", "yes", "si", "sí", "t"}:
        return 1
    if norm in {"false", "0", "no", "n", "f"}:
        return 0
    return None


def _coerce_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_to_listing(headers: list[str], row: list[Optional[str]]) -> Optional[dict]:
    if len(row) < len(headers):
        row = row + [None] * (len(headers) - len(row))

    record: dict = {}
    for col, raw in zip(headers, row):
        if col not in LISTING_PERSISTED_COLUMNS:
            continue
        if col in LISTING_BOOL_COLUMNS:
            record[col] = _coerce_bool(raw)
        elif col in LISTING_INT_COLUMNS:
            record[col] = _coerce_int(raw)
        elif col in LISTING_FLOAT_COLUMNS:
            record[col] = _coerce_float(raw)
        else:
            record[col] = raw if raw not in (None, "") else None

    if not record.get("gsraw_id"):
        return None
    return record


def _row_to_transaction(headers: list[str], row: list[Optional[str]]) -> Optional[dict]:
    if len(row) < len(headers):
        row = row + [None] * (len(headers) - len(row))

    record: dict = {}
    for col, raw in zip(headers, row):
        if col not in TXN_PERSISTED_COLUMNS:
            continue
        if col in TXN_INT_COLUMNS:
            record[col] = _coerce_int(raw)
        elif col in TXN_FLOAT_COLUMNS:
            record[col] = _coerce_float(raw)
        else:
            record[col] = raw if raw not in (None, "") else None

    if not record.get("table_id"):
        return None
    return record


# ────────────────────────────────────────────────────────────────────────
# Sheet loaders
# ────────────────────────────────────────────────────────────────────────


def _find_sheet(
    sheets: list[tuple[str, str]],
    candidates: tuple[str, ...],
) -> Optional[tuple[str, str]]:
    by_name = {name: path for name, path in sheets}
    for candidate in candidates:
        if candidate in by_name:
            return candidate, by_name[candidate]
    # Fuzzy match (Excel truncates names at 31 chars).
    for name, path in sheets:
        normalized = name.strip()
        for candidate in candidates:
            if normalized.startswith(candidate[:31].strip()):
                return name, path
    return None


def load_listings(
    zf: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
    *,
    batch_size: int = 1000,
) -> int:
    iterator = _iter_rows(zf, sheet_path, shared_strings)
    headers = next(iterator, None)
    if not headers:
        logger.warning("Listing sheet is empty")
        return 0
    headers = [h or "" for h in headers]

    total = 0
    batch: list[dict] = []
    skipped = 0
    for row in iterator:
        record = _row_to_listing(headers, row)
        if record is None:
            skipped += 1
            continue
        batch.append(record)
        if len(batch) >= batch_size:
            total += alicante_storage.bulk_upsert_listings(batch)
            logger.info("Listings upserted: %d", total)
            batch.clear()

    if batch:
        total += alicante_storage.bulk_upsert_listings(batch)

    if skipped:
        logger.info("Skipped %d listing rows without gsraw_id", skipped)
    return total


def load_transactions(
    zf: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
    *,
    batch_size: int = 1000,
) -> int:
    iterator = _iter_rows(zf, sheet_path, shared_strings)
    headers = next(iterator, None)
    if not headers:
        logger.warning("Transactions sheet is empty")
        return 0
    headers = [h or "" for h in headers]

    total = 0
    batch: list[dict] = []
    skipped = 0
    for row in iterator:
        record = _row_to_transaction(headers, row)
        if record is None:
            skipped += 1
            continue
        batch.append(record)
        if len(batch) >= batch_size:
            total += alicante_storage.bulk_upsert_transactions(batch)
            logger.info("Transactions upserted: %d", total)
            batch.clear()

    if batch:
        total += alicante_storage.bulk_upsert_transactions(batch)

    if skipped:
        logger.info("Skipped %d transaction rows without table_id", skipped)
    return total


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Alicante .xlsx into SQLite")
    parser.add_argument(
        "file",
        nargs="?",
        default=os.environ.get("ALICANTE_XLSX"),
        help="Path to the Alicante .xlsx export. Can also be set via ALICANTE_XLSX.",
    )
    args = parser.parse_args()

    if not args.file:
        parser.error("path to .xlsx is required (positional arg or ALICANTE_XLSX env)")
    xlsx_path = Path(args.file).expanduser().resolve()
    if not xlsx_path.is_file():
        parser.error(f"file not found: {xlsx_path}")

    db.init_db()
    logger.info("DB ready at %s", db.db_path())
    logger.info("Loading %s …", xlsx_path)
    started_at = datetime.now()

    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings = _parse_shared_strings(zf)
        sheets = _list_sheets(zf)
        logger.info("Sheets detected: %s", [name for name, _ in sheets])

        listings_count = 0
        transactions_count = 0

        listing_sheet = _find_sheet(sheets, LISTING_SHEET_NAMES)
        if listing_sheet:
            name, path = listing_sheet
            logger.info("Loading listings from sheet %r", name)
            listings_count = load_listings(zf, path, shared_strings)
        else:
            logger.warning("Listing sheet not found (looked for %s)", LISTING_SHEET_NAMES)

        txn_sheet = _find_sheet(sheets, TXN_SHEET_NAMES)
        if txn_sheet:
            name, path = txn_sheet
            logger.info("Loading transactions from sheet %r", name)
            transactions_count = load_transactions(zf, path, shared_strings)
        else:
            logger.warning(
                "Transactions sheet not found (looked for %s)", TXN_SHEET_NAMES
            )

    elapsed = (datetime.now() - started_at).total_seconds()
    logger.info(
        "Loaded %d listings, %d transactions in %.1fs",
        listings_count, transactions_count, elapsed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
