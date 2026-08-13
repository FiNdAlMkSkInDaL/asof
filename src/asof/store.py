from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from asof.types import ReconcileResult, Winner


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Winner):
        return json.dumps(value.value)
    if isinstance(value, datetime):
        return json.dumps(value.isoformat())
    return json.dumps(value)


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fields (
                token_id TEXT NOT NULL,
                field TEXT NOT NULL,
                cycle INTEGER NOT NULL,
                value TEXT,
                live TEXT,
                warehouse TEXT,
                winner TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                as_of TEXT NOT NULL,
                conflict INTEGER NOT NULL,
                PRIMARY KEY (token_id, field, cycle)
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def put(self, result: ReconcileResult, cycle: int) -> None:
        for d in result.decisions:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO fields
                (token_id, field, cycle, value, live, warehouse, winner, rule_id, reason, as_of, conflict)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.token_id,
                    d.field,
                    cycle,
                    _dump(d.value),
                    _dump(d.live),
                    _dump(d.warehouse),
                    d.winner.value,
                    d.rule_id,
                    d.reason,
                    d.as_of.isoformat(),
                    int(d.conflict),
                ),
            )
        self.conn.commit()

    def previous(self, token_id: str) -> dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT field, value FROM fields
            WHERE token_id = ? AND cycle = (
                SELECT COALESCE(MAX(cycle), 0) FROM fields WHERE token_id = ?
            )
            """,
            (token_id, token_id),
        ).fetchall()
        out: dict[str, Any] = {}
        for row in rows:
            out[row["field"]] = json.loads(row["value"]) if row["value"] is not None else None
        return out

    def query(self, token_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM fields
            WHERE token_id = ? AND cycle = (
                SELECT COALESCE(MAX(cycle), 0) FROM fields WHERE token_id = ?
            )
            ORDER BY field
            """,
            (token_id, token_id),
        ).fetchall()

    def explain(self, token_id: str, field: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT * FROM fields
            WHERE token_id = ? AND field = ?
            ORDER BY cycle DESC
            LIMIT 1
            """,
            (token_id, field),
        ).fetchone()
