from __future__ import annotations

from datetime import datetime
from typing import Any

from asof.types import (
    FRESH_SLA_SECONDS,
    FieldDecision,
    LiveBook,
    ReconcileResult,
    WarehouseRow,
    Winner,
)


def identity_matches(live: LiveBook, warehouse: WarehouseRow) -> bool:
    if live.token_id != warehouse.token_id:
        return False
    if warehouse.condition_id and live.condition_id != warehouse.condition_id:
        return False
    return True


def book_age_seconds(live: LiveBook, now: datetime) -> float:
    return (now - live.as_of).total_seconds()


def is_fresh(live: LiveBook, now: datetime) -> bool:
    return book_age_seconds(live, now) <= FRESH_SLA_SECONDS


def is_two_sided(live: LiveBook) -> bool:
    return live.best_bid is not None and live.best_ask is not None


def is_uncrossed(live: LiveBook) -> bool:
    if not is_two_sided(live):
        return False
    assert live.best_bid is not None and live.best_ask is not None
    return live.best_bid < live.best_ask


def market_dead(warehouse: WarehouseRow) -> bool:
    if warehouse.closed is True:
        return True
    if warehouse.accepting_orders is False:
        return True
    return False


def _conflict(live: Any, warehouse: Any) -> bool:
    if live is None or warehouse is None:
        return False
    if isinstance(live, float) and isinstance(warehouse, float):
        return abs(live - warehouse) > 1e-9
    return live != warehouse


def _decision(
    field: str,
    live: Any,
    warehouse: Any,
    winner: Winner,
    value: Any,
    rule_id: str,
    reason: str,
    as_of: datetime,
    previous: Any = None,
) -> FieldDecision:
    if winner is Winner.HOLD and value is None:
        value = previous
    # Mid/spread are functions of bid/ask; log them, do not count a second fight.
    conflict = False if field in {"mid", "spread"} else _conflict(live, warehouse)
    return FieldDecision(
        field=field,
        live=live,
        warehouse=warehouse,
        winner=winner,
        value=value,
        rule_id=rule_id,
        reason=reason,
        as_of=as_of,
        conflict=conflict,
    )


def reconcile(
    live: LiveBook,
    warehouse: WarehouseRow,
    now: datetime,
    previous: dict[str, Any] | None = None,
) -> ReconcileResult:
    """Apply POLICY.md. `previous` is last reconciled values, used only on HOLD."""
    prev = previous or {}
    as_of = now
    token_id = live.token_id or warehouse.token_id
    condition_id = live.condition_id or warehouse.condition_id
    result = ReconcileResult(token_id=token_id, condition_id=condition_id)

    if not identity_matches(live, warehouse):
        result.identity_ok = False
        reason = (
            "Live token/condition does not match the warehouse row. "
            "Refuse the merge; identity is not votable."
        )
        for name, live_v, wh_v in (
            ("token_id", live.token_id, warehouse.token_id),
            ("condition_id", live.condition_id, warehouse.condition_id),
        ):
            result.decisions.append(
                _decision(
                    name, live_v, wh_v, Winner.HOLD, prev.get(name),
                    "R-ID-HOLD", reason, as_of, prev.get(name),
                )
            )
        # Still record the other fields as HOLD so the log shows the refuse.
        for name, live_v, wh_v in _comparable_fields(live, warehouse):
            if name in {"token_id", "condition_id"}:
                continue
            result.decisions.append(
                _decision(
                    name, live_v, wh_v, Winner.HOLD, prev.get(name),
                    "R-ID-HOLD", reason, as_of, prev.get(name),
                )
            )
        return result

    result.decisions.append(
        _decision(
            "token_id", live.token_id, warehouse.token_id, Winner.WAREHOUSE,
            warehouse.token_id or live.token_id, "R-LIFE-WAREHOUSE",
            "Identity matches. Store the warehouse token id as the canonical key.",
            as_of,
        )
    )
    result.decisions.append(
        _decision(
            "condition_id", live.condition_id, warehouse.condition_id, Winner.WAREHOUSE,
            warehouse.condition_id or live.condition_id, "R-LIFE-WAREHOUSE",
            "Identity matches. Store the warehouse condition id as the canonical key.",
            as_of,
        )
    )

    result.decisions.extend(_book_fields(live, warehouse, now, prev, as_of))
    result.decisions.append(_last_trade(live, warehouse, now, prev, as_of))
    result.decisions.append(
        _decision(
            "volume", None, warehouse.volume, Winner.WAREHOUSE, warehouse.volume,
            "R-AGG-WAREHOUSE",
            "Volume is a catalogue aggregate. The book does not compute it.",
            as_of,
        )
    )
    result.decisions.append(
        _decision(
            "liquidity", None, warehouse.liquidity, Winner.WAREHOUSE,
            warehouse.liquidity, "R-AGG-WAREHOUSE",
            "Catalogue liquidity wins. Top-of-book size is not a like-for-like live value.",
            as_of,
        )
    )
    result.decisions.append(
        _decision(
            "closed", None, warehouse.closed, Winner.WAREHOUSE, warehouse.closed,
            "R-LIFE-WAREHOUSE",
            "Lifecycle is official. Live CLOB /book does not carry closed.",
            as_of,
        )
    )
    result.decisions.append(
        _decision(
            "accepting_orders", live.quoting, warehouse.accepting_orders, Winner.WAREHOUSE,
            warehouse.accepting_orders, "R-LIFE-WAREHOUSE",
            "Warehouse acceptingOrders is official. Live quoting (the book still has a ladder) is the like-for-like side.",
            as_of,
        )
    )
    return result


