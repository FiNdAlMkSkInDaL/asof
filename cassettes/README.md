# Cassettes

Committed public Polymarket payloads used by `python -m asof demo` (no network). One outcome token. Two live books (cycle 1, then the refetch). Two warehouse snapshots of that token.

| File | What it is |
| --- | --- |
| `live.json` | Unmodified CLOB `GET /book` for the Yes token of “Will Gavin Newsom win the 2028 Democratic presidential nomination?” (capture-time BBO `0.169`/`0.17`). |
| `live_c2.json` | Unmodified later CLOB `GET /book` for the same token (2026-08-16: BBO `0.161`/`0.164`). Cycle 2 refetch. Gamma agreed with this book; not a stub. |
| `warehouse_open.json` | Captured Gamma row. `bestBid` / `bestAsk` lagged (`_asof_stub`). Capture-time `lastTradePrice` `0.17` kept (CLOB last trade was `0.169`). |
| `warehouse_closed.json` | Same identity. `closed` / `acceptingOrders` overlaid (`_asof_stub`). `bestBid`/`bestAsk` are the first capture's real catalogue BBO (`0.169`/`0.17`), not the open lag. |

On replay, `CassetteSource.fetch_live` sets `as_of` to `now - 0.4s` so the 2s SLA still holds. The first fetch is `live.json`; the second is `live_c2.json`. Pass `captured_clock=True` in unit tests to use the JSON timestamp. Raw `timestamp` remains in the JSON.

On 2026-08-14 the live APIs agreed with the first book on bid/ask; recapture last trade matched that book. Lagged open bid/ask and the closed overlay are labelled in `_asof_stub`.
