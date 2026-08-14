from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from asof.policy import reconcile
from asof.store import Store
from asof.types import LiveBook, WarehouseRow, Winner

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)


def test_put_and_explain(tmp_path: Path):
    live = LiveBook(
        token_id="t1",
        condition_id="c1",
        as_of=NOW,
        best_bid=0.4,
        best_ask=0.5,
        last_trade_price=0.45,
        last_trade_time=NOW,
        quoting=True,
        top_liquidity=10.0,
    )
    wh = WarehouseRow(
        token_id="t1",
        condition_id="c1",
        clob_token_ids=("t1", "t2"),
        closed=False,
        accepting_orders=True,
        volume=100.0,
        liquidity=200.0,
        outcome_price=0.6,
        best_bid=0.3,
        best_ask=0.7,
        last_trade_price=0.55,
        last_trade_time=NOW,
    )
    result = reconcile(live, wh, NOW)
    store = Store(tmp_path / "asof.sqlite")
    store.put(result, cycle=1)
    row = store.explain("t1", "mid")
    assert row is not None
    assert row["winner"] == Winner.LIVE.value
    assert row["rule_id"] == "R-BOOK-LIVE"
    rows = store.query("t1")
    assert {r["field"] for r in rows} >= {"mid", "volume", "closed"}
    prev = store.previous("t1")
    assert prev["mid"] == live.mid
    dead = WarehouseRow(
        token_id="t1",
        condition_id="c1",
        clob_token_ids=("t1", "t2"),
        closed=True,
        accepting_orders=False,
        volume=100.0,
        liquidity=200.0,
        best_bid=0.3,
        best_ask=0.7,
        outcome_price=0.6,
        last_trade_price=0.55,
        last_trade_time=NOW,
    )
    held = reconcile(live, dead, NOW, previous=prev)
    store.put(held, cycle=2)
    row2 = store.explain("t1", "mid")
    assert row2 is not None
    assert row2["winner"] == Winner.HOLD.value
    assert row2["rule_id"] == "R-BOOK-DEAD"
    assert json.loads(row2["value"]) == live.mid
    store.close()
