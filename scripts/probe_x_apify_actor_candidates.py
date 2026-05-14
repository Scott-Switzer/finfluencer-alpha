#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)
OUT_DIR = ROOT / 'data/exports/overnight_collection'
IN_CSV = OUT_DIR / '41_x_apify_actor_discovery.csv'
OUT_MD = OUT_DIR / '42_x_apify_actor_candidate_probe.md'
OUT_CSV = OUT_DIR / '42_x_apify_actor_candidate_probe.csv'


def token_1() -> str:
    t = os.getenv('APIFY_TOKEN_1', '').strip() or os.getenv('APIFY_TOKEN', '').strip()
    if not t:
        raise SystemExit('missing APIFY token for probe')
    return t


def actor_path(aid: str) -> str:
    return aid.replace('/', '~')


def _created_raw(item: dict[str, Any]) -> Any:
    keys = ['created_at','createdAt','timestamp','date','time','tweet.created_at']
    for k in keys:
        cur: Any = item
        ok = True
        for part in k.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None,''):
            return cur
    return None


def _id_raw(item: dict[str, Any]) -> Any:
    keys = ['id','tweet_id','tweetId','rest_id','tweet.id']
    for k in keys:
        cur: Any = item
        ok = True
        for part in k.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None,''):
            return cur
    return None


def _text_raw(item: dict[str, Any]) -> str:
    keys = ['text','full_text','content','tweetText','tweet.text','body']
    for k in keys:
        cur: Any = item
        ok = True
        for part in k.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None,''):
            return str(cur)
    return ''


def parse_ts(raw: Any) -> tuple[bool, int | None]:
    import datetime as dt
    if raw in (None, ''):
        return False, None
    s = str(raw).strip()
    if not s:
        return False, None
    try:
        if s.isdigit() and len(s) >= 10:
            val = int(s)
            if len(s) >= 13:
                val //= 1000
            return True, val
        ts = int(dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp())
        return True, ts
    except Exception:
        return False, None


def build_input() -> tuple[dict[str, Any], str]:
    # conservative structured shape, valid for many advanced search actors
    payload = {
        'searchQuery': 'from:MeetKevin $TSLA since:2021-01-01 until:2021-01-08 lang:en',
        'searchTerms': ['from:MeetKevin $TSLA since:2021-01-01 until:2021-01-08 lang:en'],
        'query': 'from:MeetKevin $TSLA since:2021-01-01 until:2021-01-08 lang:en',
        'since': '2021-01-01',
        'until': '2021-01-08',
        'startDate': '2021-01-01',
        'endDate': '2021-01-08',
        'timeSince': '2021-01-01',
        'timeUntil': '2021-01-08',
        'timeSinceUnix': 1609459200,
        'timeUntilUnix': 1610064000,
        'maxItems': 1,
        'max_items': 1,
        'limit': 1,
        'maxTweets': 1,
        'numberOfTweets': 1,
        'lang': 'en',
        'language': 'en',
    }
    return payload, 'generic_historical_creator_query_shape'


