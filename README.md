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

Optional live run (public Polymarket HTTP, no keys). One network cycle on the **Yes** token from the cassette. Gamma `bestBid`/`bestAsk` are market-level (the Yes book). Writes `artifacts/live-run.txt`; does not overwrite the committed cassette transcript. Typically **no** bid/ask fights — that is why those two catalogue keys are lagged. Capture-time last trade already differed by one tick (kept).

```bash
python -m asof demo --live --token <clob_token_id>
```

`python -m asof` is the supported entry point.

## Requirements (their email → this repo)

| Requirement | Where it is |
| --- | --- |
| Agent fetches from two independent sources (live feed and warehouse snapshot) | Live: CLOB `GET /book`. Warehouse: Gamma `GET /markets`. Parsers and sources in `src/asof/tools.py`. |
| Detect disagreements on at least three fields | Cassette cycle 1 like-for-like: `best_bid` and `best_ask` (lagged in `_asof_stub` because later wire BBO agreed) plus `last_trade_price` (capture-time tick: CLOB `0.169` vs Gamma `0.17`). See Cassettes below. Catalogue `outcomePrice` is not a bid. |
| Documented conflict policy, chosen and justified | `POLICY.md`. Applied only by `src/asof/policy.py`. |
| At least two full reconciliation cycles, conflicts in each | `python -m asof demo` (cassettes). Same token. Cycle 1: live wins lagged bid/ask; last trade is the capture tick. Cycle 2 proof is HOLD of cycle-1 live `best_bid` `0.169` (`R-BOOK-DEAD`), not a new price fight. Live `closed` is `None`. `--live` is one network cycle. |
| Logs that say which source won and why | Printed `PLAN` / `TOOL` / `OBSERVE` / `APPLY` loop; each APPLY line has winner + rule id. |
| Queryable / explainable reconciled state | SQLite in `src/asof/store.py`. `python -m asof query TOKEN`, `python -m asof explain TOKEN.field`. |
| Agent plans next steps from observations, not a fixed sequence | Pure `next_action(obs)` in `src/asof/plan.py`. Miss/dead/open-only **halts are unit-tested** (`tests/test_agent.py`; `artifacts/branch-run.txt` is the dead-cycle-1 halt). The default `python -m asof demo` cassette path is always live-win then closed overlay. |
| Public repo + how to run + what I would do next | This file. |

## Authority

| Kind of field | Who wins | Why |
| --- | --- | --- |
| Bid, ask | Live, only if the book is fresh (≤2s), uncrossed, and the market is not dead | Compared to warehouse `bestBid` / `bestAsk`. |
| Mid, spread | Live, only when the book is fresh, two-sided, and uncrossed | Derived from the live book. Not from Gamma `outcomePrice`. Not counted as a conflict. |
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
- After apply: if live won bid/ask, the market was not dead, and the source has a `closed` snapshot → refetch live, then `warehouse_closed` (same token). If the source has no `closed` snapshot (`--live`), **halt**.
- Two applies → halt.
- Live miss → halt.

## Cassettes

The cassette path is the submission. `--live` is optional proof the public APIs exist.

One CLOB book (`cassettes/live.json`). Two Gamma snapshots of that **same** Yes token.

On 2026-08-14 (and 2026-08-15) live CLOB `/book` and Gamma `/markets` for this token **agreed** on bid/ask (and recapture last trade matched the book). A `--live` run therefore shows no bid/ask fights. `warehouse_open.json` lags `bestBid` / `bestAsk` (`_asof_stub`) so those rules can be shown. Capture-time last trade already differed: CLOB `0.169` vs Gamma `0.17`; that captured Gamma value is kept. `warehouse_closed.json` is the same identity with `closed` / `acceptingOrders` overlaid (`_asof_stub`, including inherited lagged bid/ask). Cycle 2’s new fact is that overlay. The second-cycle proof is HOLD of cycle-1 live `best_bid` `0.169`, not a second price observation. Live `closed` is `None`. Not a different market. Not a transplanted book.

Replay rebases live `as_of` to `now - 0.4s` so the 2s SLA is not vacuously stale. Unit tests may pass `captured_clock=True`. Cassette last-trade rows have prices and no trade clocks; `R-TRADE-NEWER` then means “fresh live, no timestamp pair,” which the APPLY reason states.

A reviewer who wants the dead-cycle-1 halt without reading tests can cat `artifacts/branch-run.txt`.

## What I would do next

- Subscribe to the CLOB websocket instead of polling `/book`, and treat a missed heartbeat as stale (same `R-BOOK-STALE` rule).
- Persist refused identity merges as first-class rows so `query` can show “we saw this pair and would not join them.”
- Optional LLM planner behind `--llm` that may only propose the next tool call. It still cannot write fields. Not in this submission: a reviewer with no network and no model key should still get a green demo.
