"""Calibration harness — runs the test dataset against /api/valuation.

Usage (from repo root):

    python -m tests.evaluation.run_evaluation \\
        --csv tests/data/test_valuation.csv \\
        [--api http://localhost:8001] \\
        [--label baseline] \\
        [--no-cache]

The CSV must contain at minimum these columns:

    - address              (string)
    - m2                   (int)
    - bedrooms             (int)
    - bathrooms            (int)
    - appraiser_value      (int — the ground truth from a professional appraiser)

Optional columns: property_type, property_condition, pool, terrace, elevator,
parking, notes. Rows missing required inputs are skipped and reported.

Outputs land in `tests/evaluation/reports/{timestamp}-{label}.{json,md}`. A
filesystem cache keyed by `(address, m2, beds, baths, property_condition)`
keeps re-runs fast (~5-15s per row otherwise).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import urllib.error
import urllib.request

from tests.evaluation.metrics import (
    AggregateMetrics,
    RowResult,
    build_row_result,
    compute_aggregate,
    format_markdown_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("evaluation")

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "tests" / "evaluation" / "reports"
CACHE_DIR = REPO_ROOT / "tests" / "evaluation" / ".cache"

REQUIRED_FIELDS = ("address", "m2", "bedrooms", "bathrooms", "appraiser_value")

# Tolerant number parser: accepts "465,000", "465.000", "465 000", quoted, etc.
NUMERIC_RE = re.compile(r"[\d]+(?:[.,\s][\d]+)*")


def parse_number(raw: Any) -> Optional[int]:
    """Best-effort int parsing for messy CSV cells (commas, spaces, N/A, -)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.upper() in {"N/A", "NA", "-", "—", "#DIV/0!", "NULL"}:
        return None
    match = NUMERIC_RE.search(text)
    if not match:
        return None
    digits = re.sub(r"[^\d]", "", match.group(0))
    return int(digits) if digits else None


def parse_bool(raw: Any) -> bool:
    if raw is None:
        return False
    return str(raw).strip().lower() in {"true", "yes", "y", "1", "sí", "si"}


def strip_floor_info(address: str) -> str:
    """Idealista does not like floor/door suffixes like '6D', '3°-7', 'PB-2'.

    Strip everything from the first occurrence of a digit-suffix pattern that
    looks like a floor/door marker, while keeping the street name + city.
    """
    # Keep the city tail (after the last comma) and rejoin once.
    parts = [p.strip() for p in address.split(",")]
    if len(parts) <= 2:
        return address
    # Anything that contains "°", "º", "ª", "planta", a 1-2 char alphanumeric
    # token like "6D"/"2C"/"PB"/"EN"/"3A", we treat as floor/door noise.
    floor_pattern = re.compile(
        r"(°|º|ª|planta|floor|esc[\.\s]|puerta|piso|pta|"
        r"^\s*(pb|ba?jo|en|principal|atico|ático)\s*$|"
        r"^\s*[a-z]{1,2}\s*-?\s*\d*\s*$|"
        r"^\s*\d+\s*[a-z]\s*$)",
        re.IGNORECASE,
    )
    cleaned = [p for p in parts if not floor_pattern.search(p)]
    if len(cleaned) < 2:
        # Fell off too much — fall back to first + last (street + city).
        return f"{parts[0]}, {parts[-1]}"
    return ", ".join(cleaned)


def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(
            f"CSV not found: {path}\n"
            f"Run with --csv pointing to your dataset. "
            f"See tests/data/test_valuation.example.csv for the expected schema."
        )

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for index, raw in enumerate(reader, start=1):
            rows.append({**raw, "_row_index": index})
    return rows


def normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Pick known columns from a CSV row and coerce types. Tolerates Spanish-named
    columns from the existing dataset (`Dirección`, `Valoraciones manuales`).
    """
    address = raw.get("address") or raw.get("Dirección") or raw.get("direccion") or ""
    appraiser_raw = (
        raw.get("appraiser_value")
        or raw.get("Valoraciones manuales")
        or raw.get("valoracion_manual")
    )

    return {
        "row_index": raw.get("_row_index"),
        "address": (address or "").strip().strip('"'),
        "m2": parse_number(raw.get("m2")),
        "bedrooms": parse_number(raw.get("bedrooms")),
        "bathrooms": parse_number(raw.get("bathrooms")),
        "property_type": (raw.get("property_type") or "").strip() or None,
        "property_condition": (raw.get("property_condition") or "").strip() or None,
        "features": {
            "pool": parse_bool(raw.get("pool")),
            "terrace": parse_bool(raw.get("terrace")),
            "elevator": parse_bool(raw.get("elevator")),
            "parking": parse_bool(raw.get("parking")),
        },
        "appraiser_value": parse_number(appraiser_raw),
        "notes": (raw.get("notes") or "").strip() or None,
    }


def is_runnable(row: dict[str, Any]) -> tuple[bool, Optional[str]]:
    missing = [
        field
        for field in REQUIRED_FIELDS
        if field == "appraiser_value" and row.get("appraiser_value") is None
        or field == "address" and not row.get("address")
        or field in ("m2", "bedrooms", "bathrooms") and row.get(field) is None
    ]
    if missing:
        return False, f"missing required fields: {', '.join(missing)}"
    return True, None


def cache_key(row: dict[str, Any]) -> str:
    payload = {
        "address": strip_floor_info(row["address"]),
        "m2": row["m2"],
        "bedrooms": row["bedrooms"],
        "bathrooms": row["bathrooms"],
        "condition": row["property_condition"],
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def post_valuation(api_base: str, payload: dict[str, Any], timeout: int = 90) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}/api/valuation"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — internal call
        return json.loads(resp.read().decode("utf-8"))


def evaluate_row(
    row: dict[str, Any],
    *,
    api_base: str,
    use_cache: bool,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Returns (api_response, error_message). Uses on-disk cache when possible."""

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = cache_key(row)
    cache_path = CACHE_DIR / f"{key}.json"

    if use_cache and cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8")), None
        except json.JSONDecodeError:
            cache_path.unlink(missing_ok=True)

    cleaned_address = strip_floor_info(row["address"])
    payload = {
        "address": cleaned_address,
        "m2": row["m2"],
        "bedrooms": row["bedrooms"],
        "bathrooms": row["bathrooms"],
        "property_type": row["property_type"],
        "property_condition": row["property_condition"],
        "features": row["features"],
    }

    try:
        response = post_valuation(api_base, payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return None, f"HTTP {exc.code}: {body[:200]}"
    except urllib.error.URLError as exc:
        return None, f"network error: {exc.reason}"
    except Exception as exc:  # pylint: disable=broad-except
        return None, f"unexpected: {exc!r}"

    if use_cache:
        cache_path.write_text(json.dumps(response), encoding="utf-8")

    return response, None


def git_sha() -> Optional[str]:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT
            )
            .decode("utf-8")
            .strip()
        )
    except Exception:  # pylint: disable=broad-except
        return None


