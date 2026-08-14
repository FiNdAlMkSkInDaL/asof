from __future__ import annotations

from datetime import datetime, timezone

from asof.plan import Action, next_action
from asof.types import LiveBook, Observation, WarehouseRow

NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)


def _live(**kwargs) -> LiveBook:
    base = dict(
        token_id="t",
        condition_id="c",
        as_of=NOW,
        best_bid=0.4,
        best_ask=0.5,
        last_trade_price=0.45,
        last_trade_time=None,
        quoting=True,
        top_liquidity=1.0,
    )
    base.update(kwargs)
    return LiveBook(**base)


def _wh(**kwargs) -> WarehouseRow:
    base = dict(
        token_id="t",
        condition_id="c",
        clob_token_ids=("t",),
        closed=False,
        accepting_orders=True,
        volume=1.0,
        liquidity=2.0,
        best_bid=0.3,
        best_ask=0.6,
        outcome_price=0.5,
        last_trade_price=0.4,
        last_trade_time=None,
    )
    base.update(kwargs)
    return WarehouseRow(**base)


def test_no_live_yet_fetches_live():
    assert next_action(Observation(token_id="t")) is Action.FETCH_LIVE


def test_live_miss_halts():
    obs = Observation(token_id="t", live_fetched=True, live=None)
    assert next_action(obs) is Action.HALT


def test_live_present_fetches_open_warehouse():
    obs = Observation(token_id="t", live_fetched=True, live=_live())
    assert next_action(obs) is Action.WAREHOUSE_OPEN


def test_warehouse_miss_retries_pinned():
    obs = Observation(
        token_id="t",
        live_fetched=True,
        live=_live(),
        warehouse_miss=True,
        retried_pinned=False,
    )
    assert next_action(obs) is Action.RETRY_WAREHOUSE_PINNED


def test_warehouse_miss_after_retry_halts():
    obs = Observation(
        token_id="t",
        live_fetched=True,
        live=_live(),
        warehouse_miss=True,
        retried_pinned=True,
    )
    assert next_action(obs) is Action.HALT


def test_both_present_applies():
    obs = Observation(
        token_id="t",
        live_fetched=True,
        live=_live(),
        warehouse=_wh(),
    )
    assert next_action(obs) is Action.APPLY


def test_after_microstructure_fetches_closed():
    obs = Observation(
        token_id="t",
        live_fetched=True,
        live=_live(),
        applies=1,
        live_won_book=True,
        market_dead=False,
    )
    assert next_action(obs) is Action.WAREHOUSE_CLOSED


def test_dead_cycle1_halts_not_closed_snapshot():
    obs = Observation(
        token_id="t",
        live_fetched=True,
        live=_live(),
        applies=1,
        live_won_book=False,
        market_dead=True,
    )
    assert next_action(obs) is Action.HALT


def test_two_applies_halt():
    obs = Observation(
        token_id="t",
        live_fetched=True,
        live=_live(),
        applies=2,
        live_won_book=True,
        market_dead=False,
    )
    assert next_action(obs) is Action.HALT
