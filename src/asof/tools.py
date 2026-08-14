from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

from asof.types import LiveBook, WarehouseRow

CLOB_URL = "https://clob.polymarket.com"
GAMMA_URL = "https://gamma-api.polymarket.com"
USER_AGENT = "asof-recon/0.1 (educational reconciliation demo)"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ms_to_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n > 1e12:
        n /= 1000.0
    return datetime.fromtimestamp(n, tz=timezone.utc)


def parse_dt(value: Any) -> datetime | None:
    """ISO-8601 or unix ms/seconds. Does not invent a time from a date-only string that is not ISO."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        text = value.strip()
        if "T" not in text and len(text) >= 19 and text[4] == "-":
            text = text[:10] + "T" + text[11:]
        if "T" in text or text.endswith("Z") or "+" in text[1:]:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return _ms_to_dt(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    return _ms_to_dt(value)


def _best_bid(bids: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    best_px: float | None = None
    best_sz: float | None = None
    for row in bids:
        px = _f(row.get("price"))
        sz = _f(row.get("size"))
        if px is None:
            continue
        if best_px is None or px > best_px:
            best_px, best_sz = px, sz
    return best_px, best_sz


def _best_ask(asks: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    best_px: float | None = None
    best_sz: float | None = None
    for row in asks:
        px = _f(row.get("price"))
        sz = _f(row.get("size"))
        if px is None:
            continue
        if best_px is None or px < best_px:
            best_px, best_sz = px, sz
    return best_px, best_sz


def parse_book(raw: dict[str, Any], *, as_of: datetime | None = None) -> LiveBook:
    bids = raw.get("bids") or []
    asks = raw.get("asks") or []
    bid_px, bid_sz = _best_bid(bids)
    ask_px, ask_sz = _best_ask(asks)
    top = None
    if bid_sz is not None or ask_sz is not None:
        top = (bid_sz or 0.0) + (ask_sz or 0.0)
    ts = as_of or parse_dt(raw.get("timestamp")) or datetime.now(timezone.utc)
    return LiveBook(
        token_id=str(raw.get("asset_id") or ""),
        condition_id=str(raw.get("market") or ""),
        as_of=ts,
        best_bid=bid_px,
        best_ask=ask_px,
        last_trade_price=_f(raw.get("last_trade_price")),
        last_trade_time=parse_dt(raw.get("last_trade_time")),
        quoting=bool(bids or asks),
        top_liquidity=top,
    )


def parse_gamma(raw: dict[str, Any], token_id: str | None = None) -> WarehouseRow:
    ids = [str(x) for x in _as_list(raw.get("clobTokenIds"))]
    prices = [_f(x) for x in _as_list(raw.get("outcomePrices"))]
    chosen = token_id or (ids[0] if ids else "")
    idx = ids.index(chosen) if chosen in ids else 0
    outcome = prices[idx] if idx < len(prices) else _f(raw.get("lastTradePrice"))
    cond = str(raw.get("conditionId") or raw.get("condition_id") or "")
    vol = _f(raw.get("volumeNum"))
    if vol is None:
        vol = _f(raw.get("volume"))
    liq = _f(raw.get("liquidityNum"))
    if liq is None:
        liq = _f(raw.get("liquidity"))
    return WarehouseRow(
        token_id=chosen if chosen else (ids[0] if ids else ""),
        condition_id=cond,
        clob_token_ids=tuple(ids),
        closed=raw.get("closed"),
        accepting_orders=raw.get("acceptingOrders"),
        volume=vol,
        liquidity=liq,
        best_bid=_f(raw.get("bestBid")),
        best_ask=_f(raw.get("bestAsk")),
        outcome_price=outcome,
        last_trade_price=_f(raw.get("lastTradePrice")),
        last_trade_time=parse_dt(raw.get("lastTradeTime")),
        slug=str(raw.get("slug") or ""),
    )


class MarketSource(Protocol):
    def primary_token(self) -> str: ...
    def fetch_live(self, token_id: str, *, captured_clock: bool = False) -> LiveBook | None: ...
    def fetch_warehouse(self, token_id: str, snapshot: str) -> WarehouseRow | None: ...


class CassetteSource:
    """Replay committed CLOB/Gamma payloads for one token and two warehouse snapshots."""

    def __init__(self, directory: Path, now: datetime) -> None:
        self.now = now
        self.dir = directory
        self._live_raw = json.loads((directory / "live.json").read_text(encoding="utf-8"))
        self._snaps: dict[str, dict[str, Any]] = {
            "open": json.loads((directory / "warehouse_open.json").read_text(encoding="utf-8")),
            "closed": json.loads((directory / "warehouse_closed.json").read_text(encoding="utf-8")),
        }

    def primary_token(self) -> str:
        return str(self._live_raw["asset_id"])

    def fetch_live(self, token_id: str, *, captured_clock: bool = False) -> LiveBook | None:
        if token_id != str(self._live_raw.get("asset_id")):
            return None
        if captured_clock:
            return parse_book(self._live_raw)
        return parse_book(self._live_raw, as_of=self.now - timedelta(seconds=0.4))

    def fetch_warehouse(self, token_id: str, snapshot: str) -> WarehouseRow | None:
        if snapshot not in self._snaps:
            return None
        raw = self._snaps[snapshot]
        ids = [str(x) for x in _as_list(raw.get("clobTokenIds"))]
        cond = str(raw.get("conditionId") or "")
        slug = str(raw.get("slug") or "")
        keys = set(ids) | {cond, slug, self.primary_token()}
        if token_id not in keys:
            return None
        pin = token_id if token_id in ids else self.primary_token()
        return parse_gamma(raw, token_id=pin)


class LiveSource:
    """One honest network cycle. snapshot='closed' returns None; we will not splice a dead book."""

    def __init__(
        self,
        now: datetime,
        token_id: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.now = now
        self._token = token_id
        self.client = client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
        )

    def primary_token(self) -> str:
        return self._token

    def fetch_live(self, token_id: str, *, captured_clock: bool = False) -> LiveBook | None:
        r = self.client.get(f"{CLOB_URL}/book", params={"token_id": token_id})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return parse_book(r.json())

    def fetch_warehouse(self, token_id: str, snapshot: str) -> WarehouseRow | None:
        if snapshot != "open":
            return None
        for params in (
            {"clob_token_ids": token_id},
            {"condition_ids": token_id},
            {"slug": token_id},
        ):
            r = self.client.get(f"{GAMMA_URL}/markets", params=params)
            if r.status_code >= 400:
                continue
            data = r.json()
            rows = data if isinstance(data, list) else [data]
            if not rows:
                continue
            raw = rows[0]
            ids = [str(x) for x in _as_list(raw.get("clobTokenIds"))]
            pin = token_id if token_id in ids else token_id
            return parse_gamma(raw, token_id=pin)
        return None
