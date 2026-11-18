"""Live HF tour checks. Synthetic inputs; no DB or GPU. Optional hidden REST key input."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import getpass
import json
from pathlib import Path
import time

import httpx


def run(args):
    payload = json.loads((Path(__file__).parent / 'gradio-guide/examples.json').read_text(encoding='utf-8'))['tour']
    key = getpass.getpass('HF AI_TOUR_SERVICE_KEY (hidden, not saved): ').strip() if args.prompt_key else ''
    report = {'checkedAtUtc': datetime.now(timezone.utc).isoformat(), 'baseUrl': args.base_url,
              'syntheticData': True, 'realCloudTourAlgorithm': True, 'gpuRequired': False,
              'authenticatedRestTested': bool(key), 'cases': [], 'checks': []}

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    def check(name, actual, expected):
        report['checks'].append({'name': name, 'actual': actual, 'expected': expected, 'passed': actual == expected})
        save()

    with httpx.Client(base_url=args.base_url, timeout=60, follow_redirects=True) as client:
        ready = client.get('/ready')
        check('readiness HTTP', ready.status_code, 200)
        check('tour key configured', ready.json().get('tour_api_configured'), True)
        path = '/api/v1/tours/recommend'
        check('REST rejects missing key before JSON', client.post(path, content=b'not-json').status_code, 401)
        check('REST rejects wrong key', client.post(path, headers={'X-Service-Key': 'invalid-test-key'}, json=payload).status_code, 401)

        def call(label, body, expected_valid=True):
            row = {'name': label, 'input': body}
            report['cases'].append(row)
            start = time.monotonic()
            try:
                if key:
                    response = client.post(path, headers={'X-Service-Key': key}, json=body)
                    row['transport'] = 'authenticated-rest'
                    row['httpStatus'] = response.status_code
                    row['output'] = response.json()
                    valid = response.status_code == 200
                else:
                    row['transport'] = 'public-gradio-queue'
                    response = client.post('/gradio_api/call/goi_y_tour', json={'data': [json.dumps(body, ensure_ascii=False)]})
                    response.raise_for_status()
                    identifier = response.json()['event_id']
                    kind, valid = '', False
                    with client.stream('GET', '/gradio_api/call/goi_y_tour/' + identifier) as stream:
                        stream.raise_for_status()
                        for line in stream.iter_lines():
                            if line.startswith('event: '):
                                kind = line[7:]
                            elif line.startswith('data: ') and kind in ('complete', 'error'):
                                data = json.loads(line[6:])
                                row['event'] = kind
                                row['output'] = data[0] if kind == 'complete' else data
                                valid = kind == 'complete'
                                break
                check(label + ' accepted/rejected as expected', valid, expected_valid)
                result = row.get('output') if valid else None
                if expected_valid and isinstance(result, dict):
                    stops = result.get('stops', [])
                    ids = [stop['artifactId'] for stop in stops]
                    candidates = {c['artifactId']: c for c in body['candidates']}
                    check(label + ' only input artifact IDs', set(ids).issubset(candidates), True)
                    check(label + ' no duplicate stops', len(ids) == len(set(ids)), True)
                    check(label + ' within time budget', result['estimatedMinutes'] <= body['availableMinutes'], True)
                    check(label + ' duration equals stop totals', round(sum(s['visitMinutes'] + s['walkMinutes'] for s in stops), 6), result['estimatedMinutes'])
                    check(label + ' preserves content versions', all(s['contentVersionId'] == candidates[s['artifactId']]['contentVersionId'] for s in stops), True)
                return result
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
                # Do not include request headers or exception request representations.
                row['transportError'] = type(error).__name__
                check(label + ' transport succeeds', False, True)
                return None
            finally:
                row['elapsedSeconds'] = round(time.monotonic() - start, 2)
                save()
                print(json.dumps({'case': label, 'elapsedSeconds': row['elapsedSeconds'],
                                  'event': row.get('event'), 'httpStatus': row.get('httpStatus')}, ensure_ascii=False), flush=True)

        pottery = call('pottery 20 minutes', payload)
        check('pottery stops are bowl then vase', [s['artifactId'] for s in (pottery or {}).get('stops', [])], [2, 1])
        bronze = call('bronze 20 minutes', {**payload, 'interests': ['đồng']})
        check('bronze preference changes actual stops', [s['artifactId'] for s in (bronze or {}).get('stops', [])], [3])
        short = call('insufficient five minutes', {**payload, 'availableMinutes': 5})
        check('insufficient time returns zero stops', (short or {}).get('stops'), [])
        boundary = call('exact six-minute budget', {**payload, 'availableMinutes': 6})
        check('boundary fits bowl with orientation', (boundary or {}).get('estimatedMinutes'), 6)
        single = call('max one stop', {**payload, 'maxStops': 1})
        check('maxStops respected', len((single or {}).get('stops', [])), 1)
        unknown = call('unmatched interests', {**payload, 'interests': ['thiên văn']})
        check('unmatched interests explicitly labelled', (unknown or {}).get('usedFallback'), True)
        mixed = call('mixed interests 40 minutes', {**payload, 'interests': ['gốm', 'đồng'], 'availableMinutes': 40})
        check('mixed preferences include all three supplied objects', sorted(s['artifactId'] for s in (mixed or {}).get('stops', [])), [1, 2, 3])
        repeated = call('identical request repeat', payload)
        check('deterministic same request', repeated, pottery)
        foreign = deepcopy(payload)
        foreign['candidates'][0]['museumId'] = 2
        call('reject mixed museums', foreign, False)
        call('reject duplicate artifact IDs', {**payload, 'candidates': [payload['candidates'][0]] * 2}, False)
        call('reject empty interests', {**payload, 'interests': []}, False)
        call('reject duration beyond limit', {**payload, 'availableMinutes': 241}, False)
        if not key:
            report['notVerified'] = ['Authenticated REST success: run with --prompt-key and enter a current Secret locally. No key copied from chat or saved to this report.',
                                     'Real museum data/access control, tour persistence, high concurrency and full product integration.']
        save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='https://trungnam1644-smgs-ai-guide.hf.space')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prompt-key', action='store_true')
    args = parser.parse_args()
    report = run(args)
    print(json.dumps({'passed': sum(c['passed'] for c in report['checks']), 'total': len(report['checks']),
                      'failed': [c['name'] for c in report['checks'] if not c['passed']],
                      'authenticatedRestTested': report['authenticatedRestTested']}, ensure_ascii=False))
    if not all(c['passed'] for c in report['checks']):
        raise SystemExit(1)
