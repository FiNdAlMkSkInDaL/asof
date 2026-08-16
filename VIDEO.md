# Video

Screen recording of a real terminal in this repo. Silent. No `--live`. About 63 seconds.

Token: `54533043819946592547517511176940999955633860128497669742211153063842200957669`

1. `Get-Content POLICY.md` — authority plus the field table (who writes, who wins).
2. `python -m asof demo` — open lag `0.15`/`0.16` stays on screen. Cycle 1 live wins that lagged book. Cycle 2 HOLDs a later book (`0.161` vs `0.169`) because the market is closed; quoting vs not accepting.
3. `explain` / `query` — latest cycle is HOLD, not cycle-1 LIVE.
4. `python -m asof demo --dead-cycle1` — if cycle 1 is already dead, the planner halts.