def _comparable_fields(live: LiveBook, warehouse: WarehouseRow) -> list[tuple[str, Any, Any]]:
    return [
        ("best_bid", live.best_bid, warehouse.best_bid),
        ("best_ask", live.best_ask, warehouse.best_ask),
        ("mid", live.mid, warehouse.mid),
        ("spread", live.spread, None),
        ("last_trade_price", live.last_trade_price, warehouse.last_trade_price),
        ("volume", None, warehouse.volume),
        ("liquidity", None, warehouse.liquidity),
        ("closed", None, warehouse.closed),
        ("accepting_orders", live.quoting, warehouse.accepting_orders),
    ]


def _book_fields(
    live: LiveBook,
    warehouse: WarehouseRow,
    now: datetime,
    prev: dict[str, Any],
    as_of: datetime,
) -> list[FieldDecision]:
    live_mid = live.mid
    live_spread = live.spread
    wh_bid = warehouse.best_bid
    wh_ask = warehouse.best_ask
    wh_mid = warehouse.mid

    if market_dead(warehouse):
        reason = (
            "Warehouse says closed or not accepting orders. "
            "Do not apply live prices to a dead market."
        )
        return [
            _decision(name, live_v, wh_v,
                      Winner.HOLD, prev.get(name), "R-BOOK-DEAD", reason, as_of, prev.get(name))
            for name, live_v, wh_v in (
                ("best_bid", live.best_bid, wh_bid),
                ("best_ask", live.best_ask, wh_ask),
                ("mid", live_mid, wh_mid),
                ("spread", live_spread, None),
            )
        ]

    if not is_fresh(live, now):
        age = book_age_seconds(live, now)
        reason = f"Book age {age:.3f}s exceeds the {FRESH_SLA_SECONDS:.0f}s SLA. Stale live does not get live privileges."
        return [
            _decision(name, live_v, wh_v,
                      Winner.HOLD, prev.get(name), "R-BOOK-STALE", reason, as_of, prev.get(name))
            for name, live_v, wh_v in (
                ("best_bid", live.best_bid, wh_bid),
                ("best_ask", live.best_ask, wh_ask),
                ("mid", live_mid, wh_mid),
                ("spread", live_spread, None),
            )
        ]

    if is_two_sided(live) and not is_uncrossed(live):
        reason = "Crossed book (bid >= ask). Corrupt, not newer."
        return [
            _decision(name, live_v, wh_v,
                      Winner.HOLD, prev.get(name), "R-BOOK-CROSSED", reason, as_of, prev.get(name))
            for name, live_v, wh_v in (
                ("best_bid", live.best_bid, wh_bid),
                ("best_ask", live.best_ask, wh_ask),
                ("mid", live_mid, wh_mid),
                ("spread", live_spread, None),
            )
        ]

    out: list[FieldDecision] = []
    two = is_two_sided(live)
    live_reason = (
        f"Fresh two-sided uncrossed book (age {book_age_seconds(live, now):.3f}s <= {FRESH_SLA_SECONDS:.0f}s). "
        "The book is the market now."
    )

    for name, live_v, wh_v in (("best_bid", live.best_bid, wh_bid), ("best_ask", live.best_ask, wh_ask)):
        if live_v is None:
            out.append(_decision(
                name, live_v, wh_v, Winner.HOLD, prev.get(name),
                "R-BOOK-ONE-SIDED", "That side of the book is empty. Do not invent it.",
                as_of, prev.get(name),
            ))
        else:
            out.append(_decision(
                name, live_v, wh_v, Winner.LIVE, live_v,
                "R-BOOK-LIVE", live_reason, as_of,
            ))

    if not two:
        one_reason = "Book is one-sided. Do not invent a mid or spread."
        out.append(_decision("mid", live_mid, wh_mid, Winner.HOLD, prev.get("mid"),
                             "R-BOOK-ONE-SIDED", one_reason, as_of, prev.get("mid")))
        out.append(_decision("spread", live_spread, None, Winner.HOLD, prev.get("spread"),
                             "R-BOOK-ONE-SIDED", one_reason, as_of, prev.get("spread")))
    else:
        out.append(_decision("mid", live_mid, wh_mid, Winner.LIVE, live_mid,
                             "R-BOOK-LIVE", live_reason, as_of))
        out.append(_decision("spread", live_spread, None, Winner.LIVE, live_spread,
                             "R-BOOK-LIVE", live_reason, as_of))
    return out


