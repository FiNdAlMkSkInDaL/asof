from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from asof.agent import Agent, render_transcript, write_artifacts
from asof.store import Store
from asof.tools import CassetteSource, DeadOpenSource, LiveSource

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

    demo = sub.add_parser("demo", help="Run reconciliation (two cassette snapshots, or one live cycle)")
    demo.add_argument("--live", action="store_true", help="Hit public Polymarket APIs for one cycle")
    demo.add_argument(
        "--dead-cycle1",
        action="store_true",
        help="Serve the closed cassette row on the open fetch so cycle 1 is dead and the planner halts",
    )
    demo.add_argument("--token", help="Token id (required with --live)")
    demo.add_argument("--db", type=Path, default=None)
    demo.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    demo.add_argument("--reset", action="store_true", help="Allow deleting a non-default --db")

    query = sub.add_parser("query", help="Print reconciled state for a token")
    query.add_argument("token")
    query.add_argument("--db", type=Path, default=DEFAULT_DB)

    explain = sub.add_parser("explain", help="Explain one field, e.g. TOKEN.best_bid")
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
    if args.live and args.dead_cycle1:
        print("choose one of --live or --dead-cycle1", file=sys.stderr)
        return 2
    branch_db = ARTIFACTS / "branch.sqlite"
    if args.db is None:
        args.db = branch_db if args.dead_cycle1 else DEFAULT_DB
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        scratch = {
            DEFAULT_DB.resolve(),
            branch_db.resolve(),
        }
        if args.db.resolve() in scratch or args.reset:
            args.db.unlink()
        else:
            print("refusing to destroy --db without --reset", file=sys.stderr)
            return 2
    store = Store(args.db)
    if args.live:
        if not args.token:
            print("live mode requires --token", file=sys.stderr)
            return 2
        source = LiveSource(now, args.token)
        print("live mode is one network cycle; the closed snapshot is cassette-only", file=sys.stderr)
        transcript = "live-run.txt"
        write_cycles = True
    elif args.dead_cycle1:
        source = DeadOpenSource(CassetteSource(CASSETTES, now))
        transcript = "branch-run.txt"
        write_cycles = False
        print(
            "dead-cycle1: warehouse snapshot 'open' returns the closed cassette row; planner should halt",
            file=sys.stderr,
        )
    else:
        source = CassetteSource(CASSETTES, now)
        transcript = "demo-run.txt"
        write_cycles = True
    agent = Agent(source, store, now)
    steps = agent.run()
    write_artifacts(
        steps,
        agent.results,
        args.artifacts,
        transcript_name=transcript,
        write_cycles=write_cycles,
    )
    print(render_transcript(steps), end="")
    print(f"wrote {args.artifacts / transcript}")
    if agent.results and not args.dead_cycle1:
        token = agent.results[0].token_id
        print(f"next: python -m asof explain {token}.best_bid")
        if _closed_true(agent.results):
            print(f"      python -m asof explain {token}.closed")
    store.close()
    return 0


def _closed_true(results: list) -> bool:
    for result in results:
        try:
            d = result.by_field("closed")
        except KeyError:
            continue
        if d.warehouse is True:
            return True
    return False


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
        print("usage: python -m asof explain TOKEN.field", file=sys.stderr)
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
