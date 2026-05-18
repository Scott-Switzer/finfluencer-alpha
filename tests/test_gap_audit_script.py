from __future__ import annotations

from pathlib import Path

from scripts import v2_critical_defense_utils as utils
from scripts.build_v2_gap_audit import main


def test_gap_audit_writes_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(utils, "OUT_DIR", tmp_path / "pkg")
    (tmp_path / "pkg").mkdir(parents=True)
    monkeypatch.setattr(utils, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.py").write_text("ok\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    assert main() == 0
    gap = tmp_path / "pkg" / "gap_audit"
    assert (gap / "gap_audit_summary.md").exists()
    assert (gap / "gap_audit_findings.csv").exists()
