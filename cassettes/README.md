# Cassettes

Committed public Polymarket payloads used by `asof demo` (no network).

| File | What it is |
| --- | --- |
| `cycle1_live.json` | Unmodified CLOB `GET /book` for the Yes token of “Will Gavin Newsom win the 2028 Democratic presidential nomination?” |
| `cycle1_warehouse.json` | Unmodified Gamma market row for that event |
| `cycle2_warehouse.json` | Unmodified Gamma row for a **closed** market (“Will Joe Biden get Coronavirus before the election?”) |
| `cycle2_live.json` | CLOB book **levels** copied from cycle 1; `asset_id` and `market` rewritten to the closed market’s token and condition id |

Cycle 2 is the documented splice in POLICY.md: closed books are often unrestorable, and the demo must show `R-BOOK-DEAD` against a quoting book.

On replay, `CassetteSource` sets live `as_of` to `now - 0.4s` so the 2s freshness SLA still holds years after capture. Raw `timestamp` remains in the JSON.
