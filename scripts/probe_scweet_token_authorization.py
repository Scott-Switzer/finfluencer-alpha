#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)

OUT_DIR = ROOT / 'data/exports/overnight_collection'
OUT_MD = OUT_DIR / '40_scweet_token_authorization_probe.md'
OUT_CSV = OUT_DIR / '40_scweet_token_authorization_probe.csv'


def load_env_map() -> dict[str, str]:
    p = ROOT / '.env'
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for raw in p.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k.strip()] = v.strip()
    return out


def parse_error(resp: requests.Response) -> tuple[str, str]:
    try:
        body = resp.json()
    except Exception:
        return '', f'non_json_http_{resp.status_code}'
    err = body.get('error') if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return '', f'http_{resp.status_code}'
    et = str(err.get('type') or '').strip()
    msg = str(err.get('message') or '').strip()
    return et, msg[:220]


def decision_for(status: int, error_type: str, actor_started: bool) -> str:
    if actor_started:
        return 'SELECTED_FIRST_ELIGIBLE'
    low = (error_type or '').lower()
    if low == 'full-permission-actor-not-approved':
        return 'AUTH_BLOCKED_APPROVAL_REQUIRED'
    if status in (401,):
        return 'AUTH_INVALID_TOKEN'
    if status == 402 or 'credit' in low or 'payment' in low or 'billing' in low:
        return 'AUTH_BLOCKED_CREDIT_OR_BILLING'
    if status == 403:
        return 'AUTH_FORBIDDEN'
    if status <= 0:
        return 'REQUEST_FAILURE'
    return 'START_FAILED'


def main() -> None:
    actor = os.getenv('SCWEET_AUTH_PROBE_ACTOR', 'altimis/scweet').strip() or 'altimis/scweet'
    actor_path = actor.replace('/', '~')
    max_items = int(os.getenv('SCWEET_AUTH_PROBE_MAX_ITEMS', '1') or 1)
    env_map = load_env_map()
    token_count = int(env_map.get('APIFY_TOKEN_COUNT', '0') or 0)
    if token_count <= 0:
        raise SystemExit('APIFY_TOKEN_COUNT missing/invalid')

    payload = {
        'source_mode': 'search',
        'search_query': 'from:MeetKevin $TSLA lang:en',
        'since': '2021-01-01',
        'until': '2021-01-08',
        'max_items': max_items,
    }

    started_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    rows: list[dict[str, Any]] = []
    selected_slot = ''
    selected_run_id = ''

    for i in range(1, token_count + 1):
        slot = f'APIFY_TOKEN_{i}'
        token = env_map.get(slot, '').strip()
        row: dict[str, Any] = {
            'token_slot': slot,
            'attempted': '1',
            'actor_started': '0',
            'http_status': '',
            'error_type': '',
            'error_summary': '',
            'decision': '',
            'selected_for_canary': '0',
            'run_id': '',
        }
        if not token:
            row['attempted'] = '0'
            row['decision'] = 'TOKEN_MISSING'
            rows.append(row)
            continue

        status = 0
        error_type = ''
        error_summary = ''
        actor_started = False
        run_id = ''

        try:
            resp = requests.post(
                f'https://api.apify.com/v2/acts/{actor_path}/runs',
                headers={'Authorization': f'Bearer {token}'},
                json=payload,
                timeout=40,
            )
            status = int(resp.status_code)
            if 200 <= status < 300:
                actor_started = True
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                data = body.get('data') if isinstance(body, dict) else None
                if isinstance(data, dict):
                    run_id = str(data.get('id') or '')
            else:
                error_type, error_summary = parse_error(resp)
        except requests.RequestException as exc:
            status = 0
            error_summary = str(exc)[:220]

        row['actor_started'] = '1' if actor_started else '0'
        row['http_status'] = str(status) if status else ''
        row['error_type'] = error_type
        row['error_summary'] = error_summary
        row['run_id'] = run_id
        row['decision'] = decision_for(status, error_type, actor_started)

        if actor_started:
            row['selected_for_canary'] = '1'
            selected_slot = slot
            selected_run_id = run_id
            rows.append(row)
            break

        rows.append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        'token_slot',
        'attempted',
        'actor_started',
        'http_status',
        'error_type',
        'error_summary',
        'decision',
        'selected_for_canary',
    ]
    with OUT_CSV.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, '') for k in fields})

    lines = [
        '# Scweet token authorization probe',
        '',
        f'Started (UTC): `{started_at}`',
        f'Actor: `{actor}`',
        f'Token slots configured: `{token_count}`',
        '',
        '## Probe payload shape',
        '',
        '```json',
        json.dumps(payload, indent=2),
        '```',
        '',
        '## Results (no secrets)',
        '',
    ]
    for row in rows:
        lines.append(
            f"- `{row['token_slot']}` attempted={row['attempted']} "
            f"started={row['actor_started']} http={row['http_status'] or 'n/a'} "
            f"error_type=`{row['error_type'] or 'n/a'}` decision=`{row['decision']}`"
        )
    lines.extend(
        [
            '',
            f"Selected slot: `{selected_slot or 'none'}`",
            f"Selected run id: `{selected_run_id or 'none'}`",
            '',
        ]
    )
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')

    print(f'WROTE_MD={OUT_MD.relative_to(ROOT)}')
    print(f'WROTE_CSV={OUT_CSV.relative_to(ROOT)}')
    print(f'SELECTED_SLOT={selected_slot or "none"}')


if __name__ == '__main__':
    main()
