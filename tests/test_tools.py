from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from asof.tools import CassetteSource, parse_book, parse_gamma

ROOT = Path(__file__).resolve().parents[1]
CASSETTES = ROOT / "cassettes"
NOW = datetime(2026, 8, 13, 18, 0, 0, tzinfo=timezone.utc)


def test_parse_cycle1_book_bests():
    raw = json.loads((CASSETTES / "cycle1_live.json").read_text(encoding="utf-8"))
    book = parse_book(raw, as_of=NOW)
    assert book.token_id == raw["asset_id"]
    assert book.condition_id == raw["market"]
    assert book.best_bid is not None and book.best_ask is not None
    assert book.best_bid < book.best_ask
    assert book.quoting is True
    assert book.mid == (book.best_bid + book.best_ask) / 2


def test_parse_cycle1_gamma_outcome_for_token():
    raw = json.loads((CASSETTES / "cycle1_warehouse.json").read_text(encoding="utf-8"))
    token = json.loads((CASSETTES / "cycle1_live.json").read_text(encoding="utf-8"))["asset_id"]
    row = parse_gamma(raw, token_id=token)
    assert row.token_id == token
    assert row.closed is False
    assert row.accepting_orders is True
    assert row.outcome_price is not None


def test_cycle1_live_and_warehouse_disagree_on_mid():
    src = CassetteSource(CASSETTES, NOW)
    token = src.cycle1_token()
    live = src.fetch_live(token)
    wh = src.fetch_warehouse(token)
    assert live is not None and wh is not None
    assert live.mid is not None and wh.outcome_price is not None
    # Catalogue is one probability; the book is a spread. Bid and ask both differ.
    assert abs(live.best_bid - wh.outcome_price) > 1e-9
    assert abs(live.best_ask - wh.outcome_price) > 1e-9
    assert live.top_liquidity != wh.liquidity


def test_cycle2_warehouse_is_dead():
    src = CassetteSource(CASSETTES, NOW)
    token = src.cycle2_token()
    wh = src.fetch_warehouse(token)
    live = src.fetch_live(token)
    assert wh is not None and live is not None
    assert wh.closed is True
    assert live.quoting is True
    assert live.token_id == wh.token_id or live.token_id in wh.clob_token_ids
    assert live.condition_id == wh.condition_id


def test_warehouse_lookup_by_condition_id():
    src = CassetteSource(CASSETTES, NOW)
    token = src.cycle1_token()
    live = src.fetch_live(token)
    assert live is not None
    wh = src.fetch_warehouse(live.condition_id)
    assert wh is not None
    assert live.condition_id == wh.condition_id


def test_unknown_token_returns_none():
    src = CassetteSource(CASSETTES, NOW)
    assert src.fetch_live("missing") is None
    assert src.fetch_warehouse("missing") is None
