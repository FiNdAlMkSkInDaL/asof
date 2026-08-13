from __future__ import annotations

from datetime import datetime, timedelta, timezone

from asof.policy import reconcile
from asof.types import FRESH_SLA_SECONDS, LiveBook, WarehouseRow, Winner

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
TOKEN = "tok-yes"
OTHER = "tok-no"
COND = "0xcond"


def book(
    *,
    token_id: str = TOKEN,
    condition_id: str = COND,
    as_of: datetime | None = None,
    best_bid: float | None = 0.44,
    best_ask: float | None = 0.46,
    last_trade_price: float | None = 0.45,
    last_trade_time: datetime | None = None,
    quoting: bool = True,
    top_liquidity: float | None = 200.0,
) -> LiveBook:
    return LiveBook(
        token_id=token_id,
        condition_id=condition_id,
        as_of=as_of if as_of is not None else NOW - timedelta(seconds=0.4),
        best_bid=best_bid,
        best_ask=best_ask,
        last_trade_price=last_trade_price,
        last_trade_time=last_trade_time if last_trade_time is not None else NOW - timedelta(seconds=1),
        quoting=quoting,
        top_liquidity=top_liquidity,
    )


def warehouse(
    *,
    token_id: str = TOKEN,
    condition_id: str = COND,
    clob_token_ids: tuple[str, ...] | None = None,
    closed: bool | None = False,
    accepting_orders: bool | None = True,
    volume: float | None = 1_000.0,
    liquidity: float | None = 5_000.0,
    outcome_price: float | None = 0.50,
    last_trade_price: float | None = 0.49,
    last_trade_time: datetime | None = None,
) -> WarehouseRow:
    return WarehouseRow(
        token_id=token_id,
        condition_id=condition_id,
        clob_token_ids=clob_token_ids if clob_token_ids is not None else (TOKEN, OTHER),
        closed=closed,
        accepting_orders=accepting_orders,
        volume=volume,
        liquidity=liquidity,
        outcome_price=outcome_price,
        last_trade_price=last_trade_price,
        last_trade_time=last_trade_time if last_trade_time is not None else NOW - timedelta(seconds=30),
    )


def test_import_reconcile():
    from asof.policy import reconcile as fn

    assert fn is reconcile


def test_r_book_live_fresh_two_sided():
    r = reconcile(book(), warehouse(), NOW)
    for name in ("best_bid", "best_ask", "mid", "spread"):
        d = r.by_field(name)
        assert d.winner is Winner.LIVE
        assert d.rule_id == "R-BOOK-LIVE"
    for name in ("best_bid", "best_ask", "mid"):
        assert r.by_field(name).conflict
    assert r.by_field("mid").value == 0.45
    assert abs(r.by_field("spread").value - 0.02) < 1e-12


def test_r_book_stale_exceeds_sla():
    live = book(as_of=NOW - timedelta(seconds=FRESH_SLA_SECONDS + 0.5))
    r = reconcile(live, warehouse(), NOW)
    for name in ("best_bid", "best_ask", "mid", "spread"):
        d = r.by_field(name)
        assert d.winner is Winner.HOLD
        assert d.rule_id == "R-BOOK-STALE"


def test_r_book_crossed():
    r = reconcile(book(best_bid=0.51, best_ask=0.49), warehouse(), NOW)
    for name in ("best_bid", "best_ask", "mid", "spread"):
        d = r.by_field(name)
        assert d.winner is Winner.HOLD
        assert d.rule_id == "R-BOOK-CROSSED"


def test_r_book_one_sided_missing_ask():
    r = reconcile(book(best_ask=None), warehouse(), NOW)
    assert r.by_field("best_bid").winner is Winner.LIVE
    assert r.by_field("best_bid").rule_id == "R-BOOK-LIVE"
    assert r.by_field("best_ask").winner is Winner.HOLD
    assert r.by_field("best_ask").rule_id == "R-BOOK-ONE-SIDED"
    assert r.by_field("mid").winner is Winner.HOLD
    assert r.by_field("mid").rule_id == "R-BOOK-ONE-SIDED"
    assert r.by_field("spread").winner is Winner.HOLD


