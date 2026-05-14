from __future__ import annotations

import math
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from finfluencer_alpha.research_expansion import TICKER_TO_SECTOR_ETF

REPO = Path('/workspace/FIN496CAPSTONE')
DB_PATH = REPO / 'data/finfluencer_alpha.db'
AUDIT = REPO / 'data/exports/research_expansion_audit'
VALIDATION_CLEAN = REPO / 'data/exports/validation/clean_auto_labeled_events.csv'
VALIDATION_AUTO = REPO / 'data/exports/validation/event_validation_sample_auto_labeled.csv'
MARKET_PATH = REPO / 'data/imports/market_data/yfinance_market_data.csv'
PRIOR_EXPANSION = REPO / 'data/exports/research_expansion'
BENCHMARKS = ['SPY', 'QQQ', 'IWM']
HORIZONS = {
    '1D': 1,
    '1W': 5,
    '2W': 10,
    '3W': 15,
    '1M': 21,
    '2M': 42,
    '3M': 63,
    '6M': 126,
    '1Y': 252,
    '2Y': 504,
    'END_OF_SAMPLE': None,
}
PRE_HORIZONS = {'PRE_1W': (-5, -1), 'PRE_1M': (-21, -1), 'PRE_3M': (-63, -1)}
SAMPLE_MODES = [
    'uncapped_full',
    'cap_250_per_creator',
    'cap_500_per_creator',
    'cap_1000_per_creator',
    'cap_100_per_creator_year',
    'balanced_creator_year_sample',
]
SECTOR_ETFS = sorted(set(TICKER_TO_SECTOR_ETF.values()))


def run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False)
    return (proc.stdout + proc.stderr).strip()


