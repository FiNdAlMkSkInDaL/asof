# Video shot list (≤3:00)

Screen recording of a real PowerShell / Windows Terminal session in this repo. No studio. No `--live`. Silent; yellow lines are the walkthrough. No fake `PS>` prompts. No `_record/print_slice.py`. No `Get-Content` of a halt transcript.

File: local screen recording (not in git). **~81s**, silent. Windows Terminal, not a studio.

Token:

`54533043819946592547517511176940999955633860128497669742211153063842200957669`

| Time | Shot |
| --- | --- |
| 0:00–0:06 | Cassette replay, no network. C1: lagged book plus last-trade tick. C2: later live book, HOLD because closed, quoting vs not accepting. |
| 0:06–0:14 | POLICY table: bid/ask vs `bestBid`/`bestAsk` not `outcomePrice`; warehouse owns `closed`; `accepting_orders` vs live quoting; dead HOLDs; never average. |
| 0:14–0:39 | `_asof_stub` dump **left on screen** through `python -m asof demo` (argv visible). C1: stub 0.15/0.16 vs live 0.169/0.17. C2: later book 0.161/0.164 vs catalogue 0.169/0.17 (not the stub); HOLD / `R-BOOK-DEAD`; `accepting_orders` conflict. |
| 0:39–0:57 | argv then `explain TOKEN.best_bid`, `explain TOKEN.closed`, `query`. Latest cycle = HOLD. `ran:` lines at the bottom. |
| 0:57–1:21 | argv `python -m asof demo --dead-cycle1`, then the halt transcript, then `ran: python -m asof demo --dead-cycle1`. Stop. |

Do not explain `.mid`. Do not run `--live`. Do not cat `artifacts/branch-run.txt`.
