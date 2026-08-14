# Video shot list (~3:00)

Screen recording. No polish. Repo open, terminal visible.

| Time | Shot |
| --- | --- |
| 0:00–0:20 | Problem. One token, two sources: CLOB book vs Gamma row. Same entity, successive warehouse snapshots. The planner fetches; the policy writes. |
| 0:20–1:00 | `POLICY.md` table. Point at: bid/ask compared to catalogue `bestBid`/`bestAsk`, not `outcomePrice`. Warehouse wins `closed`. Dead market → HOLD last live prices. No averaging. |
| 1:00–1:50 | `python -m asof demo`. Pause on cycle 1 APPLY: `best_bid` `LIVE` / `R-BOOK-LIVE` **conflict** (0.169 vs 0.15). Say: those are like-for-like bids. One sentence: open catalogue prices are a labelled lag (`_asof_stub`); replay rebases `as_of`. |
| 1:50–2:40 | Same token, cycle 2. Planner asked for the closed snapshot because cycle 1 was a live book win. APPLY: `R-BOOK-DEAD`, `best_bid` HOLD **0.169** (not empty). `closed` WAREHOUSE. One sentence: closed overlay is labelled; not a different market. |
| 2:40–3:00 | `python -m asof explain <token>.best_bid` then `python -m asof explain <token>.closed`. Rule ids on screen. Stop. |

Do not explain `.mid`. Do not run `--live` in the recording. If you already did, run `python -m asof demo` again so `artifacts/demo-run.txt` matches this shot list.
