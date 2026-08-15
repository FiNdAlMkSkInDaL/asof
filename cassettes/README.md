# Cassettes

Committed public Polymarket payloads used by `python -m asof demo` (no network). One outcome token. Two warehouse snapshots of that token.

| File | What it is |
| --- | --- |
| `live.json` | Unmodified CLOB `GET /book` for the Yes token of “Will Gavin Newsom win the 2028 Democratic presidential nomination?” |
| `warehouse_open.json` | Captured Gamma row. `bestBid` / `bestAsk` lagged (`_asof_stub`). Capture-time `lastTradePrice` `0.17` kept (CLOB last trade was `0.169`). |
| `warehouse_closed.json` | Same identity. `closed` / `acceptingOrders` overlaid (`_asof_stub`) so cycle 2 can HOLD cycle-1 live prices. Not a different market. |

On replay, `CassetteSource.fetch_live` sets `as_of` to `now - 0.4s` so the 2s SLA still holds. Pass `captured_clock=True` in unit tests to use the JSON timestamp. Raw `timestamp` remains in the JSON.

On 2026-08-14 the live APIs agreed with the book on bid/ask; recapture last trade matched the book. Lagged bid/ask and the closed overlay are labelled in `_asof_stub` (`captured` vs `recapture` vs `stubbed`).
