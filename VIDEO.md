# Video shot list (~3:00)

Screen recording. No polish. Repo open, terminal visible.

| Time | Shot |
| --- | --- |
| 0:00–0:20 | Problem. Two sources, one token: CLOB book vs Gamma row. They disagree. The planner fetches; the policy writes. |
| 0:20–1:00 | `POLICY.md` table on screen. Point at: live wins fresh bid/ask; warehouse wins volume and `closed`; dead market → `R-BOOK-DEAD` HOLD on prices. No averaging. |
| 1:00–1:50 | Terminal: `python -m asof demo`. Pause on cycle 1 APPLY: `best_bid` / `best_ask` `LIVE` / `R-BOOK-LIVE` with `conflict`. Say once: catalogue `outcomePrice` is not a bid. |
| 1:50–2:40 | Same transcript, cycle 2. Planner switched token because cycle 1 was book-vs-catalogue. APPLY: `R-BOOK-DEAD` on prices, `closed` `WAREHOUSE`. Different winner class. |
| 2:40–3:00 | `python -m asof explain <cycle1>.mid` then `python -m asof explain <cycle2>.closed`. Rule ids on screen. Stop. |

If you still have fifteen seconds: one sentence on next step (websocket; LLM still cannot set fields). Do not demo `--live` unless the network is already proven that morning.
