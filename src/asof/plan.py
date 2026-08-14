from __future__ import annotations

from enum import Enum

from asof.types import Observation, Winner


class Action(str, Enum):
    FETCH_LIVE = "fetch_live"
    WAREHOUSE_OPEN = "warehouse_open"
    WAREHOUSE_CLOSED = "warehouse_closed"
    RETRY_WAREHOUSE_PINNED = "retry_warehouse_pinned"
    APPLY = "apply"
    HALT = "halt"


def next_action(obs: Observation) -> Action:
    """Pure observation → next tool. No I/O."""
    if obs.applies >= 2:
        return Action.HALT
    if not obs.live_fetched:
        return Action.FETCH_LIVE
    if obs.live is None:
        return Action.HALT
    if obs.warehouse is None:
        if obs.warehouse_miss and not obs.retried_pinned:
            return Action.RETRY_WAREHOUSE_PINNED
        if obs.warehouse_miss and obs.retried_pinned:
            return Action.HALT
        if obs.applies == 0:
            return Action.WAREHOUSE_OPEN
        if obs.applies == 1 and obs.live_won_book and not obs.market_dead:
            return Action.WAREHOUSE_CLOSED
        return Action.HALT
    return Action.APPLY


def book_won_live(result) -> bool:
    return any(
        d.field in {"best_bid", "best_ask"} and d.winner is Winner.LIVE
        for d in result.decisions
    )


def market_was_dead(result) -> bool:
    return any(d.rule_id == "R-BOOK-DEAD" for d in result.decisions)
