# asof

Reconcile a live Polymarket order book with a Gamma warehouse row. The planner fetches; `policy.reconcile` is the only writer.

No API keys. Python 3.11+. The default demo is cassette replay (no network).

## Run

```bash
python -m pip install -e ".[dev]"
pytest
python -m asof demo
```

Then, using the token ids printed at the end of the transcript:

```bash
python -m asof query 54533043819946592547517511176940999955633860128497669742211153063842200957669
python -m asof explain 54533043819946592547517511176940999955633860128497669742211153063842200957669.mid
python -m asof explain 53135072462907880191400140706440867753044989936304433583131786753949599718775.closed
```

Optional live run (public Polymarket HTTP, no keys):

```bash
python -m asof demo --live --token <clob_token_id> [--token-cycle2 <other_token_id>]
```

`python -m asof` is the supported entry point. A console script named `asof` is also installed.

## Requirements (their email → this repo)

| Requirement | Where it is |
| --- | --- |
| Agent fetches from two independent sources (live feed and warehouse snapshot) | Live: CLOB `GET /book`. Warehouse: Gamma `GET /markets`. Parsers and sources in `src/asof/tools.py`. |
| Detect disagreements on at least three fields | Cycle 1: `best_bid`, `best_ask`, `last_trade_price`, `liquidity`. Cycle 2: book prices vs a closed catalogue, plus `closed`. See `artifacts/demo-run.txt`. |
| Documented conflict policy, chosen and justified | `POLICY.md`. Applied only by `src/asof/policy.py`. |
| At least two full reconciliation cycles, conflicts in each | `python -m asof demo`. Cycle 1 is microstructure (live wins bid/ask). Cycle 2 is lifecycle (`R-BOOK-DEAD` / warehouse `closed`). |
| Logs that say which source won and why | Printed `PLAN` / `TOOL` / `OBSERVE` / `APPLY` loop; each APPLY line has winner + rule id. |
| Queryable / explainable reconciled state | SQLite in `src/asof/store.py`. `asof query TOKEN`, `asof explain TOKEN.field`. |
| Agent plans next steps from observations, not a fixed sequence | `src/asof/agent.py`. Branches below. |
| Public repo + how to run + what I would do next | This file. |

## Authority

| Kind of field | Who wins | Why |
| --- | --- | --- |
| Bid, ask, mid, spread | Live, only if the book is fresh (≤2s), uncrossed, and the market is not dead | The book is the market now. Gamma `outcomePrice` is a lagged catalogue number. |
| Volume, liquidity | Warehouse | Aggregates are not top-of-book size. |
| `closed`, `accepting_orders` | Warehouse | Lifecycle is official. A quoting book does not reopen a closed market. |
| Last trade | Newer timestamp; HOLD if the market is dead | A trade is an event. Recency is the meaning of the field. |
| Identity mismatch | HOLD everything (`R-ID-HOLD`) | Not the same entity. Refuse the merge. |

Winners are `LIVE`, `WAREHOUSE`, or `HOLD`. Sources are never averaged. Rule ids: `R-ID-HOLD`, `R-BOOK-LIVE`, `R-BOOK-STALE`, `R-BOOK-CROSSED`, `R-BOOK-ONE-SIDED`, `R-BOOK-DEAD`, `R-TRADE-NEWER`, `R-AGG-WAREHOUSE`, `R-LIFE-WAREHOUSE`.

## How the planner branches

The loop is always `PLAN` → `TOOL` → `OBSERVE` → `APPLY`. APPLY is `policy.reconcile`. The planner never calls `set_field`.

- Warehouse miss on token id → retry `fetch_warehouse(condition_id)`.
- Identity mismatch → still APPLY; policy records `R-ID-HOLD` on every field. That is a refuse, not a merge.
- After cycle 1, if live won book prices and the market was not dead → fetch `cycle2_token()` (a closed market). That is a different entity, chosen because the first fight was book-vs-catalogue, not a replay of the same token.
- Stale live still APPLY. Policy emits `R-BOOK-STALE`. The planner does not pretend live won.

Two cycles minimum. Cassette cycle 2 uses a real closed Gamma row plus a documented splice of a real CLOB book shape (`POLICY.md`, `cassettes/README.md`). Closed books are often unrestorable; the splice exists so `R-BOOK-DEAD` is visible.

## What I would do next

- Subscribe to the CLOB websocket instead of polling `/book`, and treat a missed heartbeat as stale (same `R-BOOK-STALE` rule).
- Persist refused identity merges as first-class rows so `query` can show “we saw this pair and would not join them.”
- Optional LLM planner behind `--llm` that may only propose the next tool call. It still cannot write fields. Not in this submission: a reviewer with no network and no model key should still get a green demo.
