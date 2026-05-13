# Market Transactions Layer

## Purpose

This project now exposes a second market-data layer focused on recent transactions, separate from the current Idealista listing comparables.

The first implementation is **display-first** and **mocked**:

- the main valuation still uses Idealista asking-price comparables;
- the new market-transactions block adds context for asking vs closing analysis;
- and the negotiation margin is shown as a market signal, not yet applied to `estimated_value`.

## Response Shape

`POST /api/valuation` can now return an optional `market_transactions` block:

```json
{
  "market_transactions": {
    "summary": {
      "total_transactions": 6,
      "avg_asking_price": 512000,
      "avg_closing_price": 478000,
      "avg_asking_price_per_m2": 5400,
      "avg_closing_price_per_m2": 5040,
      "asking_vs_closing_gap_pct": 6.3,
      "negotiation_margin_pct": 6.3,
      "sample_size": 6,
      "chart_series": [
        {
          "label": "Calle Mayor 12",
          "asking_price": 530000,
          "closing_price": 494000,
          "negotiation_margin_pct": 6.8
        }
      ]
    },
    "transactions": [
      {
        "id": "txn-madrid-1",
        "address": "Calle Mayor 12, Madrid",
        "m2": 94,
        "bedrooms": 3,
        "bathrooms": 2,
        "asking_price": 530000,
        "closing_price": 494000,
        "asking_price_per_m2": 5638,
        "closing_price_per_m2": 5255,
        "negotiation_margin_pct": 6.8,
        "close_date": "2026-03-12",
        "days_on_market": 41,
        "source": "market-mock",
        "distance_m": 420
      }
    ]
  }
}
```

## Frontend Usage

The frontend renders this block as a dedicated section between:

1. the main estimated value card; and
2. the Idealista comparables grid.

That section contains:

- summary KPI cards;
- an asking-vs-closing chart;
- and recent transaction cards, including close date and time to sell.

## Future Integration

This contract is designed so the mock generator can later be replaced by:

- external market-transactions providers;
- internal PropHero transaction data;
- or a blended valuation model that adjusts `estimated_value` using negotiation margin.
