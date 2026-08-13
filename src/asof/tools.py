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
    ts = as_of or _ms_to_dt(raw.get("timestamp")) or datetime.now(timezone.utc)
    return LiveBook(
        token_id=str(raw.get("asset_id") or ""),
        condition_id=str(raw.get("market") or ""),
        as_of=ts,
        best_bid=bid_px,
        best_ask=ask_px,
        last_trade_price=_f(raw.get("last_trade_price")),
        last_trade_time=None,
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
        outcome_price=outcome,
        last_trade_price=_f(raw.get("lastTradePrice")),
        last_trade_time=_ms_to_dt(raw.get("closedTime")) if raw.get("closed") else None,
        slug=str(raw.get("slug") or ""),
    )


class MarketSource(Protocol):
    def cycle1_token(self) -> str: ...
    def cycle2_token(self) -> str: ...
    def fetch_live(self, token_id: str) -> LiveBook | None: ...
    def fetch_warehouse(self, key: str) -> WarehouseRow | None: ...


class CassetteSource:
    """Replay committed CLOB/Gamma payloads. Live as_of is rebased to `now` so the SLA holds."""

    def __init__(self, directory: Path, now: datetime) -> None:
        self.now = now
        self.dir = directory
        self._live_raw: dict[str, dict[str, Any]] = {}
        self._wh: dict[str, dict[str, Any]] = {}
        for name in ("cycle1_live.json", "cycle2_live.json"):
            raw = json.loads((directory / name).read_text(encoding="utf-8"))
            self._live_raw[str(raw["asset_id"])] = raw
        for name in ("cycle1_warehouse.json", "cycle2_warehouse.json"):
            raw = json.loads((directory / name).read_text(encoding="utf-8"))
            row = parse_gamma(raw)
            self._wh[row.token_id] = raw
            if row.condition_id:
                self._wh[row.condition_id] = raw
            if row.slug:
                self._wh[row.slug] = raw
            for tid in row.clob_token_ids:
                self._wh[tid] = raw

    def cycle1_token(self) -> str:
        raw = json.loads((self.dir / "cycle1_live.json").read_text(encoding="utf-8"))
        return str(raw["asset_id"])

    def cycle2_token(self) -> str:
        raw = json.loads((self.dir / "cycle2_live.json").read_text(encoding="utf-8"))
        return str(raw["asset_id"])

    def fetch_live(self, token_id: str) -> LiveBook | None:
        raw = self._live_raw.get(token_id)
        if raw is None:
            return None
        return parse_book(raw, as_of=self.now - timedelta(seconds=0.4))

    def fetch_warehouse(self, key: str) -> WarehouseRow | None:
        raw = self._wh.get(key)
        if raw is None:
            return None
        token = key if key in {str(x) for x in _as_list(raw.get("clobTokenIds"))} else None
        return parse_gamma(raw, token_id=token)


class LiveSource:
    def __init__(
        self,
        now: datetime,
        cycle1: str,
        cycle2: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.now = now
        self._cycle1 = cycle1
        self._cycle2 = cycle2
        self.client = client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
        )

    def cycle1_token(self) -> str:
        return self._cycle1

    def cycle2_token(self) -> str:
        return self._cycle2

    def fetch_live(self, token_id: str) -> LiveBook | None:
        r = self.client.get(f"{CLOB_URL}/book", params={"token_id": token_id})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return parse_book(r.json())

    def fetch_warehouse(self, key: str) -> WarehouseRow | None:
        for params in (
            {"clob_token_ids": key},
            {"condition_ids": key},
            {"slug": key},
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
            token = key if key in ids else None
            return parse_gamma(raw, token_id=token)
        return None
