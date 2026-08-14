# Authority

Two sources describe the **same** Polymarket outcome token, over successive warehouse snapshots.

- **Live** is the CLOB order book (`GET /book`). It is the market *now*.
- **Warehouse** is a Gamma catalogue row (`GET /markets`). It is official lifecycle and aggregates. The demo applies two snapshots of that same row: an open (lagged) catalogue, then a closed overlay.

The planner may fetch, retry, and choose the next snapshot from observations. It cannot write a field. `policy.reconcile` is the only writer. Winners are `LIVE`, `WAREHOUSE`, or `HOLD`. Sources are never averaged.

Freshness SLA: a book is live-privileged only if `now - book.as_of ≤ 2` seconds.

Cassette replay rebases live `as_of` to `now - 0.4s` so the demo is not vacuously stale. The captured CLOB timestamp is still in the JSON. A planner action / unit test may request `captured_clock=True` to exercise `R-BOOK-STALE`. That rebase is not a claim that the book is 0.4s old in the real world.

## Field table

| Field | Winner | Rule | Why |
| --- | --- | --- | --- |
| `token_id`, `condition_id` | `WAREHOUSE` if identity matches; else `HOLD` | `R-LIFE-WAREHOUSE` / `R-ID-HOLD` | Canonical keys come from the catalogue. Identity is `live.token_id == warehouse.token_id` after the outcome is resolved. Sibling clob token ids are not a merge key. |
| `best_bid`, `best_ask` | `LIVE` if the book is fresh, that side exists, uncrossed, and the market is not dead; else `HOLD` | `R-BOOK-LIVE` / `R-BOOK-STALE` / `R-BOOK-CROSSED` / `R-BOOK-ONE-SIDED` / `R-BOOK-DEAD` | Compared to warehouse `bestBid` / `bestAsk`. A lagged catalogue bid is still a bid. Gamma `outcomePrice` is not a bid. |
| `mid`, `spread` | `LIVE` only when the book is fresh, two-sided, and uncrossed; else `HOLD` | `R-BOOK-LIVE` / `R-BOOK-ONE-SIDED` / `R-BOOK-STALE` / `R-BOOK-CROSSED` / `R-BOOK-DEAD` | Derived from the live book. Warehouse mid, if both catalogue bid and ask exist, is context only — never invented from `outcomePrice`. |
| `last_trade_price` | Newer timestamp wins. If the market is dead, `HOLD`. If there is no timestamp pair and live is not fresh, `HOLD`. If there is no timestamp pair and live is fresh, live wins. | `R-TRADE-NEWER` / `R-BOOK-DEAD` / `R-BOOK-STALE` | Compared to warehouse `lastTradePrice`. Recency is the meaning of the field. Cassette payloads often have prices and no trade clocks; the timestamp branch is proven in `tests/test_policy.py`. |
| `volume`, `liquidity` | `WAREHOUSE` | `R-AGG-WAREHOUSE` | Aggregates are not top-of-book size. Top-of-book size may be logged as live. It is not a like-for-like disagreement with catalogue liquidity. |
| `closed`, `accepting_orders` | `WAREHOUSE` | `R-LIFE-WAREHOUSE` | Lifecycle is official. Live is `None` unless the live payload actually carries those keys. A missing live side is not a two-source conflict. |

`HOLD` means the previous reconciled value for **this token**. An empty previous is an empty HOLD, not a guess.

## Rule ids

| Id | When it fires |
| --- | --- |
| `R-ID-HOLD` | Live token does not equal the warehouse token, or conditions differ. Every field is `HOLD`. |
| `R-BOOK-LIVE` | Fresh (≤2s), uncrossed book. Bid/ask that exist, and mid/spread if two-sided, take live. |
| `R-BOOK-STALE` | Book age exceeds 2s. Live does not get live privileges. Trade price also `HOLD` if there is no timestamp pair. |
| `R-BOOK-CROSSED` | `best_bid >= best_ask`. Corrupt, not newer. |
| `R-BOOK-ONE-SIDED` | Missing bid or ask. Do not invent that side, mid, or spread. |
| `R-BOOK-DEAD` | Warehouse `closed` is true or `accepting_orders` is false. Do not apply live prices or last trade. |
| `R-TRADE-NEWER` | Last trade: newer timestamp wins; if there is no timestamp pair and live is fresh, live wins. |
| `R-AGG-WAREHOUSE` | `volume` and `liquidity` always warehouse. |
| `R-LIFE-WAREHOUSE` | Matching identity keys, `closed`, and `accepting_orders` always warehouse. |

## Three laws

1. **No blending.** Never `0.5 × live + 0.5 × warehouse`. A split brain is a decision plus a log line.
2. **Stale live loses live privileges.** If the book is older than the SLA, price rules do not fire as `LIVE`.
3. **Unruled fields are not invented.** `reconcile` only emits the fields in the table. A new key from an API is ignored until a rule is added here and in `policy.py`.

## Cassettes (same entity)

Both warehouse snapshots are the same outcome token as `cassettes/live.json`.

- `warehouse_open.json` is a captured Gamma row. Where the live catalogue bid/ask/last trade still matched the CLOB book, those like-for-like keys are lagged and listed in `_asof_stub`. The rest of the row is unmodified capture.
- `warehouse_closed.json` is that same identity with `closed: true` and `acceptingOrders: false`, listed in `_asof_stub`. It is not a different market and not a transplanted book.

See `cassettes/README.md`.
