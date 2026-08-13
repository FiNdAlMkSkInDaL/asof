from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from asof.agent import Agent
from asof.store import Store
from asof.tools import CassetteSource
from asof.types import LiveBook, WarehouseRow, Winner

NOW = datetime(2026, 8, 13, 18, 0, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
CASSETTES = ROOT / "cassettes"


def test_two_cycles_two_winner_classes(tmp_path: Path):
    store = Store(tmp_path / "asof.sqlite")
    src = CassetteSource(CASSETTES, NOW)
    agent = Agent(src, store, NOW)
    steps = agent.run()
    assert len(agent.results) == 2
    c1, c2 = agent.results
    assert any(
        d.field in {"best_bid", "best_ask", "mid"} and d.winner is Winner.LIVE
        for d in c1.decisions
    )
    assert any(d.rule_id == "R-BOOK-DEAD" for d in c2.decisions)
    assert c2.by_field("closed").winner is Winner.WAREHOUSE
    assert c2.by_field("closed").value is True
    live_args = [s.args.get("token_id") for s in steps if s.tool == "fetch_live"]
    assert live_args[0] != live_args[-1]
    kinds = [s.kind for s in steps]
    assert kinds[0] == "PLAN"
    assert "TOOL" in kinds and "OBSERVE" in kinds and "APPLY" in kinds
    store.close()


class _MissThenHit:
    def __init__(self, inner: CassetteSource) -> None:
        self.inner = inner
        self.token_misses = 0

    def cycle1_token(self) -> str:
        return self.inner.cycle1_token()

    def cycle2_token(self) -> str:
        return self.inner.cycle2_token()

    def fetch_live(self, token_id: str) -> LiveBook | None:
        return self.inner.fetch_live(token_id)

    def fetch_warehouse(self, key: str) -> WarehouseRow | None:
        token = self.inner.cycle1_token()
        if key == token and self.token_misses == 0:
            self.token_misses += 1
            return None
        return self.inner.fetch_warehouse(key)


def test_warehouse_miss_retries_condition_id(tmp_path: Path):
    store = Store(tmp_path / "asof.sqlite")
    inner = CassetteSource(CASSETTES, NOW)
    src = _MissThenHit(inner)
    agent = Agent(src, store, NOW)
    agent.run()
    assert src.token_misses == 1
    assert any("Retry by condition_id" in s.message for s in agent.steps)
    assert agent.results[0].identity_ok is True
    store.close()
