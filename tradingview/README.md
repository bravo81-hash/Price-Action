# Price Action TradingView companions

`../pa_confirm_v3.pine` is the current Pine v6 scanner companion. It includes
S1-S4, US/ASX/India benchmark templates, evidence tiers, separate detection and
authority columns, and the app's risk/time templates.

Pine uses the latest confirmed weekly pivot as support/resistance. The Python
app clusters several pivots into zones and remains authoritative for pattern
lifecycle, evidence, earnings, liquidity, option-chain enrichment and entries.

`archive/pa_confirm_v2.pine` is preserved for rollback and comparison.
`parity_fixture.json` is checked by the test suite so rule or evidence changes
flag the Pine companion for review.
