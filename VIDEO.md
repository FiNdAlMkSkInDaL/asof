# Video shot list (~3:00)

Screen recording. No polish. Repo open, terminal visible.

| Time | Shot |
| --- | --- |
| 0:00–0:20 | Problem. One token, two sources: CLOB book vs Gamma row. Same entity, successive warehouse snapshots. The planner fetches; the policy writes. |
| 0:20–1:00 | `POLICY.md` table. Point at: bid/ask compared to catalogue `bestBid`/`bestAsk`, not `outcomePrice`. Warehouse wins `closed`. Dead market → HOLD last live prices. No averaging. |
| 1:00–1:50 | `python -m asof demo`. Pause on cycle 1 APPLY: `best_bid` `LIVE` / `R-BOOK-LIVE` **conflict** (0.169 vs 0.15). Say: bid/ask are a labelled lag because later wire BBO agreed. Last trade on capture was already `0.169` vs `0.17`. Replay rebases `as_of`. |
| 1:50–2:40 | Same token, cycle 2. Closed overlay is labelled. Proof is `best_bid` HOLD **0.169** (`R-BOOK-DEAD`), not a new price fight. Live `closed` is `-`. `closed` WAREHOUSE true. |
| 2:40–3:00 | `python -m asof explain <token>.best_bid` then `python -m asof explain <token>.closed`. Say once: explain is the **latest** cycle, so bid shows HOLD not LIVE. Stop. |

Do not explain `.mid`. Do not run `--live` in the recording. If you already did, run `python -m asof demo` again so `artifacts/demo-run.txt` matches this shot list.
