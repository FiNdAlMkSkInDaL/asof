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
python -m asof demo --dead-cycle1
```

`explain` is the **latest** cycle. After this demo, `best_bid` is HOLD `0.169` / `R-BOOK-DEAD` (cycle 2), not cycle-1 LIVE.

Optional live run (public Polymarket HTTP, no keys). One network cycle on the **Yes** token from the cassette. Gamma `bestBid`/`bestAsk` are market-level (the Yes book). Writes `artifacts/live-run.txt`; does not overwrite the committed cassette transcript. Typically **no** bid/ask fights — that is why those two catalogue keys are lagged. Capture-time last trade already differed by one tick (kept).

```bash
python -m asof demo --live --token <clob_token_id>
```

`python -m asof` is the supported entry point.

## Requirements (their email → this repo)

| Requirement | Where it is |
| --- | --- |
| Agent fetches from two independent sources (live feed and warehouse snapshot) | Live: CLOB `GET /book`. Warehouse: Gamma `GET /markets`. Parsers and sources in `src/asof/tools.py`. |
| Detect disagreements on at least three fields | Cycle 1 APPLY: lagged `best_bid`/`best_ask` (`_asof_stub`, because capture-time wire BBO agreed) plus capture-time `last_trade_price` (CLOB `0.169` vs Gamma `0.17`). Catalogue `outcomePrice` is not a bid. |
| Documented conflict policy, chosen and justified | `POLICY.md`. Applied only by `src/asof/policy.py`. |
| At least two full reconciliation cycles, conflicts in each | Two APPLY cycles on the same token. Cycle 1: stubbed book plus last-trade tick. Cycle 2: a later live book (`live_c2.json`) vs the first catalogue's real BBO (`0.169`/`0.17`, not the `0.15`/`0.16` stub), HOLD because `closed`, and `accepting_orders` conflict (`quoting` true vs accepting false). Missing live `closed` is not a two-source fight. `--live` is one network cycle. |
| Logs that say which source won and why | Printed `PLAN` / `TOOL` / `OBSERVE` / `APPLY` loop; each APPLY line has winner + rule id. |
| Queryable / explainable reconciled state | SQLite in `src/asof/store.py`. `python -m asof query TOKEN`, `python -m asof explain TOKEN.field`. |
| Agent plans next steps from observations, not a fixed sequence | Pure `next_action(obs)` in `src/asof/plan.py`. Default `python -m asof demo` is live-win then closed overlay. `python -m asof demo --dead-cycle1` serves the closed row on the open fetch so cycle 1 is dead and the planner **halts** (same adapter as `tests/test_agent.py`). Writes `artifacts/branch-run.txt`; does not overwrite `demo-run.txt`. |
| Public repo + how to run + what I would do next | This file. |

## Authority

| Kind of field | Who wins | Why |
| --- | --- | --- |
| Bid, ask | Live, only if the book is fresh (≤2s), uncrossed, and the market is not dead | Compared to warehouse `bestBid` / `bestAsk`. |
| Mid, spread | Live, only when the book is fresh, two-sided, and uncrossed | Derived from the live book. Not from Gamma `outcomePrice`. Not counted as a conflict. |
| Volume, liquidity | Warehouse | Aggregates are not top-of-book size. |
| `closed` | Warehouse | Lifecycle is official. Live CLOB `/book` does not carry `closed` (live side is `None`). |
| `accepting_orders` | Warehouse | Warehouse `acceptingOrders`. Live side is `quoting` (book still has a ladder). |
| Last trade | Newer timestamp; HOLD if the market is dead; fresh live if no clocks (`R-TRADE-LIVE-NOCLOCK`, not recency) | Compared to warehouse `lastTradePrice`. |
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

One CLOB book (`cassettes/live.json`) plus a later book (`cassettes/live_c2.json`) for the refetch. Two Gamma snapshots of that **same** Yes token.

On 2026-08-14 live CLOB `/book` and Gamma `/markets` for this token **agreed** on bid/ask. A `--live` run on a quiet tape therefore showed no bid/ask fights. `warehouse_open.json` lags `bestBid` / `bestAsk` (`_asof_stub`) so those rules can be shown. Capture-time last trade already differed: CLOB `0.169` vs Gamma `0.17`; that captured Gamma value is kept. `warehouse_closed.json` overlays `closed` / `acceptingOrders` (`_asof_stub`) and keeps the first capture's real catalogue BBO (`0.169`/`0.17`), not the open lag. Cycle 2 refetches `live_c2.json` (book moved to `0.161`/`0.164` on 2026-08-16; Gamma agreed with that later book). HOLD of cycle-1 live `best_bid` `0.169` (`R-BOOK-DEAD`). The new Cycle 2 fight is `quoting` vs `accepting_orders` false. Live `closed` is `None`. Not a different market. Not a transplanted book.

Replay rebases live `as_of` to `now - 0.4s` so the 2s SLA is not vacuously stale. Unit tests may pass `captured_clock=True`. Cassette last-trade rows have prices and no trade clocks; that APPLY is `R-TRADE-LIVE-NOCLOCK`, not recency.

`python -m asof demo --dead-cycle1` is the halt path. It uses `DeadOpenSource` (closed cassette row on the `open` fetch). Do not cat a frozen transcript in place of running it.

## What I would do next

- Subscribe to the CLOB websocket instead of polling `/book`, and treat a missed heartbeat as stale (same `R-BOOK-STALE` rule).
- Persist refused identity merges as first-class rows so `query` can show “we saw this pair and would not join them.”
- Optional LLM planner behind `--llm` that may only propose the next tool call. It still cannot write fields. Not in this submission: a reviewer with no network and no model key should still get a green demo.
