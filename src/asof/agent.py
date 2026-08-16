from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from asof.plan import Action, book_won_live, market_was_dead, next_action
from asof.policy import reconcile
from asof.store import Store
from asof.tools import MarketSource
from asof.types import FieldDecision, LiveBook, Observation, ReconcileResult, WarehouseRow


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
        self.obs = Observation(
            token_id=source.primary_token(),
            available_snapshots=source.available_snapshots(),
        )

    def run(self) -> list[Step]:
        while True:
            action = next_action(self.obs)
            if action is Action.HALT:
                self._emit("PLAN", self._halt_reason())
                break
            if action is Action.FETCH_LIVE:
                self._do_fetch_live()
            elif action is Action.WAREHOUSE_OPEN:
                self._do_fetch_warehouse("open")
            elif action is Action.WAREHOUSE_CLOSED:
                self._do_fetch_warehouse("closed")
            elif action is Action.RETRY_WAREHOUSE_PINNED:
                self._do_retry_pinned()
            elif action is Action.APPLY:
                self._do_apply()
        return self.steps

    def _halt_reason(self) -> str:
        if self.obs.applies >= 2:
            return "Two applies done. Halt."
        if self.obs.live_fetched and self.obs.live is None:
            return "Live book missing. Halt."
        if self.obs.warehouse_miss and self.obs.retried_pinned:
            return "Warehouse still missing after pinned retry. Halt."
        if self.obs.applies == 1 and "closed" not in self.obs.available_snapshots:
            return "Closed overlay is cassette-only. Halt."
        if self.obs.applies == 1 and self.obs.market_dead:
            return "Cycle 1 was already dead. Do not fetch a closed overlay. Halt."
        if self.obs.applies == 1 and not self.obs.live_won_book:
            return "Cycle 1 was not a live book win. Halt."
        return "Halt."

    def _do_fetch_live(self) -> None:
        token = self.obs.token_id
        self._emit("PLAN", f"Fetch the live book for token {_clip_id(token)}.")
        self._emit("TOOL", f"fetch_live({_clip_id(token)})", tool="fetch_live", args={"token_id": token})
        live = self.source.fetch_live(token)
        if self.obs.applies >= 1:
            self.obs.live_refresh_done = True
        self.obs.live_fetched = True
        self.obs.live = live
        if live is None:
            self._emit("OBSERVE", "fetch_live returned none")
            return
        self.obs.token_id = live.token_id
        self._emit(
            "OBSERVE",
            f"book bid={_n(live.best_bid)} ask={_n(live.best_ask)} mid={_n(live.mid)} "
            f"quoting={live.quoting} top={_n(live.top_liquidity)}",
        )

    def _do_fetch_warehouse(self, snapshot: str) -> None:
        token = self.obs.token_id
        self._emit("PLAN", f"Fetch warehouse snapshot {snapshot!r} for token {_clip_id(token)}.")
        self._emit(
            "TOOL",
            f"fetch_warehouse({_clip_id(token)}, {snapshot})",
            tool="fetch_warehouse",
            args={"token_id": token, "snapshot": snapshot},
        )
        row = self.source.fetch_warehouse(token, snapshot)
        self.obs.warehouse_snapshot = snapshot
        if row is None:
            self.obs.warehouse = None
            self.obs.warehouse_miss = True
            self._emit("OBSERVE", "fetch_warehouse returned none")
            return
        self.obs.warehouse = row
        self.obs.warehouse_miss = False
        self.obs.retried_pinned = False
        self._emit(
            "OBSERVE",
            f"catalogue closed={row.closed} accepting={row.accepting_orders} "
            f"bid={_n(row.best_bid)} ask={_n(row.best_ask)} last={_n(row.last_trade_price)}",
        )

    def _do_retry_pinned(self) -> None:
        live = self.obs.live
        assert live is not None
        snap = self.obs.warehouse_snapshot or "open"
        self._emit(
            "PLAN",
            f"Warehouse miss. Retry snapshot {snap!r} pinned to live token {_clip_id(live.token_id)}.",
        )
        self.obs.retried_pinned = True
        self._emit(
            "TOOL",
            f"fetch_warehouse({_clip_id(live.token_id)}, {snap})",
            tool="fetch_warehouse",
            args={"token_id": live.token_id, "snapshot": snap},
        )
        row = self.source.fetch_warehouse(live.token_id, snap)
        if row is None:
            self.obs.warehouse = None
            self.obs.warehouse_miss = True
            self._emit("OBSERVE", "fetch_warehouse returned none")
            return
        self.obs.warehouse = row
        self.obs.warehouse_miss = False
        self._emit(
            "OBSERVE",
            f"catalogue closed={row.closed} accepting={row.accepting_orders} "
            f"bid={_n(row.best_bid)} ask={_n(row.best_ask)}",
        )

    def _do_apply(self) -> None:
        live = self.obs.live
        warehouse = self.obs.warehouse
        assert live is not None and warehouse is not None
        self._emit("OBSERVE", _observe(live, warehouse))
        prev = self.store.previous(live.token_id)
        result = reconcile(live, warehouse, self.now, previous=prev)
        cycle = self.obs.applies + 1
        self.store.put(result, cycle)
        self.results.append(result)
        self._emit("APPLY", _apply_summary(result), decisions=result.decisions)
        self.obs.applies += 1
        self.obs.identity_ok = result.identity_ok
        self.obs.live_won_book = book_won_live(result)
        self.obs.market_dead = market_was_dead(result)
        self.obs.last_rule_ids = frozenset(d.rule_id for d in result.decisions)
        self.obs.warehouse = None
        self.obs.warehouse_miss = False
        self.obs.retried_pinned = False

    def _emit(
        self,
        kind: str,
        message: str,
        *,
        tool: str | None = None,
        args: dict[str, Any] | None = None,
        decisions: list[FieldDecision] | None = None,
    ) -> None:
        cycle = min(max(self.obs.applies, 0) + (0 if kind == "APPLY" else 1), 2)
        if kind == "APPLY":
            cycle = self.obs.applies + 1
        self.steps.append(
            Step(
                kind=kind,
                cycle=cycle,
                message=message,
                tool=tool,
                args=args or {},
                decisions=decisions or [],
            )
        )


