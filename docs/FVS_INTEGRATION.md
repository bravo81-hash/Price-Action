# Forward-Vol-Scanner context feed

The US scan publishes `data/fvs_feed.json` as a compact, versioned interface for
Forward-Vol-Scanner. It is a one-way research feed: Price-Action contributes
market regime and per-ticker signal context, while Forward-Vol-Scanner remains
the sole authority for its shortlist, exact option legs, liquidity checks, risk
governor and untransmitted TWS staging.

## Contract

- `schema_version`: currently `1`.
- `authority`: always `context_only`.
- `generated`: UTC generation timestamp used for freshness checks.
- `bench`: reduced SPY regime context.
- `rows`: US ticker signals with signal/evidence metadata and technical context.

The feed intentionally contains no order instructions, option structure
recommendations, live quotes or portfolio permissions. S1/S2 are directional
context only, S3 is neutral research context, and S4 remains experimental.

Consumers must validate the schema, market, authority and timestamp, fail open
when the feed is unavailable or stale, and must not treat Price-Action context as
permission to rank, stage or transmit a trade.