def run(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv).resolve()
    raw_rows = load_csv(csv_path)
    normalized = [normalize_row(r) for r in raw_rows]

    runnable = []
    skipped = []
    for row in normalized:
        ok, reason = is_runnable(row)
        if ok:
            runnable.append(row)
        else:
            skipped.append((row, reason))

    logger.info(
        "Loaded %d rows from %s → %d runnable, %d skipped (missing inputs)",
        len(normalized),
        csv_path,
        len(runnable),
        len(skipped),
    )
    for row, reason in skipped[:5]:
        logger.warning("  skip #%s '%s' — %s", row["row_index"], row["address"][:60], reason)
    if len(skipped) > 5:
        logger.warning("  ... and %d more skipped rows", len(skipped) - 5)

    if not runnable:
        logger.error(
            "No runnable rows. Fill in m2 / bedrooms / bathrooms / appraiser_value "
            "in the CSV (see tests/data/test_valuation.example.csv)."
        )
        return 1

    results: list[RowResult] = []
    start = time.perf_counter()

    for index, row in enumerate(runnable, start=1):
        row_id = f"#{row['row_index']}"
        logger.info(
            "[%d/%d] %s — m²=%s, hab=%s, baños=%s, appraiser=%s",
            index,
            len(runnable),
            row["address"][:60],
            row["m2"],
            row["bedrooms"],
            row["bathrooms"],
            row["appraiser_value"],
        )

        response, err = evaluate_row(row, api_base=args.api, use_cache=not args.no_cache)

        if err or not response:
            results.append(
                build_row_result(
                    row_id=row_id,
                    address=row["address"],
                    appraiser_value=row["appraiser_value"],
                    predicted_value=None,
                    price_range_low=None,
                    price_range_high=None,
                    comparables_used=0,
                    final_stage=None,
                    estimation_method=None,
                    error=err,
                )
            )
            logger.warning("  ✗ %s", err)
            continue

        stats = response.get("stats", {}) or {}
        metadata = response.get("search_metadata", {}) or {}
        predicted = stats.get("estimated_value")
        result = build_row_result(
            row_id=row_id,
            address=row["address"],
            appraiser_value=row["appraiser_value"],
            predicted_value=predicted,
            price_range_low=stats.get("price_range_low"),
            price_range_high=stats.get("price_range_high"),
            comparables_used=stats.get("total_comparables", 0),
            final_stage=metadata.get("final_stage"),
            estimation_method=stats.get("estimation_method"),
        )
        results.append(result)

        if predicted is not None:
            logger.info(
                "  → predicted=%s, abs_err=%s, %%err=%s, in_range=%s",
                f"{predicted:,}",
                f"{result.abs_error:,}" if result.abs_error else "—",
                f"{result.pct_error:.1f}%" if result.pct_error is not None else "—",
                result.within_range,
            )
        else:
            logger.warning("  → no estimate returned by API")

    elapsed = time.perf_counter() - start
    metrics = compute_aggregate(results)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sha = git_sha() or "nosha"
    label = args.label or "run"
    base_name = f"{timestamp}-{sha}-{label}"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    json_path = REPORTS_DIR / f"{base_name}.json"
    md_path = REPORTS_DIR / f"{base_name}.md"

    json_payload = {
        "run_label": label,
        "git_sha": sha,
        "csv_path": str(csv_path),
        "api_base": args.api,
        "timestamp_utc": timestamp,
        "elapsed_seconds": round(elapsed, 2),
        "metrics": metrics.to_dict(),
        "rows": [asdict(r) for r in results],
        "skipped": [
            {"row_index": r["row_index"], "address": r["address"], "reason": reason}
            for r, reason in skipped
        ],
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(
        format_markdown_report(
            metrics=metrics, rows=results, run_label=label, git_sha=sha, api_base=args.api
        ),
        encoding="utf-8",
    )

    print_summary(metrics, elapsed)
    logger.info("Reports written to:\n  %s\n  %s", json_path, md_path)
    return 0


def print_summary(metrics: AggregateMetrics, elapsed: float) -> None:
    print("")
    print("=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  Rows total:      {metrics.n_total}")
    print(f"  Rows evaluated:  {metrics.n_evaluated}")
    print(f"  Rows failed:     {metrics.n_failed}")
    print(f"  MAE:             {metrics.mae if metrics.mae is not None else '—'} €")
    print(f"  MAPE:            {metrics.mape if metrics.mape is not None else '—'} %")
    print(f"  Median % error:  {metrics.median_pct_error if metrics.median_pct_error is not None else '—'} %")
    print(f"  RMSE:            {metrics.rmse if metrics.rmse is not None else '—'} €")
    print(f"  Within range %:  {metrics.within_range_pct if metrics.within_range_pct is not None else '—'} %")
    print(f"  Bias % (signed): {metrics.bias_pct if metrics.bias_pct is not None else '—'} %")
    print(f"  Elapsed:         {elapsed:.1f}s")
    print("=" * 60)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        default="tests/data/test_valuation.csv",
        help="Path to the ground-truth CSV (default: tests/data/test_valuation.csv)",
    )
    parser.add_argument(
        "--api",
        default="http://localhost:8001",
        help="API base URL (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--label",
        default="run",
        help="Short tag for this run, used in the report filename (e.g. 'baseline', 'ols')",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass the local response cache and re-hit the API for every row",
    )
    return parser


if __name__ == "__main__":
    sys.exit(run(build_parser().parse_args()))
