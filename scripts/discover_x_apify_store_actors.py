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
OUT_MD = OUT_DIR / '41_x_apify_actor_discovery.md'
OUT_CSV = OUT_DIR / '41_x_apify_actor_discovery.csv'

SEARCH_QUERIES = [
    'twitter search scraper',
    'x twitter scraper',
    'tweet scraper',
    'twitter advanced search',
    'x tweet search',
    'twitter profile scraper',
    'twitter historical search',
    'x advanced search',
    'tweet pay per result',
    'twitter since until',
    'x scraper since until',
]

SEED_ACTORS = [
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
    'twitterapi/twitter-search',
    'twittapi/twitter-search-scraper',
    'api402/x-twitter-scraper',
    'automation-lab/twitter-scraper',
    'gentle_cloud/twitter-tweets-scraper',
    'forge-api/x-scraper',
    'dev-sinior/twitter-scraper-unlimited',
    'igview-owner/twitter-x-search-scraper',
    'scrapier/Twitter-X-Tweets-Scraper',
    'xtdata/twitter-x-scraper',
    'xtdata/twitter-x-user-tweets-scraper',
]

FIELDNAMES = [
    'actor_id','username','name','title','actorPermissionLevel','isDeprecated','totalUsers','monthlyUsers','rating',
    'pricing_summary','modifiedAt','supports_search_query','supports_advanced_search_syntax',
    'supports_profile_or_from_user','supports_since_until_dates','supports_unix_time_filters','supports_max_items',
    'supports_language_filter','likely_historical','likely_cashtag_search','decision','reason',
]


def _env_token() -> str:
    for key in ('APIFY_TOKEN_1','APIFY_TOKEN'):
        val = os.getenv(key, '').strip()
        if val:
            return val
    return ''


