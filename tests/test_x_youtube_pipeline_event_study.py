from pathlib import Path

import pandas as pd

from finfluencer_alpha import x_youtube_pipeline as pipeline


def _configure_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    project_root = tmp_path
    overnight_dir = tmp_path / "data/exports/overnight_collection"
    event_dir = tmp_path / "data/exports/x_youtube_event_study"
    returns_dir = tmp_path / "data/exports/research_expansion_audit"
    overnight_dir.mkdir(parents=True)
    event_dir.mkdir(parents=True)
    returns_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_event_id": "yt1",
                "source_type": "youtube_recommendation",
                "ticker": "TSLA",
                "creator": "Creator",
                "attention_category": "x_pre_attention",
            }
        ]
    ).to_csv(overnight_dir / "06_integrated_event_inventory.csv", index=False)
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(pipeline, "OVERNIGHT_DIR", overnight_dir)
    monkeypatch.setattr(pipeline, "EVENT_STUDY_DIR", event_dir)
    return project_root, overnight_dir, event_dir


def test_event_study_placeholders_handles_missing_benchmark_ticker(monkeypatch, tmp_path: Path) -> None:
    project_root, _, event_dir = _configure_paths(monkeypatch, tmp_path)
    returns_path = project_root / "data/exports/research_expansion_audit/05_verified_event_window_returns.csv"
    pd.DataFrame(
        [
            {
                "event_id": "1",
                "horizon": "1D",
                "raw_stock_return": 0.03,
                "abnormal_return_SPY": 0.01,
                "abnormal_return_QQQ": 0.02,
            }
        ]
    ).to_csv(returns_path, index=False)

    result = pipeline.build_event_study_placeholders()

    summary = pd.read_csv(event_dir / "event_window_summary.csv")
    assert set(summary["benchmark_ticker"]) == {"SPY", "QQQ"}
    assert "missing benchmark_ticker" in " ".join(result["warnings"])


def test_event_study_placeholders_handles_empty_returns(monkeypatch, tmp_path: Path) -> None:
    project_root, _, event_dir = _configure_paths(monkeypatch, tmp_path)
    returns_path = project_root / "data/exports/research_expansion_audit/05_verified_event_window_returns.csv"
    pd.DataFrame(columns=["event_id", "horizon", "abnormal_return_SPY"]).to_csv(
        returns_path, index=False
    )

    result = pipeline.build_event_study_placeholders()

    summary = pd.read_csv(event_dir / "event_window_summary.csv")
    assert list(summary.columns) == ["horizon", "benchmark_ticker", "N"]
    assert summary.empty
    assert "event_window_returns input was empty" in result["warnings"]


def test_event_study_placeholders_handles_long_benchmark_ticker(monkeypatch, tmp_path: Path) -> None:
    project_root, _, event_dir = _configure_paths(monkeypatch, tmp_path)
    returns_path = project_root / "data/exports/research_expansion_audit/05_verified_event_window_returns.csv"
    pd.DataFrame(
        [
            {
                "event_id": "1",
                "horizon": "1D",
                "benchmark_ticker": "SPY",
                "abnormal_return": 0.01,
                "raw_stock_return": 0.03,
            },
            {
                "event_id": "2",
                "horizon": "1D",
                "benchmark_ticker": "SPY",
                "abnormal_return": -0.02,
                "raw_stock_return": -0.01,
            },
        ]
    ).to_csv(returns_path, index=False)

    result = pipeline.build_event_study_placeholders()

    summary = pd.read_csv(event_dir / "event_window_summary.csv")
    assert summary.loc[0, "benchmark_ticker"] == "SPY"
    assert summary.loc[0, "N"] == 2
    assert result["warnings"] == []
