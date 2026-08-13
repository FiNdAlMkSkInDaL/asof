from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from asof.policy import reconcile
from asof.store import Store
from asof.tools import MarketSource
from asof.types import FieldDecision, LiveBook, ReconcileResult, WarehouseRow, Winner


@dataclass
class Step:
    kind: str
    cycle: int
    message: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    decisions: list[FieldDecision] = field(default_factory=list)


class Agent:
    def __init__(self, source: MarketSource, store: Store, now: datetime) -> None:
        self.source = source
        self.store = store
        self.now = now
        self.steps: list[Step] = []
        self.results: list[ReconcileResult] = []
        self.world = type("World", (), {"token_id": "", "cycle": 0})()

    def run(self) -> list[Step]:
        self.world.token_id = self.source.cycle1_token()
        self._cycle(1)
        if self._cycle1_was_microstructure():
            self._emit(
                "PLAN",
                "Cycle 1 conflicts were book vs catalogue. "
                "Next market should disagree on lifecycle, not the same price lag.",
            )
        else:
            self._emit(
                "PLAN",
                "Cycle 1 was not a clean microstructure fight. "
                "Still moving to the lifecycle market to show a second winner class.",
            )
        self.world.token_id = self.source.cycle2_token()
        self._cycle(2)
        return self.steps

    def _cycle1_was_microstructure(self) -> bool:
        if not self.results:
            return False
        r = self.results[0]
        live_book = any(
            d.field in {"best_bid", "best_ask", "mid"} and d.winner is Winner.LIVE
            for d in r.decisions
        )
        dead = any(d.rule_id == "R-BOOK-DEAD" for d in r.decisions)
        return live_book and not dead

    def _cycle(self, cycle: int) -> None:
        self.world.cycle = cycle
        token = self.world.token_id
        self._emit("PLAN", f"Reconcile token {token} from the live book and the warehouse.")

        live = self._fetch_live(token)
        if live is None:
            self._emit("OBSERVE", "Live book missing. Cannot apply policy.")
            return

        warehouse = self._fetch_warehouse(token)
        if warehouse is None:
            self._emit(
                "PLAN",
                f"Warehouse miss on token id. Retry by condition_id {live.condition_id}.",
            )
            warehouse = self._fetch_warehouse(live.condition_id)
        if warehouse is None:
            self._emit("OBSERVE", "Warehouse still missing after condition_id retry. Skip apply.")
            return

        self._emit("OBSERVE", _observe(live, warehouse))
        prev = self.store.previous(live.token_id) or self.store.previous(warehouse.token_id)
        result = reconcile(live, warehouse, self.now, previous=prev)
        self.store.put(result, cycle)
        self.results.append(result)
        self._emit("APPLY", _apply_summary(result), decisions=result.decisions)

    def _fetch_live(self, token_id: str) -> LiveBook | None:
        self._emit("TOOL", f"fetch_live({token_id})", tool="fetch_live", args={"token_id": token_id})
        live = self.source.fetch_live(token_id)
        if live is None:
            self._emit("OBSERVE", "fetch_live returned none")
        else:
            self._emit(
                "OBSERVE",
                f"book bid={_n(live.best_bid)} ask={_n(live.best_ask)} mid={_n(live.mid)} quoting={live.quoting}",
            )
        return live

    def _fetch_warehouse(self, key: str) -> WarehouseRow | None:
        self._emit("TOOL", f"fetch_warehouse({key})", tool="fetch_warehouse", args={"key": key})
        row = self.source.fetch_warehouse(key)
        if row is None:
            self._emit("OBSERVE", "fetch_warehouse returned none")
        else:
            self._emit(
                "OBSERVE",
                f"catalogue closed={row.closed} accepting={row.accepting_orders} "
                f"outcome={_n(row.outcome_price)} volume={_n(row.volume)}",
            )
        return row

    def _emit(
        self,
        kind: str,
        message: str,
        *,
        tool: str | None = None,
        args: dict[str, Any] | None = None,
        decisions: list[FieldDecision] | None = None,
    ) -> None:
        self.steps.append(
            Step(
                kind=kind,
                cycle=self.world.cycle,
                message=message,
                tool=tool,
                args=args or {},
                decisions=decisions or [],
            )
        )


def _n(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _observe(live: LiveBook, warehouse: WarehouseRow) -> str:
    return (
        f"same-entity={live.token_id == warehouse.token_id or live.token_id in warehouse.clob_token_ids}; "
        f"live mid={_n(live.mid)} vs catalogue {_n(warehouse.outcome_price)}; "
        f"warehouse closed={warehouse.closed} accepting={warehouse.accepting_orders}"
    )


def _apply_summary(result: ReconcileResult) -> str:
    parts = []
    for d in result.decisions:
        if d.field in {"best_bid", "best_ask", "mid", "volume", "closed", "accepting_orders", "last_trade_price"}:
            flag = " conflict" if d.conflict else ""
            parts.append(f"{d.field}={d.winner.value}/{d.rule_id}{flag}")
    ident = "identity_ok" if result.identity_ok else "identity_refused"
    return ident + " | " + "; ".join(parts)


def render_transcript(steps: list[Step]) -> str:
    lines = ["asof -- planner fetches; policy writes", ""]
    for step in steps:
        prefix = f"C{step.cycle} {step.kind:<7}"
        lines.append(f"{prefix} {step.message}")
        for d in step.decisions:
            flag = "  conflict" if d.conflict else ""
            lines.append(
                f"         {d.field:18} {d.winner.value:10} {d.rule_id:16} "
                f"live={_n(d.live):>10}  wh={_n(d.warehouse):>10}  -> {_n(d.value)}{flag}"
            )
    return "\n".join(lines) + "\n"


def _decision_dict(d: FieldDecision) -> dict[str, Any]:
    return {
        "field": d.field,
        "live": d.live if not isinstance(d.live, datetime) else d.live.isoformat(),
        "warehouse": d.warehouse if not isinstance(d.warehouse, datetime) else d.warehouse.isoformat(),
        "winner": d.winner.value,
        "value": d.value if not isinstance(d.value, datetime) else d.value.isoformat(),
        "rule_id": d.rule_id,
        "reason": d.reason,
        "as_of": d.as_of.isoformat(),
        "conflict": d.conflict,
    }


def write_artifacts(steps: list[Step], results: list[ReconcileResult], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "demo-run.txt").write_text(render_transcript(steps), encoding="utf-8")
    payload = []
    for i, result in enumerate(results, start=1):
        entry = {
            "cycle": i,
            "token_id": result.token_id,
            "condition_id": result.condition_id,
            "identity_ok": result.identity_ok,
            "decisions": [_decision_dict(d) for d in result.decisions],
        }
        payload.append(entry)
        (directory / f"cycle{i}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
    (directory / "cycles.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
