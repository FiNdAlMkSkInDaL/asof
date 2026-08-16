from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from asof.tools import CassetteSource, parse_book, parse_dt, parse_gamma

ROOT = Path(__file__).resolve().parents[1]
CASSETTES = ROOT / "cassettes"
NOW = datetime(2026, 8, 13, 18, 0, 0, tzinfo=timezone.utc)


def test_parse_live_book_bests():
    raw = json.loads((CASSETTES / "live.json").read_text(encoding="utf-8"))
    book = parse_book(raw, as_of=NOW)
    assert book.token_id == raw["asset_id"]
    assert book.condition_id == raw["market"]
    assert book.best_bid is not None and book.best_ask is not None
    assert book.best_bid < book.best_ask
    assert book.quoting is True
    assert book.mid == (book.best_bid + book.best_ask) / 2
    assert book.last_trade_time is None


def test_parse_open_gamma_like_for_like():
    raw = json.loads((CASSETTES / "warehouse_open.json").read_text(encoding="utf-8"))
    token = json.loads((CASSETTES / "live.json").read_text(encoding="utf-8"))["asset_id"]
    row = parse_gamma(raw, token_id=token)
    assert row.token_id == token
    assert row.closed is False
    assert row.accepting_orders is True
    assert row.best_bid == 0.15
    assert row.best_ask == 0.16
    assert row.last_trade_price == 0.17
    stub = raw["_asof_stub"]
    assert stub["keys"] == ["bestBid", "bestAsk"]
    assert "lastTradePrice" not in stub["stubbed"]
    assert stub["captured"]["lastTradePrice"] == 0.17


def test_open_disagrees_on_three_like_for_like_fields():
    src = CassetteSource(CASSETTES, NOW)
    token = src.primary_token()
    live = src.fetch_live(token)
    wh = src.fetch_warehouse(token, "open")
    assert live is not None and wh is not None
    assert abs(live.best_bid - wh.best_bid) > 1e-9
    assert abs(live.best_ask - wh.best_ask) > 1e-9
    assert abs(live.last_trade_price - wh.last_trade_price) > 1e-9


def test_closed_snapshot_same_token():
    src = CassetteSource(CASSETTES, NOW)
    token = src.primary_token()
    live = src.fetch_live(token)
    open_row = src.fetch_warehouse(token, "open")
    closed = src.fetch_warehouse(token, "closed")
    assert live is not None and open_row is not None and closed is not None
    assert closed.token_id == live.token_id == open_row.token_id
    assert closed.condition_id == live.condition_id
    assert closed.closed is True
    assert closed.accepting_orders is False
    stub = json.loads((CASSETTES / "warehouse_closed.json").read_text(encoding="utf-8"))["_asof_stub"]
    assert stub["keys"] == ["closed", "acceptingOrders"]
    assert "lastTradePrice" not in stub.get("stubbed", {})
    assert "bestBid" not in stub.get("stubbed", {})
    assert closed.best_bid == 0.169
    assert closed.best_ask == 0.17
    assert closed.last_trade_price == 0.17


def test_condition_lookup_keeps_live_token():
    src = CassetteSource(CASSETTES, NOW)
    token = src.primary_token()
    live = src.fetch_live(token)
    assert live is not None
    wh = src.fetch_warehouse(live.condition_id, "open")
    assert wh is not None
    assert wh.token_id == token
    assert live.condition_id == wh.condition_id


def test_unknown_token_returns_none():
    src = CassetteSource(CASSETTES, NOW)
    assert src.fetch_live("missing") is None
    assert src.fetch_warehouse("missing", "open") is None


def test_second_live_fetch_uses_live_c2():
    src = CassetteSource(CASSETTES, NOW)
    token = src.primary_token()
    first = src.fetch_live(token)
    second = src.fetch_live(token)
    assert first is not None and second is not None
    assert first.best_bid == 0.169
    assert second.best_bid == 0.161
    assert first.last_trade_price == 0.169
    assert second.last_trade_price == 0.164


def test_captured_clock_uses_json_timestamp():
    src = CassetteSource(CASSETTES, NOW)
    token = src.primary_token()
    fresh = src.fetch_live(token)
    captured = src.fetch_live(token, captured_clock=True)
    assert fresh is not None and captured is not None
    assert abs((NOW - fresh.as_of).total_seconds() - 0.4) < 1e-6
    assert captured.as_of != fresh.as_of


def test_parse_dt_iso_not_float():
    dt = parse_dt("2020-11-02T16:31:01+00:00")
    assert dt is not None and dt.year == 2020
    spaced = parse_dt("2020-11-02 16:31:01+00")
    assert spaced is not None and spaced.year == 2020