def main() -> None:
    max_actors = int(os.getenv('X_ACTOR_PROBE_MAX_ACTORS', '5') or 5)
    cap = float(os.getenv('X_ACTOR_PROBE_SESSION_CAP_USD', '0.10') or 0.10)
    tok = token_1()
    if not IN_CSV.exists():
        raise SystemExit(f'missing discovery csv: {IN_CSV}')

    rows = list(csv.DictReader(IN_CSV.read_text(encoding='utf-8').splitlines()))
    ranked = [
        r for r in rows
        if r.get('decision') in {'LIMITED_PERMISSION_CANDIDATE','UNKNOWN_PERMISSION_AUTH_PROBE'}
        and (r.get('actorPermissionLevel') or '').upper() != 'FULL_PERMISSIONS'
    ]

    preferred = [
        'api-ninja/x-twitter-advanced-search',
        'happitap/twitter-tweet-scraper',
        'web.harvester/easy-twitter-search-scraper',
        'mikolabs/twitter-advanced-search-scraper',
        'mikolabs/x-twitter-advanced-search-tweet-scraper',
        'novi/twitter-x-api',
        'khadinakbar/x-tweet-scraper',
        'epctex/twitter-scraper',
        'dovepppp/search-tweet-scraper',
        'seemuapps/x-tweet-scraper',
    ]
    pos = {aid: i for i, aid in enumerate(preferred)}

    def score(r: dict[str, str]) -> tuple:
        aid = r.get('actor_id','')
        perm = (r.get('actorPermissionLevel') or '').upper()
        p = 0 if perm == 'LIMITED_PERMISSIONS' else 1
        s = 0 if r.get('supports_advanced_search_syntax') == 'true' or r.get('supports_search_query') == 'true' else 1
        d = 0 if r.get('supports_since_until_dates') == 'true' or r.get('supports_unix_time_filters') == 'true' else 1
        f = 0 if r.get('supports_profile_or_from_user') == 'true' else 1
        m = 0 if r.get('supports_max_items') == 'true' else 1
        pref = pos.get(aid, 999)
        return (p, pref, s, d, f, m, aid)

    ranked.sort(key=score)
    ranked = ranked[:max_actors]

    spend_used = 0.0
    out_rows: list[dict[str, Any]] = []
    selected_actor = ''
    started_utc = datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

    for i, cand in enumerate(ranked, start=1):
        aid = cand.get('actor_id','')
        perm = cand.get('actorPermissionLevel','')
        payload, shape = build_input()
        row: dict[str, Any] = {
            'provider_key': f'candidate_{i}',
            'actor_id': aid,
            'actorPermissionLevel': perm,
            'attempted_input_shape': shape,
            'started': '0',
            'run_status': '',
            'http_status': '',
            'error_type': '',
            'returned_rows': '0',
            'has_text_field': 'false',
            'has_created_at_field': 'false',
            'has_id_field': 'false',
            'created_at_parseable': 'false',
            'explicit_cashtag_detected': 'false',
            'inside_window_detected': 'false',
            'same_day_collapse_suspected': 'false',
            'mock_like_row_detected': 'false',
            'selected_for_strict_canary': '0',
            'decision': '',
            'reason': '',
        }

        if spend_used >= cap:
            row['decision'] = 'SKIPPED_CAP_REACHED'
            row['reason'] = 'probe session cap reached'
            out_rows.append(row)
            continue

        url = f"https://api.apify.com/v2/acts/{actor_path(aid)}/runs"
        resp = requests.post(url, headers={'Authorization': f'Bearer {tok}'}, json=payload, timeout=45)
        row['http_status'] = str(resp.status_code)

        if resp.status_code >= 400:
            try:
                body = resp.json()
                err = body.get('error') if isinstance(body, dict) else {}
                et = str((err or {}).get('type') or '')
                em = str((err or {}).get('message') or '')[:220]
            except Exception:
                et, em = '', resp.text[:220]
            row['error_type'] = et
            if et == 'full-permission-actor-not-approved':
                row['decision'] = 'AUTH_BLOCKED_APPROVAL_REQUIRED'
            elif resp.status_code in (401,403):
                row['decision'] = 'AUTH_OR_PERMISSION_BLOCKED'
            elif resp.status_code == 402:
                row['decision'] = 'BILLING_BLOCKED'
            else:
                row['decision'] = 'START_FAILED'
            row['reason'] = em
            out_rows.append(row)
            continue

        row['started'] = '1'
        try:
            run = resp.json().get('data', {})
        except Exception:
            run = {}
        run_id = str(run.get('id') or '')
        row['run_status'] = str(run.get('status') or '')

        # poll briefly
        final = run
        for _ in range(8):
            if not run_id:
                break
            st = requests.get(
                f'https://api.apify.com/v2/actor-runs/{run_id}',
                headers={'Authorization': f'Bearer {tok}'},
                timeout=30,
            )
            if st.status_code >= 400:
                break
            data = st.json().get('data', {})
            final = data if isinstance(data, dict) else final
            status = str(final.get('status') or '')
            if status in {'SUCCEEDED','FAILED','TIMED-OUT','ABORTED'}:
                break

        row['run_status'] = str(final.get('status') or row['run_status'])
        usage = final.get('usage') if isinstance(final, dict) else {}
        if isinstance(usage, dict):
            # conservative derived spend from totalUsd if present
            usd = usage.get('totalUsd')
            try:
                if usd is not None:
                    spend_used += float(usd)
            except Exception:
                pass

        dataset_id = str(final.get('defaultDatasetId') or '')
        items: list[dict[str, Any]] = []
        if dataset_id:
            dresp = requests.get(
                f'https://api.apify.com/v2/datasets/{dataset_id}/items',
                headers={'Authorization': f'Bearer {tok}'},
                params={'limit': 1, 'offset': 0, 'clean': '1'},
                timeout=30,
            )
            if dresp.status_code < 400:
                try:
                    data = dresp.json()
                    if isinstance(data, list):
                        items = [x for x in data if isinstance(x, dict)]
                except Exception:
                    pass

        row['returned_rows'] = str(len(items))
        if items:
            item = items[0]
            text = _text_raw(item)
            created_raw = _created_raw(item)
            id_raw = _id_raw(item)
            row['has_text_field'] = str(bool(text)).lower()
            row['has_created_at_field'] = str(created_raw not in (None, '')).lower()
            row['has_id_field'] = str(id_raw not in (None, '')).lower()
            ok_ts, ts = parse_ts(created_raw)
            row['created_at_parseable'] = str(ok_ts).lower()
            row['explicit_cashtag_detected'] = str('$TSLA' in (text or '')).lower()
            if ok_ts and ts is not None:
                row['inside_window_detected'] = str(1609459200 <= ts <= 1610064000).lower()
            if isinstance(text, str) and 'mock_tweet' in text.lower():
                row['mock_like_row_detected'] = 'true'
            # collapse suspicion if parseable and current day in historical query
            from datetime import datetime as dt
            if ok_ts and ts is not None:
                day = dt.fromtimestamp(ts, UTC).date().isoformat()
                row['same_day_collapse_suspected'] = str(day == datetime.now(UTC).date().isoformat()).lower()

        good = (
            row['started'] == '1'
            and row['returned_rows'] != '0'
            and row['has_text_field'] == 'true'
            and row['has_created_at_field'] == 'true'
            and row['has_id_field'] == 'true'
            and row['created_at_parseable'] == 'true'
            and row['explicit_cashtag_detected'] == 'true'
            and row['inside_window_detected'] == 'true'
            and row['same_day_collapse_suspected'] == 'false'
            and row['mock_like_row_detected'] == 'false'
        )
        if good and not selected_actor:
            row['selected_for_strict_canary'] = '1'
            row['decision'] = 'SELECT_FOR_STRICT_CANARY'
            row['reason'] = 'meets tiny probe quality checks'
            selected_actor = aid
        else:
            if row['started'] == '1' and row['returned_rows'] == '0':
                row['decision'] = 'STARTED_NO_ROWS'
                row['reason'] = 'authorization/schema ok but no rows from tiny probe'
            elif row['started'] == '1':
                row['decision'] = 'STARTED_QUALITY_NOT_PROVEN'
                row['reason'] = 'row shape/quality checks not sufficient for strict canary'
            else:
                row['decision'] = row['decision'] or 'START_FAILED'
                row['reason'] = row['reason'] or 'actor did not start'
        out_rows.append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        'provider_key','actor_id','actorPermissionLevel','attempted_input_shape','started','run_status','http_status','error_type',
        'returned_rows','has_text_field','has_created_at_field','has_id_field','created_at_parseable','explicit_cashtag_detected',
        'inside_window_detected','same_day_collapse_suspected','mock_like_row_detected','selected_for_strict_canary','decision','reason',
    ]
    with OUT_CSV.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, '') for k in fields})

    lines = [
        '# X Apify actor candidate tiny probe',
        '',
        f'Started (UTC): `{started_utc}`',
        f'Max actors: `{max_actors}`',
        f'Session cap USD: `{cap}`',
        '',
        f'Selected for strict canary: `{selected_actor or "none"}`',
        '',
        '## Probe rows',
        '',
    ]
    for r in out_rows:
        lines.append(
            f"- `{r['provider_key']}` `{r['actor_id']}` perm=`{r['actorPermissionLevel'] or 'unknown'}` "
            f"started={r['started']} returned={r['returned_rows']} decision=`{r['decision']}` reason=`{r['reason']}`"
        )
    OUT_MD.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

    print(f'WROTE_MD={OUT_MD.relative_to(ROOT)}')
    print(f'WROTE_CSV={OUT_CSV.relative_to(ROOT)}')
    print(f'SELECTED_ACTOR={selected_actor or "none"}')


if __name__ == '__main__':
    main()
