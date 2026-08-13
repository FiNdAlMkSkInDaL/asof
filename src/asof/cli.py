from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from asof.agent import Agent, render_transcript, write_artifacts
from asof.store import Store
from asof.tools import CassetteSource, LiveSource

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
CASSETTES = REPO / "cassettes" if (REPO / "cassettes").is_dir() else Path.cwd() / "cassettes"
ARTIFACTS = REPO / "artifacts" if (REPO / "pyproject.toml").exists() else Path.cwd() / "artifacts"
DEFAULT_DB = ARTIFACTS / "asof.sqlite"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="asof",
        description="Reconcile a live order book with a warehouse snapshot. Policy writes; the planner fetches.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="Run two reconciliation cycles")
    demo.add_argument("--live", action="store_true", help="Hit public Polymarket APIs instead of cassettes")
    demo.add_argument("--token", help="Cycle-1 token id (required with --live)")
    demo.add_argument("--token-cycle2", help="Cycle-2 token id (live mode; default: cassette closed-market token)")
    demo.add_argument("--db", type=Path, default=DEFAULT_DB)
    demo.add_argument("--artifacts", type=Path, default=ARTIFACTS)

    query = sub.add_parser("query", help="Print reconciled state for a token")
    query.add_argument("token")
    query.add_argument("--db", type=Path, default=DEFAULT_DB)

    explain = sub.add_parser("explain", help="Explain one field, e.g. TOKEN.mid")
    explain.add_argument("target", help="TOKEN.field")
    explain.add_argument("--db", type=Path, default=DEFAULT_DB)

    args = parser.parse_args(argv)
    if args.cmd == "demo":
        return _demo(args)
    if args.cmd == "query":
        return _query(args)
    if args.cmd == "explain":
        return _explain(args)
    return 2


def _demo(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        args.db.unlink()
    store = Store(args.db)
    if args.live:
        if not args.token:
            print("live mode requires --token", file=sys.stderr)
            return 2
        cycle2 = args.token_cycle2 or CassetteSource(CASSETTES, now).cycle2_token()
        source = LiveSource(now, args.token, cycle2)
    else:
        source = CassetteSource(CASSETTES, now)
    agent = Agent(source, store, now)
    steps = agent.run()
    write_artifacts(steps, agent.results, args.artifacts)
    print(render_transcript(steps), end="")
    print(f"wrote {args.artifacts / 'demo-run.txt'}")
    if len(agent.results) >= 2:
        t1, t2 = agent.results[0].token_id, agent.results[1].token_id
        print(f"next: asof explain {t1}.mid")
        print(f"      asof explain {t2}.closed")
    store.close()
    return 0


def _query(args: argparse.Namespace) -> int:
    store = Store(args.db)
    rows = store.query(args.token)
    if not rows:
        print(f"no state for {args.token}", file=sys.stderr)
        return 1
    print(f"{'field':22} {'value':>12} {'winner':>10}  rule")
    for row in rows:
        value = json.loads(row["value"]) if row["value"] is not None else None
        print(f"{row['field']:22} {_fmt(value):>12} {row['winner']:>10}  {row['rule_id']}")
    store.close()
    return 0


def _explain(args: argparse.Namespace) -> int:
    if "." not in args.target:
        print("usage: asof explain TOKEN.field", file=sys.stderr)
        return 2
    token, field = args.target.split(".", 1)
    store = Store(args.db)
    row = store.explain(token, field)
    if not row:
        print(f"no field {args.target}", file=sys.stderr)
        return 1
    value = json.loads(row["value"]) if row["value"] is not None else None
    live = json.loads(row["live"]) if row["live"] is not None else None
    warehouse = json.loads(row["warehouse"]) if row["warehouse"] is not None else None
    print(f"{token}.{field}")
    print(f"  value      {_fmt(value)}")
    print(f"  winner     {row['winner']}")
    print(f"  rule       {row['rule_id']}")
    print(f"  live       {_fmt(live)}")
    print(f"  warehouse  {_fmt(warehouse)}")
    print(f"  as_of      {row['as_of']}")
    print(f"  {row['reason']}")
    store.close()
    return 0


def _fmt(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
