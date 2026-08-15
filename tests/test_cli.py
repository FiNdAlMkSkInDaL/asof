from __future__ import annotations

from pathlib import Path

from asof.cli import main

TOKEN = "54533043819946592547517511176940999955633860128497669742211153063842200957669"


def test_dead_cycle1_writes_branch_not_demo(tmp_path: Path, capsys):
    art = tmp_path / "art"
    art.mkdir()
    (art / "demo-run.txt").write_text("sentinel\n", encoding="utf-8")
    db = tmp_path / "branch.sqlite"
    assert main(["demo", "--dead-cycle1", "--db", str(db), "--artifacts", str(art)]) == 0
    out = capsys.readouterr()
    assert "already dead" in out.out
    assert "C2 PLAN" in out.out
    assert (art / "demo-run.txt").read_text(encoding="utf-8") == "sentinel\n"
    text = (art / "branch-run.txt").read_text(encoding="utf-8")
    assert "already dead" in text
    assert not (art / "cycle1.json").exists()
    assert not (art / "cycles.json").exists()


def test_dead_cycle1_rejects_live():
    assert main(["demo", "--live", "--dead-cycle1", "--token", TOKEN]) == 2


def test_explain_after_default_demo(tmp_path: Path, capsys):
    art = tmp_path / "art"
    db = tmp_path / "asof.sqlite"
    assert main(["demo", "--db", str(db), "--artifacts", str(art)]) == 0
    capsys.readouterr()
    assert main(["explain", f"{TOKEN}.best_bid", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "HOLD" in out
    assert "R-BOOK-DEAD" in out
