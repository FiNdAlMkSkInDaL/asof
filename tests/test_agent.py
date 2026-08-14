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


def test_two_applies_one_token_hold(tmp_path: Path):
    store = Store(tmp_path / "asof.sqlite")
    src = CassetteSource(CASSETTES, NOW)
    agent = Agent(src, store, NOW)
    steps = agent.run()
    assert len(agent.results) == 2
    c1, c2 = agent.results
    assert c1.token_id == c2.token_id == src.primary_token()
    bid = c1.by_field("best_bid")
    assert bid.winner is Winner.LIVE
    assert bid.conflict is True
    assert any(d.rule_id == "R-BOOK-DEAD" for d in c2.decisions)
    assert c2.by_field("closed").winner is Winner.WAREHOUSE
    assert c2.by_field("closed").value is True
    assert c2.by_field("best_bid").winner is Winner.HOLD
    assert c2.by_field("best_bid").value == bid.value
    live_args = [s.args.get("token_id") for s in steps if s.tool == "fetch_live"]
    assert live_args
    assert all(t == src.primary_token() for t in live_args)
    kinds = [s.kind for s in steps]
    assert kinds[0] == "PLAN"
    assert "TOOL" in kinds and "OBSERVE" in kinds and "APPLY" in kinds
    store.close()


class _MissThenHit:
    def __init__(self, inner: CassetteSource) -> None:
        self.inner = inner
        self.token_misses = 0

    def primary_token(self) -> str:
        return self.inner.primary_token()

    def fetch_live(self, token_id: str, *, captured_clock: bool = False) -> LiveBook | None:
        return self.inner.fetch_live(token_id, captured_clock=captured_clock)

    def fetch_warehouse(self, token_id: str, snapshot: str) -> WarehouseRow | None:
        if snapshot == "open" and self.token_misses == 0:
            self.token_misses += 1
            return None
        return self.inner.fetch_warehouse(token_id, snapshot)


def test_warehouse_miss_retries_pinned(tmp_path: Path):
    store = Store(tmp_path / "asof.sqlite")
    inner = CassetteSource(CASSETTES, NOW)
    src = _MissThenHit(inner)
    agent = Agent(src, store, NOW)
    agent.run()
    assert src.token_misses == 1
    assert any("pinned to live token" in s.message for s in agent.steps)
    assert agent.results[0].identity_ok is True
    store.close()


class _AlwaysClosed:
    def __init__(self, inner: CassetteSource) -> None:
        self.inner = inner

    def primary_token(self) -> str:
        return self.inner.primary_token()

    def fetch_live(self, token_id: str, *, captured_clock: bool = False) -> LiveBook | None:
        return self.inner.fetch_live(token_id, captured_clock=captured_clock)

    def fetch_warehouse(self, token_id: str, snapshot: str) -> WarehouseRow | None:
        return self.inner.fetch_warehouse(token_id, "closed")


def test_dead_cycle1_does_not_run_second_snapshot(tmp_path: Path):
    store = Store(tmp_path / "asof.sqlite")
    src = _AlwaysClosed(CassetteSource(CASSETTES, NOW))
    agent = Agent(src, store, NOW)
    agent.run()
    assert len(agent.results) == 1
    assert any(d.rule_id == "R-BOOK-DEAD" for d in agent.results[0].decisions)
    snaps = [s.args.get("snapshot") for s in agent.steps if s.tool == "fetch_warehouse"]
    assert snaps == ["open"]
    assert any("already dead" in s.message for s in agent.steps)
    store.close()