def test_r_book_dead_closed_warehouse():
    r = reconcile(book(), warehouse(closed=True), NOW)
    for name in ("best_bid", "best_ask", "mid", "spread", "last_trade_price"):
        d = r.by_field(name)
        assert d.winner is Winner.HOLD
        assert d.rule_id == "R-BOOK-DEAD"
    assert r.by_field("closed").winner is Winner.WAREHOUSE
    assert r.by_field("closed").value is True
    assert r.by_field("closed").rule_id == "R-LIFE-WAREHOUSE"


def test_r_book_dead_not_accepting():
    r = reconcile(book(), warehouse(accepting_orders=False), NOW)
    assert r.by_field("mid").rule_id == "R-BOOK-DEAD"
    assert r.by_field("accepting_orders").value is False
    assert r.by_field("accepting_orders").winner is Winner.WAREHOUSE


def test_r_trade_newer_live_timestamp():
    live = book(last_trade_price=0.41, last_trade_time=NOW - timedelta(seconds=1))
    wh = warehouse(last_trade_price=0.49, last_trade_time=NOW - timedelta(seconds=40))
    d = reconcile(live, wh, NOW).by_field("last_trade_price")
    assert d.winner is Winner.LIVE
    assert d.value == 0.41
    assert d.rule_id == "R-TRADE-NEWER"


def test_r_trade_newer_warehouse_timestamp():
    live = book(last_trade_price=0.41, last_trade_time=NOW - timedelta(seconds=40))
    wh = warehouse(last_trade_price=0.49, last_trade_time=NOW - timedelta(seconds=1))
    d = reconcile(live, wh, NOW).by_field("last_trade_price")
    assert d.winner is Winner.WAREHOUSE
    assert d.value == 0.49
    assert d.rule_id == "R-TRADE-NEWER"


def test_r_agg_warehouse():
    r = reconcile(book(top_liquidity=200.0), warehouse(volume=9_001.0, liquidity=8_002.0), NOW)
    vol = r.by_field("volume")
    liq = r.by_field("liquidity")
    assert vol.winner is Winner.WAREHOUSE and vol.value == 9_001.0
    assert vol.rule_id == "R-AGG-WAREHOUSE"
    assert liq.winner is Winner.WAREHOUSE and liq.value == 8_002.0
    assert liq.live == 200.0
    assert liq.warehouse == 8_002.0


def test_r_life_warehouse_keys():
    r = reconcile(book(), warehouse(), NOW)
    assert r.identity_ok is True
    assert r.by_field("token_id").winner is Winner.WAREHOUSE
    assert r.by_field("condition_id").winner is Winner.WAREHOUSE
    assert r.by_field("token_id").rule_id == "R-LIFE-WAREHOUSE"
    assert r.by_field("closed").value is False
    assert r.by_field("accepting_orders").value is True


def test_r_id_hold_token_mismatch():
    live = book(token_id="alien", condition_id=COND)
    wh = warehouse(token_id=TOKEN, clob_token_ids=(TOKEN, OTHER))
    r = reconcile(live, wh, NOW)
    assert r.identity_ok is False
    for d in r.decisions:
        assert d.winner is Winner.HOLD
        assert d.rule_id == "R-ID-HOLD"


def test_r_id_hold_condition_mismatch():
    r = reconcile(book(condition_id="0xother"), warehouse(), NOW)
    assert r.identity_ok is False
    assert all(d.rule_id == "R-ID-HOLD" for d in r.decisions)


def test_identity_ok_when_token_in_clob_ids():
    live = book(token_id=OTHER)
    wh = warehouse(token_id=TOKEN, clob_token_ids=(TOKEN, OTHER))
    r = reconcile(live, wh, NOW)
    assert r.identity_ok is True
    assert r.by_field("token_id").value == TOKEN


def test_no_averaging_mid():
    r = reconcile(book(best_bid=0.40, best_ask=0.50), warehouse(outcome_price=0.10), NOW)
    mid = r.by_field("mid")
    assert mid.winner is Winner.LIVE
    assert mid.value == 0.45
    assert mid.value != (0.45 + 0.10) / 2


def test_hold_uses_previous_value():
    live = book(as_of=NOW - timedelta(seconds=10))
    r = reconcile(live, warehouse(), NOW, previous={"mid": 0.33})
    assert r.by_field("mid").winner is Winner.HOLD
    assert r.by_field("mid").value == 0.33
