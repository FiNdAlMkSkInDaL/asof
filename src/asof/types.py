from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

FRESH_SLA_SECONDS = 2.0


class Winner(str, Enum):
    LIVE = "LIVE"
    WAREHOUSE = "WAREHOUSE"
    HOLD = "HOLD"


@dataclass(frozen=True)
class LiveBook:
    token_id: str
    condition_id: str
    as_of: datetime
    best_bid: float | None
    best_ask: float | None
    last_trade_price: float | None
    last_trade_time: datetime | None
    quoting: bool
    top_liquidity: float | None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid


@dataclass(frozen=True)
class WarehouseRow:
    token_id: str
    condition_id: str
    clob_token_ids: tuple[str, ...]
    closed: bool | None
    accepting_orders: bool | None
    volume: float | None
    liquidity: float | None
    outcome_price: float | None
    last_trade_price: float | None
    last_trade_time: datetime | None
    slug: str = ""


@dataclass(frozen=True)
class FieldDecision:
    field: str
    live: Any
    warehouse: Any
    winner: Winner
    value: Any
    rule_id: str
    reason: str
    as_of: datetime
    conflict: bool


@dataclass
class ReconcileResult:
    token_id: str
    condition_id: str
    identity_ok: bool = True
    decisions: list[FieldDecision] = field(default_factory=list)

    def values(self) -> dict[str, Any]:
        return {d.field: d.value for d in self.decisions}

    def by_field(self, name: str) -> FieldDecision:
        for d in self.decisions:
            if d.field == name:
                return d
        raise KeyError(name)