def _last_trade(
    live: LiveBook,
    warehouse: WarehouseRow,
    now: datetime,
    prev: dict[str, Any],
    as_of: datetime,
) -> FieldDecision:
    live_px = live.last_trade_price
    wh_px = warehouse.last_trade_price
    if market_dead(warehouse):
        return _decision(
            "last_trade_price", live_px, wh_px, Winner.HOLD, prev.get("last_trade_price"),
            "R-BOOK-DEAD",
            "Market is closed or not accepting. Do not take a live last trade as truth.",
            as_of, prev.get("last_trade_price"),
        )
    live_t = live.last_trade_time
    wh_t = warehouse.last_trade_time
    if live_t is not None and wh_t is not None:
        if live_t >= wh_t:
            return _decision(
                "last_trade_price", live_px, wh_px, Winner.LIVE, live_px,
                "R-TRADE-NEWER", "Live trade timestamp is newer.", as_of,
            )
        return _decision(
            "last_trade_price", live_px, wh_px, Winner.WAREHOUSE, wh_px,
            "R-TRADE-NEWER", "Warehouse trade timestamp is newer.", as_of,
        )
    if is_fresh(live, now) and live_px is not None:
        return _decision(
            "last_trade_price", live_px, wh_px, Winner.LIVE, live_px,
            "R-TRADE-LIVE-NOCLOCK",
            "No trade timestamps on either side. Fresh live last-trade price wins; this is not a recency comparison.",
            as_of,
        )
    return _decision(
        "last_trade_price", live_px, wh_px, Winner.HOLD, prev.get("last_trade_price"),
        "R-BOOK-STALE",
        "No trustworthy trade timestamp pair, and live is not fresh.",
        as_of, prev.get("last_trade_price"),
    )
