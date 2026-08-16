# asof

Reconcile a **live Polymarket order book** with **Gamma warehouse snapshots** of the same outcome token.

The planner chooses what to fetch. A written policy decides which source wins each field. Sources are never averaged.

No API keys. Python 3.11+. The default demo replays committed cassettes (no network).

## Run

```bash
python -m pip install -e ".[dev]"
pytest
python -m asof demo
```

Token used throughout:

```
54533043819946592547517511176940999955633860128497669742211153063842200957669
```

```bash
python -m asof explain 54533043819946592547517511176940999955633860128497669742211153063842200957669.best_bid
python -m asof explain 54533043819946592547517511176940999955633860128497669742211153063842200957669.closed
python -m asof query 54533043819946592547517511176940999955633860128497669742211153063842200957669
python -m asof demo --dead-cycle1
```

`explain` is the **latest** cycle. After the default demo, `best_bid` is HOLD `0.169` (cycle 2), not cycle-1 LIVE.

Optional live probe (public HTTP, one cycle, does not overwrite the cassette transcript):

```bash
python -m asof demo --live --token 54533043819946592547517511176940999955633860128497669742211153063842200957669
```

## What the demo does

Two sources, one Yes token (“Will Gavin Newsom win the 2028 Democratic presidential nomination?”):

- **Live** — CLOB `GET /book` (the market now)
- **Warehouse** — Gamma `GET /markets` (official lifecycle and aggregates)

**Cycle 1.** Live book `0.169` / `0.17` against an open catalogue whose bid/ask were lagged to `0.15` / `0.16` (labelled in the JSON: on the wire those two APIs agreed, so a stubbed warehouse is what makes the bid/ask rules visible). Last trade is a real one-tick gap: CLOB `0.169` vs Gamma `0.17`. Live wins the book (`R-BOOK-LIVE`).

**Cycle 2.** The planner refetches a **later** live book (`0.161` / `0.164`) and applies a closed overlay of the same token. The market is dead, so prices **HOLD** at cycle-1’s `0.169` (`R-BOOK-DEAD`). The new disagreement is lifecycle: the book is still quoting, the catalogue says not accepting. Warehouse wins `accepting_orders`. Live has no `closed` key — that dash is missing data, not a fight.

`--dead-cycle1` is the other branch: the open fetch already returns the closed row, so the planner **halts** after one apply.

## Who wins

Full table and rule ids: [`POLICY.md`](POLICY.md). Short version:

| Field | Winner | Why |
| --- | --- | --- |
| Bid, ask | Live if the book is fresh, uncrossed, and the market is open; otherwise HOLD | Compared to catalogue `bestBid` / `bestAsk`, not `outcomePrice` |
| Last trade | Newer clock; HOLD if dead; live if there are prices but no clocks | Compared to `lastTradePrice` |
| Volume, liquidity | Warehouse | Aggregates are not top-of-book size |
| `closed` | Warehouse | Live `/book` does not carry this key |
| `accepting_orders` | Warehouse | Live side is whether the book is still quoting |
| Identity mismatch | HOLD everything | Live token must equal warehouse token |

`HOLD` is the previous reconciled value for this token. Never `0.5 × live + 0.5 × warehouse`.

A book is “fresh” only if it is ≤2 seconds old. Cassette replay sets live `as_of` to `now − 0.4s` so that rule is not vacuously stale; the captured timestamp stays in the JSON.

## How it decides what to fetch next

`next_action` in `src/asof/plan.py` is a pure function of what has been observed. The loop in `src/asof/agent.py` only executes that action. The only writer is `policy.reconcile`.

No live yet → fetch the book. No warehouse yet → fetch snapshot `open`. Miss → retry pinned to the live token, then halt. After a live book win, refetch live and fetch snapshot `closed`. Already dead after cycle 1 → halt. Two applies → halt. `--live` has no closed snapshot → halt after one cycle.

## Cassettes

Committed under `cassettes/`. Details in [`cassettes/README.md`](cassettes/README.md).

Stubbed warehouse is allowed. Bid/ask on the open row are labelled lags. The closed row only stubs `closed` / `acceptingOrders`; its bid/ask are the first capture’s real catalogue BBO. `live_c2.json` is an unmodified later CLOB book.

## What I would do next

- Subscribe to the CLOB websocket and treat a missed heartbeat as stale (same `R-BOOK-STALE` rule).
- Persist refused identity merges so `query` can show “we saw this pair and would not join them.”
- Optional LLM planner behind `--llm` that may only propose the next tool call. It still cannot write fields. Not in this submission: a reviewer with no network and no model key should still get a green demo.
