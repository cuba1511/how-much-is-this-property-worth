# how-much-is-this-property-worth

## Quick start

```bash
make install
make db
make dev
```

- API: http://localhost:8001  
- UI: http://localhost:5173  

See [docs/structure.md](docs/structure.md) for folder layout, env files, and what to ignore at the repo root.

## Project Description

`how-much-is-this-property-worth` is a residential property valuation tool focused on sale price estimation. The goal is to estimate what a property is worth today based on market evidence in the surrounding area, answering a simple owner question: **"How much is this property worth, and how much could I sell it for today?"**

The core flow starts from the property address. From that location, the system looks for comparable properties, recent transactions, and local market signals to calculate a current sale price estimate using nearby references and similar asset characteristics.

## How It Works

The user enters the property address and the system:

1. identifies the property's location;
2. finds nearby comparables;
3. filters them by relevant characteristics such as square meters, bedrooms, and bathrooms;
4. combines comparable listings with recent closings and local market behavior;
5. generates an estimated current sale price.

## Valuation Logic

The valuation is based on geographic comparables and transactions. The geographic reference can be defined using:

- a radius around the property;
- a census tract;
- and, if broader coverage is needed, larger areas such as district or municipality.

The product should always prioritize the closest relevant geography possible so the estimate reflects the real market for that specific property.

The valuation model is designed as a combination of:

- comparable properties in the same micro-market;
- recent closing transactions;
- the gap between asking price and closing price, used as a negotiation margin signal;
- and time-to-sell behavior by product type.

This means the estimate should not rely only on listed prices, but also on how the market is actually closing and how quickly similar properties are selling.

## Planned Outputs

Beyond the core valuation, the product direction also includes structured outputs such as:

- sale and rental reports;
- downloadable charts in `PNG` and `JPG`;
- CSV export with the underlying data;
- AI-generated reports;
- commercial API reports;
- and local broker intelligence, such as the top brokers in a given area and how many properties they have sold there.

## Product Roadmap

### Current Phase

Sale price estimation: how much a property could be sold for today, based on nearby comparables, recent transactions, negotiation margin signals, and local selling velocity.

### Phase 1

Rental estimation: how much the property could be rented for today.

### Phase 2

Potential return estimation, adding extra inputs such as:

- purchase price;
- transfer tax (`ITP`);
- other relevant transaction costs.