def _get(url: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    resp = requests.get(url, headers=headers, params=params or {}, timeout=40)
    if resp.status_code >= 400:
        return {'error_http_status': resp.status_code, 'error_text': resp.text[:500]}
    try:
        return resp.json()
    except Exception:
        return {'error_http_status': resp.status_code, 'error_text': 'non_json'}


def as_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return x != 0
    t = str(x or '').strip().lower()
    if t in {'true','1','yes','y','on'}:
        return True
    if t in {'false','0','no','n','off',''}:
        return False
    return bool(x)


def _scan(text: str, patterns: list[str]) -> bool:
    t = (text or '').lower()
    return any(p in t for p in patterns)


def _first(*vals: Any) -> Any:
    for v in vals:
        if v not in (None, '', []):
            return v
    return ''


def _short_pricing(info: dict[str, Any]) -> str:
    for k in ('pricing','pricingModel','pricingInfo'):
        v = info.get(k)
        if isinstance(v, str) and v.strip():
            return v[:160]
        if isinstance(v, dict):
            model = v.get('model') or v.get('pricingModel') or ''
            desc = v.get('description') or ''
            out = ' '.join(x for x in [str(model).strip(), str(desc).strip()] if x)
            if out:
                return out[:160]
    # fallback from README cues
    txt = ' '.join(str(info.get(k) or '') for k in ('description','title','name'))
    if _scan(txt, ['pay per result','pay-per-result','consumption']):
        return 'pay-per-result/consumption (from metadata text)'
    return ''


def classify(actor: dict[str, Any]) -> tuple[str, str]:
    perm = str(actor.get('actorPermissionLevel') or '').upper()
    if as_bool(actor.get('isDeprecated')):
        return 'DEPRECATED_SKIP', 'actor marked deprecated'

    text_blob = ' '.join(
        str(actor.get(k) or '') for k in (
            'title','name','description','readme','input_schema_text','example_input_text'
        )
    ).lower()

    relevant = _scan(text_blob, ['twitter', 'x ', 'tweet', 'tweets', 'x.com', 'advanced search'])
    if not relevant:
        return 'NOT_RELEVANT_SKIP', 'metadata does not look like X/Twitter post scraping'

    if _scan(text_blob, ['email', 'newsletter', 'community replies only']):
        return 'UNSUITABLE_REPLY_OR_EMAIL_SKIP', 'not creator-authored search oriented'

    hist = actor.get('likely_historical')
    search = actor.get('supports_search_query') or actor.get('supports_advanced_search_syntax')
    if perm == 'FULL_PERMISSIONS':
        return 'FULL_PERMISSION_SKIP', 'requires manual full-permission approval'
    if perm == 'LIMITED_PERMISSIONS' and hist and search:
        return 'LIMITED_PERMISSION_CANDIDATE', 'limited permissions + historical/search support'
    if not perm and hist and search:
        return 'UNKNOWN_PERMISSION_AUTH_PROBE', 'permission missing but metadata looks promising'
    if perm == 'LIMITED_PERMISSIONS' and (hist or search):
        return 'LIMITED_PERMISSION_CANDIDATE', 'limited permissions; partially promising'
    return 'NOT_RELEVANT_SKIP', 'insufficient historical/search indicators'


def main() -> None:
    token = _env_token()
    discovered: dict[str, dict[str, Any]] = {}

    # Discover via Store search
    for q in SEARCH_QUERIES:
        payload = _get('https://api.apify.com/v2/store', token, params={'search': q, 'limit': 200})
        data = payload.get('data') if isinstance(payload, dict) else None
        items = []
        if isinstance(data, dict):
            items = data.get('items') or []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            aid = str(_first(it.get('actorId'), it.get('id'), it.get('name')) or '').strip()
            user = str(_first(it.get('username'), it.get('ownerUsername')) or '').strip()
            if not aid:
                continue
            if '/' not in aid and user:
                aid = f'{user}/{aid}'
            if '/' not in aid:
                continue
            discovered.setdefault(aid.lower(), {'actor_id': aid, 'store_item': it, 'search_hits': set()})
            discovered[aid.lower()]['search_hits'].add(q)

    # Ensure seed actors included
    for aid in SEED_ACTORS:
        discovered.setdefault(aid.lower(), {'actor_id': aid, 'store_item': {}, 'search_hits': set()})

    rows: list[dict[str, Any]] = []
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

    for key in sorted(discovered.keys()):
        aid = discovered[key]['actor_id']
        actor_path = aid.replace('/', '~')
        meta = _get(f'https://api.apify.com/v2/acts/{actor_path}', token)
        data = meta.get('data') if isinstance(meta, dict) else None
        actor = data if isinstance(data, dict) else {}
        if not actor and isinstance(discovered[key].get('store_item'), dict):
            actor = discovered[key]['store_item']

        username = str(_first(actor.get('username'), actor.get('ownerUsername'), aid.split('/')[0]))
        name = str(_first(actor.get('name'), aid.split('/')[-1]))
        title = str(_first(actor.get('title'), actor.get('description'), name))
        perm = str(actor.get('actorPermissionLevel') or '')
        deprecated = as_bool(actor.get('isDeprecated', False))
        total_users = _first(actor.get('totalUsers'), actor.get('stats', {}).get('totalUsers'))
        monthly_users = _first(actor.get('monthlyUsers'), actor.get('stats', {}).get('monthlyUsers'))
        rating = _first(actor.get('rating'), actor.get('stats', {}).get('rating'))
        modified = str(_first(actor.get('modifiedAt'), actor.get('createdAt')))
        pricing = _short_pricing(actor)

        schema = actor.get('inputSchema') if isinstance(actor.get('inputSchema'), dict) else {}
        props = schema.get('properties') if isinstance(schema.get('properties'), dict) else {}
        prop_keys = {k.lower() for k in props.keys()}

        readme = str(actor.get('readme') or '')
        desc = str(actor.get('description') or '')
        text = ' '.join([
            aid, username, name, title, desc, readme,
            ' '.join(props.keys()),
            json_dumps_safe(schema)[:3000],
        ]).lower()

        supports_search = bool(prop_keys & {'query','search','searchquery','searchterms','q','keyword','keywords'}) or _scan(text, ['search query','searchterms','advanced search'])
        supports_adv = _scan(text, ['from:', 'since:', 'until:', 'advanced search'])
        supports_profile = bool(prop_keys & {'username','screenname','profile','profiles','profileurl','profileurls','fromuser','from_user'}) or _scan(text, ['from user','profile'])
        supports_since_until = bool(prop_keys & {'since','until','startdate','enddate','timesince','timeuntil','start','end'}) or _scan(text, ['since', 'until', 'startdate', 'enddate'])
        supports_unix = bool(prop_keys & {'timesinceunix','timeuntilunix','since_time','until_time','fromtimestamp','totimestamp'}) or _scan(text, ['unix', 'timestamp'])
        supports_max = bool(prop_keys & {'maxitems','max_items','limit','maxtweets','numberoftweets','maxresults'}) or _scan(text, ['max items','limit'])
        supports_lang = bool(prop_keys & {'lang','language','tweetlanguage'}) or _scan(text, ['language','lang'])

        likely_historical = supports_since_until or supports_unix or _scan(text, ['historical', 'archive'])
        likely_cashtag = _scan(text, ['cashtag', '$tsla', '$aapl', 'ticker'])

        row: dict[str, Any] = {
            'actor_id': aid,
            'username': username,
            'name': name,
            'title': title[:200],
            'actorPermissionLevel': perm,
            'isDeprecated': str(deprecated).lower(),
            'totalUsers': str(total_users),
            'monthlyUsers': str(monthly_users),
            'rating': str(rating),
            'pricing_summary': pricing,
            'modifiedAt': modified,
            'supports_search_query': str(supports_search).lower(),
            'supports_advanced_search_syntax': str(supports_adv).lower(),
            'supports_profile_or_from_user': str(supports_profile).lower(),
            'supports_since_until_dates': str(supports_since_until).lower(),
            'supports_unix_time_filters': str(supports_unix).lower(),
            'supports_max_items': str(supports_max).lower(),
            'supports_language_filter': str(supports_lang).lower(),
            'likely_historical': str(likely_historical).lower(),
            'likely_cashtag_search': str(likely_cashtag).lower(),
            'decision': '',
            'reason': '',
            'readme': readme[:1200],
            'input_schema_text': json_dumps_safe(schema)[:2000],
            'example_input_text': json_dumps_safe(actor.get('exampleRunInput') or actor.get('defaultRunOptions') or {}),
        }
        decision, reason = classify(row)
        row['decision'] = decision
        row['reason'] = reason
        rows.append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES, lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in FIELDNAMES})

    counts = {}
    for r in rows:
        counts[r['decision']] = counts.get(r['decision'], 0) + 1

    lines = [
        '# X Apify actor discovery',
        '',
        f'Generated (UTC): `{now}`',
        f'Search queries used: `{len(SEARCH_QUERIES)}`',
        f'Seed actors checked: `{len(SEED_ACTORS)}`',
        f'Total actors evaluated: `{len(rows)}`',
        '',
        '## Decision summary',
        '',
    ]
    for k in sorted(counts.keys()):
        lines.append(f'- `{k}`: {counts[k]}')

    def rank_key(r: dict[str, Any]) -> tuple:
        perm = r.get('actorPermissionLevel')
        pscore = 0 if perm == 'LIMITED_PERMISSIONS' else (1 if not perm else 2)
        hist = r.get('supports_since_until_dates') == 'true' or r.get('supports_unix_time_filters') == 'true'
        search = r.get('supports_advanced_search_syntax') == 'true' or r.get('supports_search_query') == 'true'
        from_user = r.get('supports_profile_or_from_user') == 'true'
        return (
            pscore,
            0 if search else 1,
            0 if hist else 1,
            0 if from_user else 1,
            0 if r.get('supports_max_items') == 'true' else 1,
            r.get('actor_id',''),
        )

    candidates = [r for r in rows if r['decision'] in {'LIMITED_PERMISSION_CANDIDATE','UNKNOWN_PERMISSION_AUTH_PROBE'}]
    candidates.sort(key=rank_key)

    lines.extend(['', '## Top candidates', ''])
    for r in candidates[:15]:
        lines.append(
            f"- `{r['actor_id']}` perm=`{r['actorPermissionLevel'] or 'unknown'}` "
            f"search={r['supports_search_query']} adv={r['supports_advanced_search_syntax']} "
            f"dates={r['supports_since_until_dates']} unix={r['supports_unix_time_filters']} "
            f"from={r['supports_profile_or_from_user']} decision=`{r['decision']}`"
        )

    OUT_MD.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    print(f'WROTE_MD={OUT_MD.relative_to(ROOT)}')
    print(f'WROTE_CSV={OUT_CSV.relative_to(ROOT)}')


def json_dumps_safe(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=True)
    except Exception:
        return ''


if __name__ == '__main__':
    main()