TRANSCRIPT_WIDTH = 92


def _n(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _clip_id(value: Any) -> str:
    text = _n(value)
    if len(text) <= 14:
        return text
    return f"{text[:6]}..{text[-4:]}"


def _observe(live: LiveBook, warehouse: WarehouseRow) -> str:
    return (
        f"same-entity={live.token_id == warehouse.token_id}; "
        f"live bid={_n(live.best_bid)} ask={_n(live.best_ask)} vs "
        f"wh bid={_n(warehouse.best_bid)} ask={_n(warehouse.best_ask)}; "
        f"warehouse closed={warehouse.closed} accepting={warehouse.accepting_orders}"
    )


def _apply_summary(result: ReconcileResult) -> str:
    parts = []
    for d in result.decisions:
        if d.field in {"best_bid", "best_ask", "last_trade_price", "closed", "accepting_orders"}:
            flag = " conflict" if d.conflict else ""
            parts.append(f"{d.field}={d.winner.value}/{d.rule_id}{flag}")
    ident = "identity_ok" if result.identity_ok else "identity_refused"
    return ident + " | " + "; ".join(parts)


def render_transcript(steps: list[Step]) -> str:
    lines = ["asof -- planner fetches; policy writes", ""]
    for step in steps:
        prefix = f"C{step.cycle} {step.kind:<7}"
        body = f"{prefix} {step.message}"
        if len(body) <= TRANSCRIPT_WIDTH:
            lines.append(body)
        else:
            wrapped = textwrap.wrap(
                body,
                width=TRANSCRIPT_WIDTH,
                subsequent_indent="         ",
            )
            lines.extend(wrapped or [body])
        for d in step.decisions:
            if d.field in {"token_id", "condition_id", "mid", "spread", "volume", "liquidity"}:
                continue
            line = _decision_line(d)
            if len(line) <= TRANSCRIPT_WIDTH:
                lines.append(line)
            else:
                lines.extend(
                    textwrap.wrap(line, width=TRANSCRIPT_WIDTH, subsequent_indent="         ")
                    or [line]
                )
    return "\n".join(lines) + "\n"


def _decision_line(d: FieldDecision) -> str:
    flag = " conflict" if d.conflict else ""
    if d.field in {"token_id", "condition_id"}:
        detail = "match" if _n(d.live) == _n(d.warehouse) else (
            f"live={_clip_id(d.live)} wh={_clip_id(d.warehouse)}"
        )
        return f"         {d.field:<18} {d.winner.value:<10} {d.rule_id:<22} {detail}"
    return (
        f"         {d.field:<18} {d.winner.value:<10} {d.rule_id:<22} "
        f"{_n(d.live)}/{_n(d.warehouse)}->{_n(d.value)}{flag}"
    )


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


def write_artifacts(
    steps: list[Step],
    results: list[ReconcileResult],
    directory: Path,
    *,
    transcript_name: str = "demo-run.txt",
    write_cycles: bool = True,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / transcript_name).write_text(render_transcript(steps), encoding="utf-8")
    if not write_cycles:
        return
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
