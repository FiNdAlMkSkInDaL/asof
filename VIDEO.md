# Video

Screen recording of a real terminal in this repo. Silent. No `--live`. About 135 seconds.

Token: `54533043819946592547517511176940999955633860128497669742211153063842200957669`

1. `POLICY.md` — authority, field table, rule ids (who writes, who wins, and why).
2. `python -m asof demo` — open lag `0.15`/`0.16` and later book `0.161`/`0.164` stay on screen. Cycle 1 live wins the lagged book. Cycle 2 HOLDs because the market is closed; quoting vs not accepting.
3. `explain` — latest cycle is HOLD `0.169`, not cycle-1 LIVE. Also `closed` and `accepting_orders`.
4. `query` — same latest row.
5. `python -m asof demo --dead-cycle1` — if cycle 1 is already dead, the planner halts.
6. `python -m pytest -v -k …` — named edges the demo does not run: identity HOLD, sibling refuse, crossed book, stale SLA, no averaging.
