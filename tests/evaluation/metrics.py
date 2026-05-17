"""Aggregate accuracy metrics for the valuation evaluation harness.

All inputs are paired lists of `(predicted, ground_truth)` in EUR. Predicted
may be `None` (the API failed to return an estimate for that row); those rows
are excluded from the aggregate metrics and reported separately.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from statistics import median
from typing import Optional


@dataclass(frozen=True)
class RowResult:
    """Per-row evaluation outcome."""

    row_id: str
    address: str
    appraiser_value: int
    predicted_value: Optional[int]
    price_range_low: Optional[int]
    price_range_high: Optional[int]
    abs_error: Optional[int]
    pct_error: Optional[float]
    within_range: Optional[bool]
    comparables_used: int
    final_stage: Optional[str]
    estimation_method: Optional[str]
    error: Optional[str] = None  # populated when the API call failed


@dataclass(frozen=True)
class AggregateMetrics:
    n_total: int
    n_evaluated: int
    n_failed: int
    mae: Optional[float]            # Mean Absolute Error (€)
    mape: Optional[float]           # Mean Absolute Percentage Error (%)
    median_pct_error: Optional[float]
    rmse: Optional[float]           # Root Mean Square Error (€)
    within_range_pct: Optional[float]  # % of appraiser values inside [low, high]
    bias_pct: Optional[float]       # mean signed pct error — positive = we overestimate

    def to_dict(self) -> dict:
        return asdict(self)


def compute_aggregate(rows: list[RowResult]) -> AggregateMetrics:
    evaluated = [r for r in rows if r.predicted_value is not None and r.appraiser_value]
    failed = [r for r in rows if r.predicted_value is None]

    if not evaluated:
        return AggregateMetrics(
            n_total=len(rows),
            n_evaluated=0,
            n_failed=len(failed),
            mae=None,
            mape=None,
            median_pct_error=None,
            rmse=None,
            within_range_pct=None,
            bias_pct=None,
        )

    abs_errors = [float(r.abs_error) for r in evaluated if r.abs_error is not None]
    pct_errors = [float(r.pct_error) for r in evaluated if r.pct_error is not None]
    signed_pct_errors = [
        ((r.predicted_value - r.appraiser_value) / r.appraiser_value) * 100.0
        for r in evaluated
        if r.predicted_value is not None
    ]
    ranged = [r for r in evaluated if r.within_range is not None]
    in_range = sum(1 for r in ranged if r.within_range)

    mae = sum(abs_errors) / len(abs_errors) if abs_errors else None
    mape = sum(pct_errors) / len(pct_errors) if pct_errors else None
    med_pct = median(pct_errors) if pct_errors else None
    rmse = (
        math.sqrt(sum(e * e for e in abs_errors) / len(abs_errors))
        if abs_errors
        else None
    )
    within_pct = (in_range / len(ranged)) * 100.0 if ranged else None
    bias = sum(signed_pct_errors) / len(signed_pct_errors) if signed_pct_errors else None

    return AggregateMetrics(
        n_total=len(rows),
        n_evaluated=len(evaluated),
        n_failed=len(failed),
        mae=round(mae, 2) if mae is not None else None,
        mape=round(mape, 2) if mape is not None else None,
        median_pct_error=round(med_pct, 2) if med_pct is not None else None,
        rmse=round(rmse, 2) if rmse is not None else None,
        within_range_pct=round(within_pct, 2) if within_pct is not None else None,
        bias_pct=round(bias, 2) if bias is not None else None,
    )


def build_row_result(
    *,
    row_id: str,
    address: str,
    appraiser_value: int,
    predicted_value: Optional[int],
    price_range_low: Optional[int],
    price_range_high: Optional[int],
    comparables_used: int,
    final_stage: Optional[str],
    estimation_method: Optional[str],
    error: Optional[str] = None,
) -> RowResult:
    if predicted_value is None or appraiser_value <= 0:
        return RowResult(
            row_id=row_id,
            address=address,
            appraiser_value=appraiser_value,
            predicted_value=predicted_value,
            price_range_low=price_range_low,
            price_range_high=price_range_high,
            abs_error=None,
            pct_error=None,
            within_range=None,
            comparables_used=comparables_used,
            final_stage=final_stage,
            estimation_method=estimation_method,
            error=error,
        )

    abs_err = abs(predicted_value - appraiser_value)
    pct_err = (abs_err / appraiser_value) * 100.0
    within = None
    if price_range_low is not None and price_range_high is not None:
        within = price_range_low <= appraiser_value <= price_range_high

    return RowResult(
        row_id=row_id,
        address=address,
        appraiser_value=appraiser_value,
        predicted_value=predicted_value,
        price_range_low=price_range_low,
        price_range_high=price_range_high,
        abs_error=int(abs_err),
        pct_error=round(pct_err, 2),
        within_range=within,
        comparables_used=comparables_used,
        final_stage=final_stage,
        estimation_method=estimation_method,
        error=None,
    )


def format_markdown_report(
    *,
    metrics: AggregateMetrics,
    rows: list[RowResult],
    run_label: str,
    git_sha: Optional[str],
    api_base: str,
) -> str:
    """Render a human-friendly Markdown report for `reports/{ts}-{run_label}.md`."""

    def fmt_eur(value: Optional[int]) -> str:
        return f"{value:,} €".replace(",", ".") if value is not None else "—"

    def fmt_pct(value: Optional[float]) -> str:
        return f"{value:.2f}%" if value is not None else "—"

    lines: list[str] = []
    lines.append(f"# Evaluation Report — {run_label}")
    lines.append("")
    if git_sha:
        lines.append(f"**Git SHA:** `{git_sha}`")
    lines.append(f"**API:** `{api_base}`")
    lines.append("")
    lines.append("## Aggregate Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Rows total | {metrics.n_total} |")
    lines.append(f"| Rows evaluated | {metrics.n_evaluated} |")
    lines.append(f"| Rows failed | {metrics.n_failed} |")
    lines.append(f"| MAE | {fmt_eur(int(metrics.mae)) if metrics.mae else '—'} |")
    lines.append(f"| MAPE | {fmt_pct(metrics.mape)} |")
    lines.append(f"| Median % error | {fmt_pct(metrics.median_pct_error)} |")
    lines.append(f"| RMSE | {fmt_eur(int(metrics.rmse)) if metrics.rmse else '—'} |")
    lines.append(f"| Within range % | {fmt_pct(metrics.within_range_pct)} |")
    lines.append(f"| Bias % (signed) | {fmt_pct(metrics.bias_pct)} |")
    lines.append("")
    lines.append("## Per-row Results")
    lines.append("")
    lines.append("| # | Address | Appraiser | Predicted | Abs Err | % Err | In range | Comps | Stage | Method |")
    lines.append("|---|---------|-----------|-----------|---------|-------|----------|-------|-------|--------|")
    for r in rows:
        in_range_cell = (
            "✓" if r.within_range else ("✗" if r.within_range is False else "—")
        )
        lines.append(
            f"| {r.row_id} | {r.address[:40]} | {fmt_eur(r.appraiser_value)} | "
            f"{fmt_eur(r.predicted_value)} | {fmt_eur(r.abs_error)} | "
            f"{fmt_pct(r.pct_error)} | {in_range_cell} | "
            f"{r.comparables_used} | {r.final_stage or '—'} | {r.estimation_method or '—'} |"
        )

    failed_rows = [r for r in rows if r.predicted_value is None]
    if failed_rows:
        lines.append("")
        lines.append("## Failed Rows")
        lines.append("")
        for r in failed_rows:
            lines.append(f"- **{r.row_id}** `{r.address}` — {r.error or 'no estimate returned'}")

    return "\n".join(lines) + "\n"
