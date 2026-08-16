# Video

Screen recording of a real terminal in this repo. Silent. No `--live`. About 81 seconds.

Token: `54533043819946592547517511176940999955633860128497669742211153063842200957669`

1. Policy in one table (who wins bid/ask, last trade, closed, dead markets).
2. `python -m asof demo` — cycle 1 live wins a lagged book; cycle 2 HOLDs a later book because the market is closed; `accepting_orders` disagrees.
3. `explain` / `query` — latest cycle is HOLD, not cycle-1 LIVE.
4. `python -m asof demo --dead-cycle1` — planner halts after a dead cycle 1.
