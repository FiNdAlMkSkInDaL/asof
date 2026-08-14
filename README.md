# asof

Reconcile a live Polymarket order book with successive Gamma warehouse snapshots of the **same** outcome token. The planner fetches; `policy.reconcile` is the only writer.

No API keys. Python 3.11+. The default demo is cassette replay (no network).

## Run

```bash
python -m pip install -e ".[dev]"
pytest
python -m asof demo
```

Then:

```bash
python -m asof query 54533043819946592547517511176940999955633860128497669742211153063842200957669
python -m asof explain 54533043819946592547517511176940999955633860128497669742211153063842200957669.best_bid
python -m asof explain 54533043819946592547517511176940999955633860128497669742211153063842200957669.closed
```

Optional live run (public Polymarket HTTP, no keys). One network cycle. The closed snapshot is cassette-only; this will not splice a dead book onto a live token.

```bash
python -m asof demo --live --token <clob_token_id>
```

`python -m asof` is the supported entry point.

## Requirements (their email → this repo)

| Requirement | Where it is |
| --- | --- |
| Agent fetches from two independent sources (live feed and warehouse snapshot) | Live: CLOB `GET /book`. Warehouse: Gamma `GET /markets`. Parsers and sources in `src/asof/tools.py`. |
| Detect disagreements on at least three fields | Cycle 1 like-for-like: `best_bid`, `best_ask`, `last_trade_price` (book vs catalogue bid/ask/last trade). See `artifacts/demo-run.txt`. Catalogue `outcomePrice` is not counted as a bid. |
| Documented conflict policy, chosen and justified | `POLICY.md`. Applied only by `src/asof/policy.py`. |
| At least two full reconciliation cycles, conflicts in each | `python -m asof demo`. Same token. Cycle 1: live wins lagged bid/ask. Cycle 2: warehouse `closed` → prices HOLD the cycle-1 live values (`R-BOOK-DEAD`). |
| Logs that say which source won and why | Printed `PLAN` / `TOOL` / `OBSERVE` / `APPLY` loop; each APPLY line has winner + rule id. |
| Queryable / explainable reconciled state | SQLite in `src/asof/store.py`. `python -m asof query TOKEN`, `python -m asof explain TOKEN.field`. |
| Agent plans next steps from observations, not a fixed sequence | Pure `next_action(obs)` in `src/asof/plan.py`. If cycle 1 is already dead, it **halts** instead of fetching the closed overlay. Warehouse miss retries pinned to the live token. Two applies → halt. |
| Public repo + how to run + what I would do next | This file. |

## Authority

| Kind of field | Who wins | Why |
| --- | --- | --- |
| Bid, ask | Live, only if the book is fresh (≤2s), uncrossed, and the market is not dead | Compared to warehouse `bestBid` / `bestAsk`. |
| Mid, spread | Live, only when the book is fresh, two-sided, and uncrossed | Derived from the live book. Not from Gamma `outcomePrice`. |
| Volume, liquidity | Warehouse | Aggregates are not top-of-book size. |
| `closed`, `accepting_orders` | Warehouse | Lifecycle is official. Live CLOB `/book` does not carry these keys (live side is `None`). |
| Last trade | Newer timestamp; HOLD if the market is dead; fresh live if no clocks | Compared to warehouse `lastTradePrice`. |
| Identity mismatch | HOLD everything (`R-ID-HOLD`) | `live.token_id` must equal `warehouse.token_id`. Sibling Yes/No tokens do not merge. |

Winners are `LIVE`, `WAREHOUSE`, or `HOLD`. `HOLD` is the previous reconciled value for this token. Sources are never averaged.

## How the planner branches

`next_action` in `src/asof/plan.py` is a pure function of `Observation`. The loop in `src/asof/agent.py` only executes the action. APPLY is always `policy.reconcile`.

- No live yet → `fetch_live`.
- Live present, no warehouse → `warehouse_open`.
- Warehouse miss → retry the same snapshot pinned to `live.token_id`. Still missing → halt.
- Both present → apply.
- After apply: if live won bid/ask and the market was not dead → `warehouse_closed` (same token). **Else halt.**
- Two applies → halt.
- Live miss → halt.

## Cassettes

One CLOB book (`cassettes/live.json`). Two Gamma snapshots of that token.

A recapture on 2026-08-14 still had Gamma `bestBid`/`bestAsk`/`lastTradePrice` equal to the book. `warehouse_open.json` lags those three keys and lists them in `_asof_stub`. `warehouse_closed.json` is the same identity with `closed` / `acceptingOrders` overlaid (`_asof_stub`). Not a different market. Not a transplanted book.

Replay rebases live `as_of` to `now - 0.4s` so the 2s SLA is not vacuously stale. `captured_clock=True` uses the JSON timestamp (`R-BOOK-STALE` in unit tests).

## What I would do next

- Subscribe to the CLOB websocket instead of polling `/book`, and treat a missed heartbeat as stale (same `R-BOOK-STALE` rule).
- Persist refused identity merges as first-class rows so `query` can show “we saw this pair and would not join them.”
- Optional LLM planner behind `--llm` that may only propose the next tool call. It still cannot write fields. Not in this submission: a reviewer with no network and no model key should still get a green demo.
