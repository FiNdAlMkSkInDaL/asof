# Authority

Two sources describe the same Polymarket outcome token.

- **Live** is the CLOB order book (`GET /book`). It is the market *now*.
- **Warehouse** is the Gamma catalogue row (`GET /markets`). It is official lifecycle and aggregates.

The planner may fetch, retry, and choose which token to reconcile next. It cannot write a field. `policy.reconcile` is the only writer. Winners are `LIVE`, `WAREHOUSE`, or `HOLD`. Sources are never averaged.

Freshness SLA: a book is live-privileged only if `now - book.as_of ≤ 2` seconds.

## Field table

| Field | Winner | Rule | Why |
| --- | --- | --- | --- |
| `token_id`, `condition_id` | `WAREHOUSE` if identity matches; else `HOLD` | `R-LIFE-WAREHOUSE` / `R-ID-HOLD` | Canonical keys come from the catalogue. If the two rows are not the same entity, refuse the merge. Identity is not votable. |
| `best_bid`, `best_ask` | `LIVE` if the book is fresh, two-sided or that side exists, uncrossed, and the market is not dead; else `HOLD` | `R-BOOK-LIVE` / `R-BOOK-STALE` / `R-BOOK-CROSSED` / `R-BOOK-ONE-SIDED` / `R-BOOK-DEAD` | The book is the only source that is the market right now. A lagged catalogue price is not a bid. |
| `mid`, `spread` | `LIVE` only when the book is fresh, two-sided, and uncrossed; else `HOLD` | `R-BOOK-LIVE` / `R-BOOK-ONE-SIDED` / `R-BOOK-STALE` / `R-BOOK-CROSSED` / `R-BOOK-DEAD` | Mid and spread are derived. Do not invent them from one side or from Gamma `outcomePrice`. |
| `last_trade_price` | Newer timestamp wins. If the market is dead, `HOLD`. If there is no timestamp pair and live is not fresh, `HOLD`. | `R-TRADE-NEWER` / `R-BOOK-DEAD` / `R-BOOK-STALE` | A trade is an event. Recency is the meaning of the field. |
| `volume`, `liquidity` | `WAREHOUSE` | `R-AGG-WAREHOUSE` | Aggregates are computed off the book. Top-of-book size is logged as live, not stored as truth. |
| `closed`, `accepting_orders` | `WAREHOUSE` | `R-LIFE-WAREHOUSE` | Lifecycle is official. A still-quoting book does not reopen a closed market. |

Warehouse `outcomePrice` is compared to live bid/ask/mid so disagreements are visible. It never wins those fields.

## Rule ids

| Id | When it fires |
| --- | --- |
| `R-ID-HOLD` | Live token/condition does not match the warehouse row. Every field is `HOLD`. |
| `R-BOOK-LIVE` | Fresh (≤2s), uncrossed book. Bid/ask that exist, and mid/spread if two-sided, take live. |
| `R-BOOK-STALE` | Book age exceeds 2s. Live does not get live privileges. Trade price also `HOLD` if there is no timestamp pair. |
| `R-BOOK-CROSSED` | `best_bid >= best_ask`. Corrupt, not newer. |
| `R-BOOK-ONE-SIDED` | Missing bid or ask. Do not invent that side, mid, or spread. |
| `R-BOOK-DEAD` | Warehouse `closed` is true or `accepting_orders` is false. Do not apply live prices or last trade. |
| `R-TRADE-NEWER` | Last trade: newer timestamp wins; if warehouse has no trade time and live is fresh, live wins. |
| `R-AGG-WAREHOUSE` | `volume` and `liquidity` always warehouse. |
| `R-LIFE-WAREHOUSE` | Matching identity keys, `closed`, and `accepting_orders` always warehouse. |

## Three laws

1. **No blending.** Never `0.5 × live + 0.5 × warehouse`. A split brain is a decision plus a log line.
2. **Stale live loses live privileges.** If the book is older than the SLA, price rules do not fire as `LIVE`.
3. **Unruled fields are not invented.** `reconcile` only emits the fields in the table. A new key from an API is ignored until a rule is added here and in `policy.py`.

## Cassette splice (cycle 2)

Cycle 1 cassettes are unmodified public CLOB and Gamma payloads for an open market.

Cycle 2 warehouse is an unmodified Gamma row for a **closed** market. Closed markets often have no restable book. The cycle 2 live file is a real CLOB `/book` payload with `asset_id` and `market` rewritten to that closed market’s token and condition id so the planner can show `R-BOOK-DEAD` without inventing prices. The book levels themselves are untouched captured data. See `cassettes/README.md`.