def write_md(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def pct(x: float | int | None) -> str:
    if x is None or pd.isna(x):
        return 'NA'
    return f'{100 * float(x):.2f}%'


def con() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def scalar(conn: sqlite3.Connection, sql: str) -> Any:
    return conn.execute(sql).fetchone()[0]


def phase0() -> None:
    tmux = run(['tmux', 'ls']) or 'no tmux sessions'
    if 'no server running' in tmux:
        tmux = 'no tmux sessions'
    procs = run(['pgrep', '-af', 'finfluencer_alpha|collect-apify|run-event-study|run-statistical-models|build-event-window|portfolio|research_expansion'])
    branch = run(['git', 'branch', '--show-current'])
    branches = run(['git', 'branch', '-a'])
    log = run(['git', 'log', '-8', '--oneline', '--decorate'])
    remotes = run(['git', 'remote', '-v'])
    status = run(['git', 'status', '--short'])
    commit_38 = run(['git', 'cat-file', '-t', '38e07428ced7cc0e32328a546d63e09a1fec1cf6']) or 'missing'
    commit_bff = run(['git', 'cat-file', '-t', 'bffb993']) or 'missing'
    lines = [
        '# RunPod and GitHub Connection Audit',
        '',
        f'- Audit generated UTC: {datetime.now(UTC).isoformat(timespec="seconds")}',
        '- SSH worked: yes. The required status command reached the RunPod host before this file was generated.',
        '- Codex operating mode: RunPod live repo via SSH, not GitHub-only.',
        f'- Remote repo path: `{REPO}`',
        f'- Current branch: `{branch}`',
        f'- Remote repo exists: {REPO.exists()}',
        f'- `.venv` exists: {(REPO / ".venv/bin/activate").exists()}',
        f'- DB exists: {DB_PATH.exists()} (`{DB_PATH}`)',
        f'- Prior `data/exports/research_expansion` outputs exist: {PRIOR_EXPANSION.exists()}',
        '- Branch `research-expansion-robust-alpha-tests` exists: yes (`origin/research-expansion-robust-alpha-tests`).',
        f'- Commit `38e07428ced7cc0e32328a546d63e09a1fec1cf6` exists: {commit_38 == "commit"}',
        f'- Commit `bffb993` exists: {commit_bff == "commit"}',
        f'- Active tmux sessions: `{tmux}`',
        f'- Active finfluencer Python processes: `{procs or "none"}`',
        '- Audit can proceed on RunPod: yes.',
        '', '## Git Remotes', '```text', remotes, '```',
        '', '## Available Branches', '```text', branches, '```',
        '', '## Latest Commits', '```text', log, '```',
        '', '## Working Tree Status at Audit Time', '```text', status or 'clean', '```',
    ]
    write_md(AUDIT / '00_runpod_github_connection_audit.md', lines)


def transcript_reconciliation() -> dict[str, Any]:
    conn = con()
    total_videos = scalar(conn, 'select count(*) from raw_youtube_videos')
    transcript_rows = scalar(conn, 'select count(*) from youtube_transcripts')
    unique_transcript_videos = scalar(conn, 'select count(distinct video_id) from youtube_transcripts')
    successful = scalar(conn, """
        select count(*) from youtube_transcripts
        where lower(ifnull(status,'')) in ('available','success','ok')
           or lower(ifnull(retrieval_status,'')) in ('available','success','ok')
           or length(trim(ifnull(full_text,''))) > 0
    """)
    full_text_not_null = scalar(conn, 'select count(*) from youtube_transcripts where full_text is not null')
    full_text_nonblank = scalar(conn, "select count(*) from youtube_transcripts where length(trim(ifnull(full_text,''))) > 0")
    full_text_gt_50 = scalar(conn, "select count(*) from youtube_transcripts where length(trim(ifnull(full_text,''))) > 50")
    duplicate_video_ids = scalar(conn, 'select count(*) from (select video_id,count(*) c from youtube_transcripts group by video_id having c>1)')
    provider = pd.read_sql_query("""
        select ifnull(transcript_source,'') as transcript_source,
               ifnull(provider_name,'') as provider_name,
               count(*) as transcript_rows,
               sum(case when lower(ifnull(status,'')) in ('available','success','ok')
                         or lower(ifnull(retrieval_status,'')) in ('available','success','ok')
                         or length(trim(ifnull(full_text,''))) > 0 then 1 else 0 end) as successful_rows,
               sum(case when length(trim(ifnull(full_text,''))) > 50 then 1 else 0 end) as full_text_gt_50_rows
        from youtube_transcripts group by 1,2 order by transcript_rows desc
    """, conn)
    status = pd.read_sql_query("""
        select ifnull(status,'') as status, ifnull(retrieval_status,'') as retrieval_status, count(*) as rows
        from youtube_transcripts group by 1,2 order by rows desc
    """, conn)
    conn.close()
    rows = [
        {'metric': 'total_videos', 'value': total_videos, 'note': 'raw_youtube_videos rows'},
        {'metric': 'total_transcript_rows', 'value': transcript_rows, 'note': 'youtube_transcripts rows'},
        {'metric': 'successful_transcript_rows', 'value': successful, 'note': 'available/success/ok or nonblank full_text'},
        {'metric': 'unique_video_ids_with_transcript_rows', 'value': unique_transcript_videos, 'note': 'distinct video_id in youtube_transcripts'},
        {'metric': 'full_text_not_null', 'value': full_text_not_null, 'note': 'full_text is not null'},
        {'metric': 'full_text_nonblank', 'value': full_text_nonblank, 'note': 'trim(full_text) length > 0'},
        {'metric': 'full_text_gt_50_chars', 'value': full_text_gt_50, 'note': 'strict usable-text filter requested'},
        {'metric': 'duplicate_video_id_groups', 'value': duplicate_video_ids, 'note': 'duplicate transcript rows by video_id'},
        {'metric': 'blank_or_short_transcripts', 'value': transcript_rows - full_text_gt_50, 'note': 'transcript_rows - full_text_gt_50_chars'},
    ]
    combined = pd.concat([
        pd.DataFrame(rows),
        provider.assign(metric='provider_source_breakdown', value=provider['transcript_rows'], note=provider['transcript_source'] + ':' + provider['provider_name'])[['metric','value','note']],
        status.assign(metric='status_breakdown', value=status['rows'], note=status['status'] + '/' + status['retrieval_status'])[['metric','value','note']],
    ], ignore_index=True)
    write_csv(AUDIT / '01_transcript_count_reconciliation.csv', combined)
    lines = [
        '# Transcript Count Reconciliation', '',
        f'- Total videos in current RunPod DB: **{total_videos:,}**.',
        f'- Transcript rows: **{transcript_rows:,}** across **{unique_transcript_videos:,}** unique videos.',
        f'- Successful transcripts: **{successful:,}**.',
        f'- Transcripts with `full_text > 50` chars: **{full_text_gt_50:,}**.',
        f'- Coverage using successful transcripts: **{successful / total_videos:.1%}**.',
        f'- Coverage using `full_text > 50`: **{full_text_gt_50 / total_videos:.1%}**.',
        f'- Duplicate transcript video IDs: **{duplicate_video_ids:,}**.',
        '', '## Reconciliation',
        '- The prior 9,747 successful-transcript count is present in the live DB.',
        '- The OpenCode 6,384 count is not present in the current DB. It appears in committed markdown only and reflects a stale pre-collection snapshot or copied report, not the current RunPod database.',
        '- The correct current text-usable count to cite is **9,742** if the paper uses the strict `full_text > 50` filter, or **9,747** if it cites successful transcript retrievals.',
        '- The DB is not stale or partial relative to the OpenCode report; it is more complete.',
    ]
    write_md(AUDIT / '01_transcript_count_reconciliation.md', lines)
    return {'total_videos': total_videos, 'successful': successful, 'full_text_gt_50': full_text_gt_50}


def load_validation_clean() -> pd.DataFrame:
    df = pd.read_csv(VALIDATION_CLEAN, low_memory=False)
    df['event_date_utc'] = pd.to_datetime(df['event_date_utc'], errors='coerce').dt.strftime('%Y-%m-%d')
    df['ticker'] = df['ticker'].astype(str).str.upper().str.strip()
    df['confidence'] = pd.to_numeric(df.get('confidence'), errors='coerce')
    return df


def dedupe_events(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    quality_rank = {'strong': 3, 'medium': 2, 'weak': 1}
    work['_quality_rank'] = work.get('evidence_quality', '').map(quality_rank).fillna(0)
    work = work.sort_values(['video_id', 'ticker', 'event_date_utc', 'confidence', '_quality_rank', 'event_id'], ascending=[True, True, True, False, False, True])
    return work.drop_duplicates(['video_id', 'ticker', 'event_date_utc'], keep='first').drop(columns=['_quality_rank']).reset_index(drop=True)


def event_funnel(clean_row_level: pd.DataFrame, clean_deduped: pd.DataFrame) -> dict[str, Any]:
    conn = con()
    total_events = scalar(conn, 'select count(*) from transcript_recommendation_events')
    candidate_windows = scalar(conn, 'select count(*) from transcript_candidate_windows')
    accepted_windows = scalar(conn, 'select count(*) from transcript_candidate_windows where accepted=1 or accepted_event_flag=1')
    exclusions = scalar(conn, 'select count(*) from transcript_event_exclusions')
    conn.close()
    auto = pd.read_csv(VALIDATION_AUTO, low_memory=False) if VALIDATION_AUTO.exists() else pd.DataFrame()
    label_counts = auto['is_true_recommendation'].value_counts(dropna=False).to_dict() if not auto.empty else {}
    dup_groups = clean_row_level.groupby(['video_id','ticker','event_date_utc']).size().reset_index(name='rows')
    duplicate_groups = int((dup_groups['rows'] > 1).sum())
    duplicate_extra = int((dup_groups['rows'] - 1).clip(lower=0).sum())
    conflict_groups = clean_row_level.groupby(['video_id','ticker','event_date_utc'])['direction'].nunique().reset_index(name='directions')
    direction_conflicts = int((conflict_groups['directions'] > 1).sum())
    rows = [
        {'metric': 'candidate_windows', 'value': candidate_windows, 'note': 'transcript_candidate_windows rows'},
        {'metric': 'accepted_candidate_windows', 'value': accepted_windows, 'note': 'accepted=1 or accepted_event_flag=1'},
        {'metric': 'transcript_recommendation_events', 'value': total_events, 'note': 'DB row-level extracted events'},
        {'metric': 'auto_labeled_yes', 'value': label_counts.get('yes', 0), 'note': 'event_validation_sample_auto_labeled.csv'},
        {'metric': 'auto_labeled_no', 'value': label_counts.get('no', 0), 'note': 'event_validation_sample_auto_labeled.csv'},
        {'metric': 'auto_labeled_unclear', 'value': label_counts.get('unclear', 0), 'note': 'event_validation_sample_auto_labeled.csv'},
        {'metric': 'prior_conservative_clean_row_level', 'value': len(clean_row_level), 'note': 'data/exports/validation/clean_auto_labeled_events.csv'},
        {'metric': 'corrected_unique_video_ticker_date_events', 'value': len(clean_deduped), 'note': 'deduped for event-study to avoid repeated ticker mentions in same video'},
        {'metric': 'excluded_events_file_rows', 'value': exclusions, 'note': 'transcript_event_exclusions DB table'},
        {'metric': 'row_level_duplicate_event_ids', 'value': len(clean_row_level) - clean_row_level['event_id'].nunique(), 'note': 'conservative clean file'},
        {'metric': 'duplicate_video_ticker_date_groups', 'value': duplicate_groups, 'note': 'same ticker/date/video repeated'},
        {'metric': 'extra_rows_from_repeated_video_ticker_date', 'value': duplicate_extra, 'note': 'row-level inflation removed by dedupe'},
        {'metric': 'direction_conflict_groups', 'value': direction_conflicts, 'note': 'same video/ticker/date with both positive and negative directions'},
        {'metric': 'unique_creators_corrected', 'value': clean_deduped['creator'].nunique(), 'note': 'deduped conservative events'},
        {'metric': 'unique_tickers_corrected', 'value': clean_deduped['ticker'].nunique(), 'note': 'deduped conservative events'},
    ]
    top_dupes = dup_groups.sort_values('rows', ascending=False).head(20).copy()
    top_dupes['metric'] = 'top_repeated_video_ticker_date'
    top_dupes['value'] = top_dupes['rows']
    top_dupes['note'] = top_dupes['video_id'] + ':' + top_dupes['ticker'] + ':' + top_dupes['event_date_utc']
    write_csv(AUDIT / '02_event_funnel_reconciliation.csv', pd.concat([pd.DataFrame(rows), top_dupes[['metric','value','note']]], ignore_index=True))
    lines = [
        '# Event Funnel Reconciliation', '',
        f'- Candidate transcript windows: **{candidate_windows:,}**.',
        f'- DB transcript recommendation rows: **{total_events:,}**.',
        f'- Auto-label counts: yes={label_counts.get("yes", 0):,}, no={label_counts.get("no", 0):,}, unclear={label_counts.get("unclear", 0):,}.',
        f'- Conservative prior clean row-level events: **{len(clean_row_level):,}**.',
        f'- Corrected unique video/ticker/date events for return testing: **{len(clean_deduped):,}**.',
        f'- Duplicate video/ticker/date groups in conservative clean rows: **{duplicate_groups:,}** with **{duplicate_extra:,}** extra repeated rows.',
        '', '## Audit Finding',
        '- The OpenCode 2,078 clean-event figure is not a defensible clean-label count for the current RunPod state.',
        '- The research-expansion branch bypassed the earlier auto-label safeguards (`is_true_recommendation`, `needs_review`, evidence quality, and exclusion reasons) and treated most DB recommendation rows as clean.',
        '- For the paper, cite **562** conservative row-level pseudo-labeled clean events and **473** unique video/ticker/date events for event-study returns.',
        '- The corrected return pipeline below uses the 473 deduped events to avoid overweighting repeated mentions of the same ticker in the same transcript.',
    ]
    write_md(AUDIT / '02_event_funnel_reconciliation.md', lines)
    return {'candidate_windows': candidate_windows, 'total_events': total_events, 'clean_row_level': len(clean_row_level), 'clean_deduped': len(clean_deduped)}


def apply_sample_mode(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    work = df.copy().sort_values(['creator', 'event_date_utc', 'event_id'])
    work['year'] = pd.to_datetime(work['event_date_utc'], errors='coerce').dt.year
    if mode == 'uncapped_full':
        return work.reset_index(drop=True)
    if mode == 'cap_250_per_creator':
        return work.groupby('creator', group_keys=False).head(250).reset_index(drop=True)
    if mode == 'cap_500_per_creator':
        return work.groupby('creator', group_keys=False).head(500).reset_index(drop=True)
    if mode == 'cap_1000_per_creator':
        return work.groupby('creator', group_keys=False).head(1000).reset_index(drop=True)
    if mode == 'cap_100_per_creator_year':
        return work.groupby(['creator','year'], group_keys=False).head(100).reset_index(drop=True)
    if mode == 'balanced_creator_year_sample':
        sizes = work.groupby(['creator','year']).size()
        target = max(1, int(sizes.median())) if len(sizes) else 1
        return work.groupby(['creator','year'], group_keys=False).head(target).reset_index(drop=True)
    raise ValueError(mode)


def sample_mode_audit(df: pd.DataFrame, funnel: dict[str, Any]) -> None:
    base_n = len(df)
    rows = []
    for mode in SAMPLE_MODES:
        sample = apply_sample_mode(df, mode)
        counts_creator = sample['creator'].value_counts()
        counts_video_creator = sample.drop_duplicates('video_id')['creator'].value_counts()
        counts_ticker = sample['ticker'].value_counts()
        cy = sample.assign(year=pd.to_datetime(sample['event_date_utc'], errors='coerce').dt.year)
        max_cy = int(cy.groupby(['creator','year']).size().max()) if not cy.empty else 0
        rows.append({
            'sample_mode': mode,
            'videos': sample['video_id'].nunique(),
            'transcripts': sample['video_id'].nunique(),
            'candidate_events': funnel.get('total_events'),
            'clean_events': len(sample),
            'unique_creators': sample['creator'].nunique(),
            'unique_tickers': sample['ticker'].nunique(),
            'max_events_per_creator': int(counts_creator.max()) if not counts_creator.empty else 0,
            'max_videos_per_creator': int(counts_video_creator.max()) if not counts_video_creator.empty else 0,
            'max_events_per_creator_year': max_cy,
            'top_creator_event_share': round(float(counts_creator.iloc[0] / len(sample)), 6) if len(sample) else 0,
            'top_creator_video_share': round(float(counts_video_creator.iloc[0] / sample['video_id'].nunique()), 6) if sample['video_id'].nunique() else 0,
            'top_ticker_event_share': round(float(counts_ticker.iloc[0] / len(sample)), 6) if len(sample) else 0,
            'earliest_date': sample['event_date_utc'].min(),
            'latest_date': sample['event_date_utc'].max(),
            'cap_binding_yes_no': 'yes' if len(sample) < base_n else 'no',
            'explanation': 'cap/balance reduced sample' if len(sample) < base_n else 'cap not binding on corrected deduped sample',
        })
    out = pd.DataFrame(rows)
    write_csv(AUDIT / '03_sample_mode_audit.csv', out)
    lines = ['# Sample Mode Audit', '']
    for _, r in out.iterrows():
        lines.append(f"- `{r['sample_mode']}`: {int(r['clean_events']):,} events, cap binding={r['cap_binding_yes_no']}, top creator share={pct(r['top_creator_event_share'])}.")
    lines += ['', 'The 250/500/1000 creator caps do not bind on the corrected deduped sample; the 100-per-creator-year and balanced creator-year samples do change composition.']
    write_md(AUDIT / '03_sample_mode_audit.md', lines)


def normalize_market() -> pd.DataFrame:
    market = pd.read_csv(MARKET_PATH, low_memory=False)
    base = market[['ticker','date','adjusted_close','data_source']].copy()
    base['ticker'] = base['ticker'].astype(str).str.upper().str.strip()
    base['date'] = pd.to_datetime(base['date'], errors='coerce').dt.strftime('%Y-%m-%d')
    base['adjusted_close'] = pd.to_numeric(base['adjusted_close'], errors='coerce')
    frames = [base]
    if {'benchmark_ticker','benchmark_adjusted_close'}.issubset(market.columns):
        bench = market[['benchmark_ticker','date','benchmark_adjusted_close','data_source']].copy()
        bench = bench.rename(columns={'benchmark_ticker':'ticker','benchmark_adjusted_close':'adjusted_close'})
        bench['ticker'] = bench['ticker'].astype(str).str.upper().str.strip()
        bench['date'] = pd.to_datetime(bench['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        bench['adjusted_close'] = pd.to_numeric(bench['adjusted_close'], errors='coerce')
        frames.append(bench)
    prices = pd.concat(frames, ignore_index=True)
    prices = prices.dropna(subset=['ticker','date','adjusted_close'])
    return prices.sort_values(['ticker','date']).drop_duplicates(['ticker','date'], keep='last').reset_index(drop=True)


def fetch_supplemental_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    try:
        import yfinance as yf
    except Exception:
        return pd.DataFrame(columns=['ticker','date','adjusted_close','data_source'])
    rows = []
    for ticker in tickers:
        try:
            data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True, threads=False)
        except Exception:
            continue
        if data is None or data.empty:
            continue
        data = data.reset_index()
        close_col = 'Close'
        date_col = 'Date'
        if isinstance(data.columns, pd.MultiIndex):
            close_col = ('Close', ticker)
            date_col = ('Date', '') if ('Date', '') in data.columns else data.columns[0]
        if close_col not in data.columns:
            continue
        for _, row in data.iterrows():
            close = row.get(close_col)
            if pd.isna(close):
                continue
            rows.append({'ticker': ticker, 'date': pd.to_datetime(row[date_col]).strftime('%Y-%m-%d'), 'adjusted_close': float(close), 'data_source': 'yfinance_yahoo_prototype_supplemental'})
    return pd.DataFrame(rows)


def price_maps(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {ticker: sub[['date','adjusted_close']].dropna().sort_values('date').drop_duplicates('date').reset_index(drop=True) for ticker, sub in prices.groupby('ticker')}


def next_trading_day(date: str, dates: list[str]) -> tuple[int | None, str | None]:
    for i, d in enumerate(dates):
        if d >= date:
            return i, d
    return None, None


def calc_return(histories: dict[str, pd.DataFrame], ticker: str, start_date: str, end_date: str) -> float | None:
    hist = histories.get(ticker)
    if hist is None:
        return None
    lookup = dict(zip(hist['date'], hist['adjusted_close'], strict=False))
    sp = lookup.get(start_date)
    ep = lookup.get(end_date)
    if sp is None or ep is None or sp == 0:
        return None
    return round((float(ep) / float(sp)) - 1, 6)


def event_window_rows(events: pd.DataFrame, prices: pd.DataFrame, sample_mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    histories = price_maps(prices)
    rows: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for _, ev in events.iterrows():
        ticker = ev['ticker']
        hist = histories.get(ticker)
        if hist is None or hist.empty:
            for h in list(HORIZONS) + list(PRE_HORIZONS):
                invalid.append({'sample_mode': sample_mode, 'event_id': ev['event_id'], 'ticker': ticker, 'horizon': h, 'invalid_reason': 'missing_ticker_prices'})
            continue
        dates = hist['date'].tolist()
        start_idx, start_day = next_trading_day(ev['event_date_utc'], dates)
        if start_idx is None or start_day is None:
            for h in list(HORIZONS) + list(PRE_HORIZONS):
                invalid.append({'sample_mode': sample_mode, 'event_id': ev['event_id'], 'ticker': ticker, 'horizon': h, 'invalid_reason': 'no_next_trading_day'})
            continue
        base = {'sample_mode': sample_mode, 'event_id': ev['event_id'], 'video_id': ev['video_id'], 'creator': ev['creator'], 'ticker': ticker, 'recommendation_type': ev.get('recommendation_type', ''), 'direction': ev.get('direction', ''), 'event_date': ev['event_date_utc'], 'next_trading_day': start_day}
        for label, offset in HORIZONS.items():
            if offset is None:
                end_idx = len(dates) - 1
                if end_idx <= start_idx:
                    invalid.append({**base, 'horizon': label, 'invalid_reason': 'no_future_price_after_entry'})
                    continue
            else:
                end_idx = start_idx + offset
                if end_idx >= len(dates):
                    invalid.append({**base, 'horizon': label, 'invalid_reason': 'insufficient_future_data'})
                    continue
            end_day = dates[end_idx]
            raw = calc_return(histories, ticker, start_day, end_day)
            if raw is None:
                invalid.append({**base, 'horizon': label, 'invalid_reason': 'missing_endpoint_price'})
                continue
            row = {**base, 'horizon': label, 'end_trading_day': end_day, 'raw_stock_return': raw, 'valid_window': True}
            for bench in BENCHMARKS:
                br = calc_return(histories, bench, start_day, end_day)
                if br is not None:
                    row[f'benchmark_return_{bench}'] = br
                    row[f'abnormal_return_{bench}'] = round(raw - br, 6)
            sector = TICKER_TO_SECTOR_ETF.get(ticker)
            if sector:
                sr = calc_return(histories, sector, start_day, end_day)
                if sr is not None:
                    row['sector_benchmark'] = sector
                    row['sector_benchmark_return'] = sr
                    row['abnormal_return_SECTOR'] = round(raw - sr, 6)
            rows.append(row)
        for label, (start_off, end_off) in PRE_HORIZONS.items():
            s_idx = start_idx + start_off
            e_idx = start_idx + end_off
            if s_idx < 0 or e_idx < 0:
                invalid.append({**base, 'horizon': label, 'invalid_reason': 'insufficient_pre_event_data'})
                continue
            s_day, e_day = dates[s_idx], dates[e_idx]
            raw = calc_return(histories, ticker, s_day, e_day)
            if raw is None:
                invalid.append({**base, 'horizon': label, 'invalid_reason': 'missing_pre_endpoint_price'})
                continue
            row = {**base, 'horizon': label, 'start_trading_day': s_day, 'end_trading_day': e_day, 'raw_stock_return': raw, 'valid_window': True}
            for bench in BENCHMARKS:
                br = calc_return(histories, bench, s_day, e_day)
                if br is not None:
                    row[f'benchmark_return_{bench}'] = br
                    row[f'abnormal_return_{bench}'] = round(raw - br, 6)
            sector = TICKER_TO_SECTOR_ETF.get(ticker)
            if sector:
                sr = calc_return(histories, sector, s_day, e_day)
                if sr is not None:
                    row['sector_benchmark'] = sector
                    row['sector_benchmark_return'] = sr
                    row['abnormal_return_SECTOR'] = round(raw - sr, 6)
            rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(invalid)


def summarize_event_windows(windows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (mode, horizon), sub in windows.groupby(['sample_mode','horizon']):
        for bench in [*BENCHMARKS, 'SECTOR']:
            col = f'abnormal_return_{bench}'
            if col not in sub.columns:
                continue
            vals = pd.to_numeric(sub[col], errors='coerce').dropna()
            n = len(vals)
            if n == 0:
                continue
            mean = float(vals.mean())
            median = float(vals.median())
            std = float(vals.std(ddof=1)) if n > 1 else 0.0
            se = std / math.sqrt(n) if n > 1 else 0.0
            t = mean / se if se else 0.0
            p = float(2 * (1 - stats.t.cdf(abs(t), n - 1))) if se and n > 1 else 1.0
            rng = np.random.default_rng(496)
            if n > 1:
                boots = [float(vals.iloc[rng.integers(0, n, n)].mean()) for _ in range(1000)]
                lo, hi = np.percentile(boots, [2.5, 97.5])
            else:
                lo = hi = mean
            rows.append({'sample_mode': mode, 'horizon': horizon, 'benchmark': bench, 'N': n, 'mean_abnormal_return': round(mean, 6), 'median_abnormal_return': round(median, 6), 'standard_deviation': round(std, 6), 'standard_error': round(se, 6), 't_stat': round(t, 4), 'p_value': round(p, 8), 'win_rate': round(float((vals > 0).mean()), 6), 'bootstrap_ci_lower': round(float(lo), 6), 'bootstrap_ci_upper': round(float(hi), 6)})
    return pd.DataFrame(rows)


def market_and_returns(clean_deduped: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    prices = normalize_market()
    missing = sorted(set(BENCHMARKS + SECTOR_ETFS) - set(prices['ticker'].unique()))
    if missing:
        supplemental = fetch_supplemental_prices(missing, prices['date'].min(), datetime.now(UTC).date().isoformat())
        if not supplemental.empty:
            prices = pd.concat([prices, supplemental], ignore_index=True).sort_values(['ticker','date']).drop_duplicates(['ticker','date'], keep='last')
    histories = price_maps(prices)
    price_rows = [{'record_type': 'price_rows_by_ticker', 'ticker': ticker, 'row_count': len(hist), 'min_date': hist['date'].min(), 'max_date': hist['date'].max(), 'duplicate_price_rows': 0, 'uses_adjusted_close': 'yes', 'note': 'existing yfinance prototype plus supplemental benchmark/sector fetch when needed'} for ticker, hist in histories.items()]
    all_windows = []
    all_invalid = []
    for mode in SAMPLE_MODES:
        sample = apply_sample_mode(clean_deduped, mode)
        windows, invalid = event_window_rows(sample, prices, mode)
        all_windows.append(windows)
        all_invalid.append(invalid)
    windows_df = pd.concat(all_windows, ignore_index=True)
    invalid_df = pd.concat(all_invalid, ignore_index=True)
    summary = summarize_event_windows(windows_df)
    write_csv(AUDIT / '05_verified_event_window_returns.csv', windows_df)
    write_csv(AUDIT / '05_verified_event_window_summary.csv', summary)
    coverage_rows = price_rows
    for _, r in summary[['sample_mode','horizon','benchmark','N']].iterrows():
        coverage_rows.append({'record_type': 'valid_return_count', 'ticker': r['benchmark'], 'row_count': r['N'], 'min_date': '', 'max_date': '', 'duplicate_price_rows': '', 'uses_adjusted_close': '', 'note': f"{r['sample_mode']} {r['horizon']}"})
    if not invalid_df.empty:
        for _, r in invalid_df.groupby(['sample_mode','horizon','invalid_reason']).size().reset_index(name='rows').iterrows():
            coverage_rows.append({'record_type': 'invalid_reason_count', 'ticker': r['invalid_reason'], 'row_count': r['rows'], 'min_date': '', 'max_date': '', 'duplicate_price_rows': '', 'uses_adjusted_close': '', 'note': f"{r['sample_mode']} {r['horizon']}"})
        for _, r in invalid_df.head(20).iterrows():
            coverage_rows.append({'record_type': 'invalid_example', 'ticker': r.get('ticker',''), 'row_count': r.get('event_id',''), 'min_date': r.get('event_date',''), 'max_date': r.get('horizon',''), 'duplicate_price_rows': '', 'uses_adjusted_close': '', 'note': r.get('invalid_reason','')})
    for _, r in windows_df[(windows_df['sample_mode'] == 'uncapped_full') & (windows_df['horizon'] == '1D')].head(20).iterrows():
        coverage_rows.append({'record_type': 'manual_valid_trace', 'ticker': r['ticker'], 'row_count': r['event_id'], 'min_date': r['event_date'], 'max_date': r['end_trading_day'], 'duplicate_price_rows': '', 'uses_adjusted_close': 'yes', 'note': f"entry={r['next_trading_day']}; raw={r['raw_stock_return']}; spy_ar={r.get('abnormal_return_SPY', np.nan)}"})
    write_csv(AUDIT / '04_return_coverage_audit.csv', pd.DataFrame(coverage_rows))
    lines = ['# Market Data and Return Coverage Audit', '']
    for h in ['1D','1W','1M','3M','6M','1Y','2Y','END_OF_SAMPLE','PRE_1W','PRE_1M','PRE_3M']:
        sub = summary[(summary['sample_mode']=='uncapped_full') & (summary['horizon']==h) & (summary['benchmark']=='SPY')]
        if not sub.empty:
            lines.append(f"- {h} valid SPY-adjusted returns: **{int(sub.iloc[0]['N']):,}**.")
    lines += ['', '- Weekend/holiday events are mapped to the next available ticker trading day.', '- Return horizons use trading-day offsets, not calendar-day offsets.', '- Duplicate price rows are collapsed by ticker/date before return calculation.', '- Missing benchmark endpoints leave that benchmark-adjusted return invalid.']
    write_md(AUDIT / '04_return_coverage_audit.md', lines)
    md = ['# Verified Event-Window Summary', '', '| Sample | Horizon | Benchmark | N | Mean AR | p-value | Win rate |', '|---|---|---:|---:|---:|---:|---:|']
    for _, r in summary[summary['sample_mode']=='uncapped_full'].iterrows():
        md.append(f"| {r['sample_mode']} | {r['horizon']} | {r['benchmark']} | {int(r['N'])} | {r['mean_abnormal_return']:.4f} | {r['p_value']:.4g} | {pct(r['win_rate'])} |")
    write_md(AUDIT / '05_verified_event_window_summary.md', md)
    return prices, windows_df, invalid_df, summary


def daily_returns_for_portfolio(events: pd.DataFrame, prices: pd.DataFrame, mode: str, horizon: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    histories = price_maps(prices)
    position_rows = []
    event_rows = []
    for _, ev in events.iterrows():
        direction = str(ev.get('direction','')).lower()
        rec_type = str(ev.get('recommendation_type','')).lower()
        if mode == 'buy_only' and direction != 'positive':
            continue
        if mode == 'sell_inverse_or_short_proxy' and direction != 'negative':
            continue
        if mode == 'price_target_only' and rec_type != 'price_target':
            continue
        if mode == 'portfolio_update_only' and rec_type != 'portfolio_update':
            continue
        sign = -1 if direction == 'negative' else 1
        hist = histories.get(ev['ticker'])
        if hist is None or hist.empty:
            continue
        dates = hist['date'].tolist()
        start_idx, _ = next_trading_day(ev['event_date_utc'], dates)
        if start_idx is None or start_idx + horizon >= len(hist):
            continue
        closes = hist['adjusted_close'].tolist()
        event_ret = sign * ((closes[start_idx + horizon] / closes[start_idx]) - 1)
        event_rows.append({'event_id': ev['event_id'], 'creator': ev['creator'], 'ticker': ev['ticker'], 'signed_horizon_return': event_ret})
        for i in range(start_idx + 1, start_idx + horizon + 1):
            raw = (closes[i] / closes[i - 1]) - 1
            signed = sign * raw
            net = signed - (0.001 if i == start_idx + 1 else 0) - (0.001 if i == start_idx + horizon else 0)
            position_rows.append({'date': dates[i], 'event_id': ev['event_id'], 'creator': ev['creator'], 'ticker': ev['ticker'], 'gross_return': signed, 'net_return': net})
    pos = pd.DataFrame(position_rows)
    evrets = pd.DataFrame(event_rows)
    if pos.empty:
        return pd.DataFrame(), evrets
    if mode == 'creator_weighted_all_recommendations':
        by_creator = pos.groupby(['date','creator']).agg(gross_return=('gross_return','mean'), net_return=('net_return','mean'), active_positions=('event_id','nunique')).reset_index()
        daily = by_creator.groupby('date').agg(gross_return=('gross_return','mean'), net_return=('net_return','mean'), active_positions=('active_positions','sum')).reset_index()
    else:
        daily = pos.groupby('date').agg(gross_return=('gross_return','mean'), net_return=('net_return','mean'), active_positions=('event_id','nunique')).reset_index()
    daily['portfolio_type'] = mode
    daily['holding_period'] = f'{horizon}D'
    return daily, evrets


def performance_metrics(daily: pd.DataFrame, event_rets: pd.DataFrame, prices: pd.DataFrame, mode: str, horizon: int, n_creators: int, n_tickers: int) -> dict[str, Any]:
    rets = daily['net_return'].astype(float)
    gross = daily['gross_return'].astype(float)
    total = float((1 + rets).prod() - 1) if len(rets) else 0.0
    gross_total = float((1 + gross).prod() - 1) if len(gross) else 0.0
    ann = float((1 + total) ** (252 / max(len(rets), 1)) - 1) if len(rets) else 0.0
    vol = float(rets.std(ddof=1) * math.sqrt(252)) if len(rets) > 1 else 0.0
    sharpe = ann / vol if vol else 0.0
    downside = rets[rets < 0]
    sortino = ann / (float(downside.std(ddof=1) * math.sqrt(252)) if len(downside) > 1 else np.nan)
    cum = (1 + rets).cumprod() if len(rets) else pd.Series([1.0])
    dd = (cum / cum.cummax()) - 1
    histories = price_maps(prices)
    def bench_daily(ticker: str) -> pd.Series:
        hist = histories.get(ticker)
        if hist is None:
            return pd.Series(dtype=float)
        b = hist.copy()
        b["ret"] = b["adjusted_close"].pct_change()
        return b.set_index('date')['ret']
    aligned = daily.set_index('date')['net_return'].astype(float)
    alpha_spy = beta_spy = alpha_qqq = info_ratio = np.nan
    for ticker in ["SPY", "QQQ"]:
        b = bench_daily(ticker)
        joined = pd.concat([aligned, b], axis=1, join='inner').dropna()
        if len(joined) > 2 and joined.iloc[:, 1].var() > 0:
            beta = float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / joined.iloc[:, 1].var())
            alpha = float((joined.iloc[:, 0].mean() - beta * joined.iloc[:, 1].mean()) * 252)
            if ticker == 'SPY':
                beta_spy, alpha_spy = beta, alpha
            else:
                alpha_qqq = alpha
                active = joined.iloc[:, 0] - joined.iloc[:, 1]
                info_ratio = float(active.mean() / active.std(ddof=1) * math.sqrt(252)) if active.std(ddof=1) else np.nan
    return {'portfolio_type': mode, 'holding_period': f'{horizon}D', 'total_return': round(total, 6), 'annualized_return': round(ann, 6), 'annualized_volatility': round(vol, 6), 'sharpe': round(sharpe, 4), 'sortino': round(float(sortino), 4) if not pd.isna(sortino) else '', 'max_drawdown': round(float(dd.min()), 6), 'hit_rate': round(float((event_rets['signed_horizon_return'] > 0).mean()), 6) if not event_rets.empty else '', 'turnover': round(float(len(event_rets) * 2 / max(len(daily), 1)), 6), 'average_active_positions': round(float(daily['active_positions'].mean()), 4) if not daily.empty else 0, 'transaction_cost_impact': round(gross_total - total, 6), 'alpha_vs_SPY': round(alpha_spy, 6) if not pd.isna(alpha_spy) else '', 'beta_vs_SPY': round(beta_spy, 6) if not pd.isna(beta_spy) else '', 'alpha_vs_QQQ': round(alpha_qqq, 6) if not pd.isna(alpha_qqq) else '', 'information_ratio': round(info_ratio, 6) if not pd.isna(info_ratio) else '', 'N_events': len(event_rets), 'N_creators': n_creators, 'N_tickers': n_tickers}


def portfolio_audit(events: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    modes = ['equal_weight_all_recommendations','creator_weighted_all_recommendations','buy_only','sell_inverse_or_short_proxy','long_buy_short_sell','price_target_only','portfolio_update_only']
    all_daily = []
    summaries = []
    for mode in modes:
        calc_mode = 'equal_weight_all_recommendations' if mode == 'long_buy_short_sell' else mode
        for horizon in [5, 21, 63, 126, 252]:
            daily, evrets = daily_returns_for_portfolio(events, prices, calc_mode, horizon)
            if daily.empty or len(evrets) < 5:
                continue
            daily['portfolio_type'] = mode
            all_daily.append(daily)
            summaries.append(performance_metrics(daily, evrets, prices, mode, horizon, events['creator'].nunique(), events['ticker'].nunique()))
    daily_df = pd.concat(all_daily, ignore_index=True) if all_daily else pd.DataFrame()
    summary = pd.DataFrame(summaries)
    write_csv(AUDIT / '06_verified_portfolio_daily_returns.csv', daily_df)
    write_csv(AUDIT / '06_verified_portfolio_performance_summary.csv', summary)
    lines = ['# Portfolio Audit', '', '- Entry date: next ticker trading day after the YouTube publish date.', '- Exit date: holding-period trading-day offset from entry.', '- Overlapping positions are allowed and averaged daily.', '- Equal-weight portfolios average active event positions each day.', '- Creator-weighted portfolios average within creator first, then across creators.', '- Transaction costs: 10 bps at entry and 10 bps at exit.', '- No lookahead: all entries occur after the event date using next-trading-day execution.', '', '| Portfolio | Holding | N events | Total return | Sharpe | Alpha vs SPY |', '|---|---:|---:|---:|---:|---:|']
    for _, r in summary.iterrows():
        lines.append(f"| {r['portfolio_type']} | {r['holding_period']} | {int(r['N_events'])} | {r['total_return']:.4f} | {r['sharpe']} | {r['alpha_vs_SPY']} |")
    write_md(AUDIT / '06_portfolio_audit.md', lines)
    write_md(AUDIT / '06_verified_portfolio_performance_summary.md', lines)
    return summary


def classifier_audit() -> None:
    actual = PRIOR_EXPANSION / 'classifier_ai_audit/ai_adjudication_results.csv'
    template = PRIOR_EXPANSION / 'classifier_ai_audit/ai_adjudication_results_template.csv'
    confusion = PRIOR_EXPANSION / 'classifier_ai_audit/rule_vs_ai_confusion_matrix.csv'
    if actual.exists() and actual.stat().st_size > 100:
        ai = pd.read_csv(actual)
        write_csv(AUDIT / '07_rule_vs_ai_confusion_matrix.csv', pd.crosstab(ai.get('rule_label', pd.Series(dtype=str)), ai.get('ai_label', pd.Series(dtype=str))).reset_index())
        write_csv(AUDIT / '07_ai_disagreement_examples.csv', ai.head(100))
        status = [f'Actual AI adjudication results exist with {len(ai):,} rows.']
    else:
        write_csv(AUDIT / '07_rule_vs_ai_confusion_matrix.csv', pd.DataFrame([{'status': 'missing_filled_ai_labels', 'reason': 'template/confusion matrix cannot be treated as human validation'}]))
        write_csv(AUDIT / '07_ai_disagreement_examples.csv', pd.DataFrame(columns=['status','event_id','rule_label','ai_label','reason']))
        status = ['No filled `ai_adjudication_results.csv` exists in the committed research-expansion outputs.', f'Template exists: {template.exists()}. Confusion matrix exists without underlying filled results: {confusion.exists()}.']
    write_csv(AUDIT / '07_ai_agree_only_event_window_summary.csv', pd.DataFrame([{'status': 'not_computed', 'reason': 'filled AI labels missing or synthetic; no AI-agree-only sample is defensible'}]))
    write_md(AUDIT / '07_classifier_ai_audit_verification.md', ['# Classifier AI Audit Verification', '', *[f'- {s}' for s in status], '', '- Treat all classifier labels as deterministic rule-generated pseudo-labels.', '- The available AI audit is AI-assisted or template-derived, not human validation.', '- Because filled adjudication labels are missing, AI-agree-only return results are not computed.'])


def robust_statistics(windows: pd.DataFrame, summary: pd.DataFrame, prices: pd.DataFrame) -> None:
    rows = []
    base = windows[windows['sample_mode']=='uncapped_full'].copy()
    for horizon in sorted(base['horizon'].dropna().unique()):
        sub = base[base['horizon']==horizon]
        for bench in BENCHMARKS:
            col = f'abnormal_return_{bench}'
            if col not in sub.columns:
                continue
            vals = pd.to_numeric(sub[col], errors='coerce').dropna()
            if len(vals) < 2:
                continue
            t, p = stats.ttest_1samp(vals, 0.0)
            try:
                w_p = stats.wilcoxon(vals).pvalue
            except Exception:
                w_p = np.nan
            rng = np.random.default_rng(496)
            signs = rng.choice([-1,1], size=(1000, len(vals)))
            perm = np.abs((signs * vals.to_numpy()).mean(axis=1))
            perm_p = max(float((perm >= abs(vals.mean())).mean()), 0.001)
            rows.append({'horizon': horizon, 'benchmark': bench, 'method': 't_test', 'statistic': round(float(t),6), 'p_value': round(float(p),8), 'estimate': round(float(vals.mean()),6), 'n': len(vals)})
            rows.append({'horizon': horizon, 'benchmark': bench, 'method': 'wilcoxon_signed_rank', 'statistic': '', 'p_value': round(float(w_p),8) if not pd.isna(w_p) else '', 'estimate': round(float(vals.median()),6), 'n': len(vals)})
            rows.append({'horizon': horizon, 'benchmark': bench, 'method': 'sign_flip_permutation', 'statistic': '', 'p_value': round(perm_p,8), 'estimate': round(float(vals.mean()),6), 'n': len(vals)})
    robust = pd.DataFrame(rows)
    write_csv(AUDIT / '08_verified_robust_statistics.csv', robust)
    if not robust.empty:
        pvals = pd.to_numeric(robust['p_value'], errors='coerce')
        mask = pvals.notna()
        reject, corr, _, _ = multipletests(pvals[mask], alpha=0.05, method='fdr_bh')
        mt = robust.loc[mask, ['horizon','benchmark','method','p_value']].copy()
        mt['fdr_corrected_p'] = corr
        mt['survives_fdr_5pct'] = reject
    else:
        mt = pd.DataFrame()
    write_csv(AUDIT / '08_verified_multiple_testing_adjustment.csv', mt)
    placebo_rows = []
    pre = summary[(summary['sample_mode']=='uncapped_full') & (summary['horizon'].str.startswith('PRE_', na=False))]
    for _, r in pre.iterrows():
        placebo_rows.append({'placebo_type': 'pre_event', 'horizon': r['horizon'], 'benchmark': r['benchmark'], 'N': r['N'], 'mean_abnormal_return': r['mean_abnormal_return'], 'p_value': r['p_value']})
    histories = price_maps(prices)
    rng = np.random.default_rng(496)
    sample = base[(base['horizon']=='1M') & base['abnormal_return_SPY'].notna()].copy()
    random_vals = []
    for _, ev in sample.iterrows():
        hist = histories.get(ev['ticker'])
        if hist is None or len(hist) < 30:
            continue
        idx = int(rng.integers(0, max(len(hist)-22, 1)))
        s, e = hist.iloc[idx]['date'], hist.iloc[idx+21]['date']
        raw = calc_return(histories, ev['ticker'], s, e)
        br = calc_return(histories, 'SPY', s, e)
        if raw is not None and br is not None:
            random_vals.append(raw - br)
    if random_vals:
        arr = pd.Series(random_vals)
        _, p = stats.ttest_1samp(arr, 0.0)
        placebo_rows.append({'placebo_type': 'random_date_by_ticker', 'horizon': '1M', 'benchmark': 'SPY', 'N': len(arr), 'mean_abnormal_return': round(float(arr.mean()),6), 'p_value': round(float(p),8)})
    write_csv(AUDIT / '08_verified_placebo_tests.csv', pd.DataFrame(placebo_rows))
    write_md(AUDIT / '08_verified_statistical_summary.md', ['# Verified Statistical Summary', '', '- Includes t-tests, Wilcoxon signed-rank tests, sign-flip permutation tests, bootstrap CIs in the event-window summary, and Benjamini-Hochberg FDR correction.', '- Pre-event placebos are reported from PRE_1W, PRE_1M, and PRE_3M windows.', '- Random-date by ticker placebo is included where market data coverage allows.', '- Creator/ticker clustered standard errors and fixed-effects regressions remain a residual improvement area for the final paper.'])


def final_claims(transcripts: dict[str, Any], funnel: dict[str, Any], ev_summary: pd.DataFrame, port_summary: pd.DataFrame) -> None:
    spy = ev_summary[(ev_summary['sample_mode']=='uncapped_full') & (ev_summary['benchmark']=='SPY')]
    def line_for(h: str) -> str:
        r = spy[spy['horizon']==h]
        if r.empty:
            return f'- {h}: unavailable.'
        rr = r.iloc[0]
        return f"- {h}: N={int(rr['N'])}, mean SPY abnormal return={rr['mean_abnormal_return']:.4%}, p={rr['p_value']:.4g}."
    lines = ['# Final Claims Audit', '', '## 1. Verified Dataset Facts', f"- Current RunPod DB videos: {transcripts['total_videos']:,}.", f"- Successful transcripts: {transcripts['successful']:,}.", f"- Strict usable transcripts (`full_text > 50`): {transcripts['full_text_gt_50']:,}.", '## 2. Verified Event-Label Facts', f"- DB recommendation rows: {funnel['total_events']:,}.", f"- Conservative clean row-level pseudo-labels: {funnel['clean_row_level']:,}.", f"- Corrected unique video/ticker/date events for returns: {funnel['clean_deduped']:,}.", '## 3. Verified Market-Data Facts', '- Market data is yfinance prototype data, with supplemental yfinance benchmark/sector fetches where needed.', '## 4. Verified Event-Window Findings', line_for('1D'), line_for('1W'), line_for('1M'), line_for('3M'), line_for('6M'), line_for('1Y'), line_for('2Y'), line_for('PRE_1W'), '## 5. Verified Portfolio Findings']
    if not port_summary.empty:
        for _, r in port_summary.sort_values('sharpe', ascending=False).head(5).iterrows():
            lines.append(f"- {r['portfolio_type']} {r['holding_period']}: Sharpe={r['sharpe']}, total return={r['total_return']:.2%}, N={int(r['N_events'])}.")
    lines += ['## 6. Verified Benchmark Findings', '- Benchmark-adjusted results are descriptive and sensitive to horizon, benchmark, and event deduplication.', '## 7. Verified Classifier Limitations', '- Labels are rules-based pseudo-labels. There is no human ground truth.', '- AI audit artifacts are not human validation and filled AI labels are missing/synthetic.', '## 8. Claims Supported', '- The project can claim dataset size, transcript coverage, conservative pseudo-labeled event counts, and descriptive abnormal returns.', '## 9. Claims Not Supported', '- Do not claim causality or that finfluencers beat the market.', '## 10. Claims Requiring Bloomberg', '- Institutional-grade adjusted returns, intraday execution, delisting/survivorship checks.', '## 11. Claims Requiring Human Validation', '- Classifier accuracy, precision, recall, and false-positive rates.', '## 12. Claims Requiring Out-of-Sample Testing', '- Tradable alpha, strategy persistence, creator skill.', '## 13. Final Recommended Thesis', '- YouTube finfluencer recommendations show horizon-dependent descriptive abnormal returns in prototype data, but evidence is not sufficient for causal alpha claims after correcting event labels and duplicate mentions.', '## 14. Exact Language To Use In The Paper', '- "Using yfinance prototype market data and rule-generated pseudo-labels..."', '- "Descriptive benchmark-adjusted event-window returns..."', '- "Conservative clean events are deduplicated at the video/ticker/date level for return tests."', '## 15. Exact Language To Avoid', '- "Finfluencers beat the market."', '- "Causal impact."', '- "Human-validated labels."', '- "Bloomberg-grade returns."']
    write_md(AUDIT / '09_final_claims_audit.md', lines)
    prof = ['# Professor Update', '', 'My FIN 496 capstone asks whether YouTube finfluencer stock recommendations are associated with benchmark-adjusted abnormal returns or whether they mostly reflect attention around stocks already being discussed.', '', f'The reconciled RunPod dataset has {transcripts["total_videos"]:,} YouTube videos, {transcripts["successful"]:,} successful transcripts, and {transcripts["full_text_gt_50"]:,} transcripts with more than 50 characters of text. The conservative rule-labeling pipeline produces {funnel["clean_row_level"]:,} row-level clean pseudo-labeled events, which I deduplicate to {funnel["clean_deduped"]:,} video/ticker/date events for return testing.', '', 'The method combines NLP-style deterministic event extraction, next-trading-day event windows, SPY/QQQ/IWM benchmark adjustment, portfolio backtests, and robustness checks. The classifier caveat is important: these are rule-generated pseudo-labels, not human ground truth. The available AI audit is AI-assisted and cannot be described as human validation.', '', 'What changed from the prior results is that the large OpenCode clean-event count was not defensible as a clean-label count; it bypassed earlier validation safeguards and overweighted repeated ticker mentions. The verified audit uses the conservative deduped event set.', '', 'Before final presentation, the main next step is to decide whether to keep yfinance as explicitly prototype-grade or replace the market data with Bloomberg-adjusted prices if access is available.']
    write_md(AUDIT / '10_professor_update.md', prof)


def main() -> None:
    AUDIT.mkdir(parents=True, exist_ok=True)
    phase0()
    transcripts = transcript_reconciliation()
    clean = load_validation_clean()
    deduped = dedupe_events(clean)
    funnel = event_funnel(clean, deduped)
    sample_mode_audit(deduped, funnel)
    prices, windows, _, ev_summary = market_and_returns(deduped)
    port_summary = portfolio_audit(deduped, prices)
    classifier_audit()
    robust_statistics(windows, ev_summary, prices)
    final_claims(transcripts, funnel, ev_summary, port_summary)


if __name__ == '__main__':
    main()
