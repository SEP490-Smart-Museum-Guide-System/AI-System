"""Anonymous public Space smoke: real chatbot inference and CPU tour outputs.

Does not read local secrets, access a DB, or establish production uptime/quality.
"""
import argparse
import datetime
import json
from pathlib import Path
import time

import httpx


def run(args):
    examples = json.loads((Path(__file__).parent / 'gradio-guide/examples.json').read_text(encoding='utf-8'))
    report = {'baseUrl': args.base_url, 'checkedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'real_model_request': True, 'sourcesAreSynthetic': True, 'anonymous': True, 'checks': [], 'calls': []}

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    def check(name, actual, expected):
        report['checks'].append({'name': name, 'actual': actual, 'expected': expected, 'passed': actual == expected})
        save()

    with httpx.Client(base_url=args.base_url, timeout=180, follow_redirects=True) as client:
        metadata = client.get('https://huggingface.co/api/spaces/Trungnam1644/smgs-ai-guide')
        metadata.raise_for_status()
        info = metadata.json()
        report['space'] = {key: info.get(key) for key in ('sha', 'runtime', 'sdk')}
        ready = client.get('/ready')
        report['readiness'] = {'status': ready.status_code, 'body': ready.json()}
        check('Space model loaded', ready.json().get('model_ready'), True)
        check('deployed model uses CUDA', ready.json().get('device'), 'cuda')
        for path in ('/api/v1/guide/answers', '/api/v1/tours/recommend'):
            response = client.post(path, content=b'not-json')
            check(path + ' rejects anonymous REST', response.status_code in (401, 503), True)

        def call(endpoint, data):
            started = time.monotonic()
            row = {'api': endpoint, 'input': data}
            report['calls'].append(row)
            try:
                response = client.post('/gradio_api/call/' + endpoint, json={'data': data})
                response.raise_for_status()
                identifier = response.json()['event_id']
                events = []
                kind = ''
                with client.stream('GET', '/gradio_api/call/' + endpoint + '/' + identifier) as stream:
                    stream.raise_for_status()
                    for line in stream.iter_lines():
                        if line.startswith('event: '):
                            kind = line[7:]
                        elif line.startswith('data: '):
                            payload = json.loads(line[6:])
                            if kind in ('complete', 'error'):
                                events.append({'event': kind, 'data': payload})
                                row['events'] = events
                                if kind == 'error':
                                    return None
                                return payload[0]
            except (httpx.HTTPError, ValueError, KeyError, IndexError) as error:
                row['transportError'] = type(error).__name__ + ': ' + str(error)
                return None
            finally:
                row['elapsedSeconds'] = round(time.monotonic() - started, 2)
                save()
                print(json.dumps({'api': endpoint, 'elapsedSeconds': row['elapsedSeconds'], 'events': row.get('events'),
                                  'transportError': row.get('transportError')}, ensure_ascii=False), flush=True)

        tour = examples['tour']
        pottery = call('goi_y_tour', [json.dumps(tour, ensure_ascii=False)])
        check('pottery tour returns stops', [s['artifactId'] for s in (pottery or {}).get('stops', [])], [2, 1])
        bronze = call('goi_y_tour', [json.dumps({**tour, 'interests': ['đồng']}, ensure_ascii=False)])
        check('bronze preference selects different artifact', [s['artifactId'] for s in (bronze or {}).get('stops', [])], [3])
        short = call('goi_y_tour', [json.dumps({**tour, 'availableMinutes': 5}, ensure_ascii=False)])
        check('short budget explicitly returns no stops', (short or {}).get('stops'), [])
        chat = examples['chat']
        context = json.dumps(chat['context'], ensure_ascii=False)
        result = call('hoi_hien_vat', [context, chat['question'], '[]'])
        report['real_chat_completed'] = bool(result and result.get('ok'))
        check('real chatbot answer supported from material source',
              bool(result and result.get('ok') and result.get('result', {}).get('supported') and
                   'đất nung' in result['result']['answer'].casefold()), True)
        if result and result.get('ok'):
            absent = call('hoi_hien_vat', [context, 'Bình gốm được chế tác vào năm nào?', '[]'])
            check('missing fact refused without invented year',
                  bool(absent and absent.get('ok') and absent.get('result') == {'answer': '', 'supported': False}), True)
    save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='https://trungnam1644-smgs-ai-guide.hf.space')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({'passed': sum(item['passed'] for item in result['checks']), 'total': len(result['checks']),
                      'failed': [item['name'] for item in result['checks'] if not item['passed']]}, ensure_ascii=False))
    if not all(item['passed'] for item in result['checks']):
        raise SystemExit(1)
