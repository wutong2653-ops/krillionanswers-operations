#!/usr/bin/env python3
"""Archive the current Dive from the official JSON source; never generate pages."""
import datetime as dt
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_URL = 'https://krillion.io/api/today'
UTC = dt.timezone.utc

class StaleDive(ValueError):
    pass

def utcnow():
    return dt.datetime.now(UTC)

def instant(value):
    if not isinstance(value, str):
        raise ValueError('resetsAt must be a UTC ISO timestamp')
    value = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.utcoffset() != dt.timedelta(0):
        raise ValueError('resetsAt must use UTC')
    return value

def validate(payload, fetched_at, records):
    if not isinstance(payload, dict):
        raise ValueError('response must be a JSON object')
    number = payload.get('dayNumber')
    if type(number) is not int or number < 1:
        raise ValueError('dayNumber must be a positive integer')
    day = dt.date.fromisoformat(payload.get('date', ''))
    if day.isoformat() != payload['date']:
        raise ValueError('date must be YYYY-MM-DD')
    reset = instant(payload.get('resetsAt'))
    expected = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(5), UTC)
    if reset != expected:
        raise ValueError('resetsAt must be 05:00 UTC on the day after date')
    if fetched_at >= reset:
        raise StaleDive('fetchedAt must be earlier than resetsAt; ended Dive discarded')
    if fetched_at < reset - dt.timedelta(days=1):
        raise ValueError('Dive has not started at fetchedAt')
    prompts = payload.get('prompts')
    if not isinstance(prompts, list) or len(prompts) != 7:
        raise ValueError('prompts must contain exactly 7 entries')
    ids = []
    for item in prompts:
        if not isinstance(item, dict):
            raise ValueError('each prompt must be an object')
        ids.append(item.get('id'))
        if not isinstance(item.get('text'), str) or not item['text'].strip():
            raise ValueError('each prompt text must be a nonempty string')
    if sorted(ids, key=str) != ['p1','p2','p3','p4','p5','p6','p7']:
        raise ValueError('prompt IDs must be p1 through p7 exactly once')
    # Same-Dive reruns compare to the preceding distinct Dive, not to themselves.
    same = [r for r in records if r['dayNumber'] == number]
    if any(r['date'] != payload['date'] for r in same):
        raise ValueError('same dayNumber cannot change date')
    if records and number < max(r['dayNumber'] for r in records):
        raise ValueError('dayNumber regressed behind the latest stored Dive')
    earlier = [r for r in records if r['dayNumber'] < number]
    if earlier:
        previous = max(earlier, key=lambda r:r['dayNumber'])
        if number != previous['dayNumber'] + 1:
            raise ValueError('dayNumber must be previous dayNumber +1')
        if day != dt.date.fromisoformat(previous['date']) + dt.timedelta(days=1):
            raise ValueError('date must be previous date +1 day')
    return {'fetchedAt':fetched_at.isoformat().replace('+00:00','Z'),
            'date':payload['date'], 'dayNumber':number, 'resetsAt':payload['resetsAt'],
            'prompts':[{'id':p['id'],'text':p['text']} for p in prompts],
            'sourceUrl':SOURCE_URL}

def request():
    # Default Python client, no supplied UA, authentication, cookies or proxy rotation.
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=35) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)
    except (TimeoutError, socket.timeout) as error:
        return 0, str(error).encode(), {}
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            return 0, str(error).encode(), {}
        raise

def archive(root, log=print, fetch=None, clock=None, sleep=None):
    root = Path(root)
    fetch = fetch or request
    clock = clock or utcnow
    sleep = sleep or time.sleep
    records = []
    for path in sorted((root/'history').glob('*.json')):
        record = json.loads(path.read_text())
        if record.get('sourceUrl') != SOURCE_URL or type(record.get('dayNumber')) is not int:
            raise ValueError('unsupported archive record: '+path.name)
        records.append(record)
    for attempt in range(2):
        status, body, headers = fetch()
        fetched_at = clock()
        content_type = next((v for k,v in headers.items() if k.lower()=='content-type'),'')
        log(json.dumps({'fetchedAt':fetched_at.isoformat(), 'sourceUrl':SOURCE_URL,
                        'attempt':attempt+1,'status':status,'contentType':content_type,
                        'bodyFirst200':body.decode(errors='replace')[:200]},ensure_ascii=False))
        if status == 403 or b'error code: 1010' in body.lower():
            raise RuntimeError('被 Cloudflare 拦截，需在有正常出口网络的环境运行')
        if status == 0 or 500 <= status <= 599:
            if attempt == 0:
                log('Timeout/5xx: retry once in 60 seconds')
                sleep(60)
                continue
            raise RuntimeError('HTTP timeout/5xx after one retry: '+str(status))
        if status != 200:
            raise RuntimeError('HTTP status must be 200; got '+str(status))
        if content_type.split(';')[0].strip().lower() != 'application/json':
            raise ValueError('content-type must be application/json; got '+content_type)
        payload = json.loads(body)
        try:
            record = validate(payload, fetched_at, records)
        except StaleDive:
            if attempt == 0:
                log('Ended Dive: discard and retry once in 60 seconds')
                sleep(60)
                continue
            raise
        path = root/'history'/f'{record["date"]}.json'
        if path.exists():
            existing = json.loads(path.read_text())
            if existing.get('dayNumber') != record['dayNumber']:
                raise ValueError('date path belongs to another dayNumber')
        # All validation is complete before any archive file is created/replaced.
        text = json.dumps(record,ensure_ascii=False,indent=2)+'\n'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text)
        (root/'latest.json').write_text(text)
        log(json.dumps(record,ensure_ascii=False))
        return 0

def main(root=None):
    try:
        return archive(root or Path(__file__).parent)
    except Exception as error:
        print(f'Archive validation/fetch failed: {type(error).__name__}: {error}',file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
