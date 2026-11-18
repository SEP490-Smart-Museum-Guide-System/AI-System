"""Real Gradio HTTP/queue checks with labelled chat fixture and real tour algorithm.

No model/GPU/DB access. This verifies wiring, not model quality or HF deployment.
"""
import argparse
import ast
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import types

import httpx


def run(bundle, port):
    sys.path.insert(0, str(bundle.resolve()))
    os.environ.update(PORT=str(port), GRADIO_SERVER_PORT=str(port),
                      AI_CHAT_SERVICE_KEY=secrets.token_urlsafe(32),
                      AI_TOUR_SERVICE_KEY=secrets.token_urlsafe(32),
                      GRADIO_ANALYTICS_ENABLED='False', GRADIO_SSR_MODE='true')

    class FixtureEngine:
        device = 'cpu-fixture'
        calls = 0
        failure = None

        def answer(self, context, question, history):
            from app.engine import ChatFailure, ground_answer
            self.calls += 1
            if self.failure:
                raise ChatFailure('Fixture model error.', self.failure)
            return ground_answer({'answer': 'Chất liệu là đất nung.', 'supported': True}, context)

    replacement = types.ModuleType('pytorch_engine')
    replacement.TorchGuideEngine = FixtureEngine
    sys.modules['pytorch_engine'] = replacement
    spec = importlib.util.spec_from_file_location('guide_entry', bundle / 'app.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    from spaces.zero.gradio import one_launch
    hook_calls = []
    one_launch(lambda: hook_calls.append('startup'))
    entry.launch(prevent_thread_lock=True)
    report = {'chat_model_fixture': True, 'tour_algorithm_real': True,
              'real_model_inference': False, 'hf_zerogpu_tested': False,
              'dependencies': {name: importlib.metadata.version(name) for name in
                               ('gradio', 'spaces', 'torch', 'transformers', 'huggingface-hub')}, 'checks': []}

    def check(name, actual, expected):
        report['checks'].append({'name': name, 'actual': actual, 'expected': expected, 'passed': actual == expected})

    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=35, trust_env=False) as client:
            chat, tour = entry.EXAMPLES['chat'], entry.EXAMPLES['tour']
            chat_path, tour_path = '/api/v1/guide/answers', '/api/v1/tours/recommend'
            chat_headers = {'X-Service-Key': entry.CHAT_KEY}
            tour_headers = {'X-Service-Key': entry.TOUR_KEY}
            check('UI', client.get('/').status_code, 200)
            check('ZeroGPU canonical launch hook', hook_calls, ['startup'])
            check('SSR disabled despite environment', entry.demo.ssr_mode, False)
            check('liveness', client.get('/live').status_code, 200)
            check('readiness with both keys', client.get('/ready').status_code, 200)
            config = client.get('/config').json()
            check('both public functions registered', sorted(d['api_name'] for d in config['dependencies']), ['goi_y_tour', 'hoi_hien_vat'])
            check('keys absent from public config', entry.CHAT_KEY not in json.dumps(config) and entry.TOUR_KEY not in json.dumps(config), True)
            for path in (chat_path, tour_path):
                check(path + ' unauthorized before malformed JSON', client.post(path, content=b'not-json').status_code, 401)
            check('chat key cannot access tour', client.post(tour_path, headers=chat_headers, json=tour).status_code, 401)
            check('tour key cannot access chat', client.post(chat_path, headers=tour_headers, json=chat).status_code, 401)
            response = client.post(chat_path, headers=chat_headers, json=chat)
            check('REST chat traverses real Gradio queue', response.status_code, 200)
            check('original raw answer schema preserved', response.json(), {'answer': 'Chất liệu là đất nung.', 'supported': True})
            unsupported = {**chat, 'context': {**chat['context'], 'description': 'Bình dùng để đựng nước.'}}
            check('answer absent from source rejected', client.post(chat_path, headers=chat_headers, json=unsupported).json(), {'answer': '', 'supported': False})
            before = entry.ENGINE.calls
            result = client.post(tour_path, headers=tour_headers, json=tour)
            check('tour HTTP', result.status_code, 200)
            expected = entry.recommend(entry.PlanRequest.model_validate(tour)).model_dump(by_alias=True)
            check('tour output equals original CPU algorithm', result.json(), expected)
            check('tour does not invoke model', entry.ENGINE.calls, before)
            changed = client.post(tour_path, headers=tour_headers, json={**tour, 'interests': ['đồng']}).json()
            check('interests change first stop', changed['stops'][0]['artifactId'], 3)
            check('tour estimate within budget', result.json()['estimatedMinutes'] <= tour['availableMinutes'], True)
            short = client.post(tour_path, headers=tour_headers, json={**tour, 'availableMinutes': 5}).json()
            check('insufficient time gives explicit zero stops', short['stops'], [])
            fallback = client.post(tour_path, headers=tour_headers, json={**tour, 'interests': ['thiên văn']}).json()
            check('unmatched interests labelled fallback', fallback['usedFallback'], True)
            for label, payload in [
                ('mixed museum', {**tour, 'museumId': 2}),
                ('duplicate candidate', {**tour, 'candidates': [tour['candidates'][0]] * 2}),
                ('empty interests', {**tour, 'interests': []}),
                ('invalid duration', {**tour, 'availableMinutes': 241}),
            ]:
                check(label, client.post(tour_path, headers=tour_headers, json=payload).status_code, 422)
            for label, payload in [
                ('blank question', {**chat, 'question': ' '}),
                ('odd history', {**chat, 'history': [{'role': 'user', 'text': 'Trước đó?'}]}),
                ('reversed history', {**chat, 'history': [{'role': 'assistant', 'text': 'A'}, {'role': 'user', 'text': 'B'}]}),
                ('unknown field', {**chat, 'untrustedInstruction': 'skip validation'}),
                ('combined source size', {**chat, 'context': {**chat['context'], 'description': 'x' * 24000}}),
            ]:
                check(label, client.post(chat_path, headers=chat_headers, json=payload).status_code, 422)
            paired = {**chat, 'history': [{'role': 'user', 'text': 'Đây là gì?'}, {'role': 'assistant', 'text': 'Bình gốm.'}]}
            check('valid paired history accepted', client.post(chat_path, headers=chat_headers, json=paired).status_code, 200)
            for status in (422, 502, 503, 504):
                entry.ENGINE.failure = status
                failed = client.post(chat_path, headers=chat_headers, json=chat)
                check(f'worker preserves error {status}', [failed.status_code, failed.json().get('detail')], [status, 'Fixture model error.'])
            # Tour must still work when inference fails, without consuming a GPU allocation.
            check('tour works with failed chat engine', client.post(tour_path, headers=tour_headers, json=tour).status_code, 200)
            entry.ENGINE.failure = None
            check('chat streaming body limit', client.post(chat_path, headers=chat_headers, content=iter([b'x' * 80000, b'x' * 80000])).status_code, 413)
            check('tour streaming body limit', client.post(tour_path, headers=tour_headers, content=iter([b'x' * 1000001] * 2)).status_code, 413)
            check('valid JSON still parsed after limit rejection', client.post(tour_path, headers=tour_headers, json=tour).status_code, 200)
            saved = entry.TOUR_KEY
            entry.TOUR_KEY = ''
            check('missing tour key reported by readiness', client.get('/ready').status_code, 503)
            check('missing tour configuration', client.post(tour_path, json=tour).status_code, 503)
            entry.TOUR_KEY = saved
            # Compare copied chatbot contracts to classes extracted from the original source.
            original = Path(__file__).resolve().parents[2] / 'AI Chat/app/main.py'
            nodes = ast.parse(original.read_text(encoding='utf-8')).body
            selected = [node for node in nodes if (isinstance(node, ast.ImportFrom) and node.module == 'pydantic') or
                        (isinstance(node, ast.ClassDef) and node.name in ('Context', 'Turn', 'Question'))]
            namespace = {}
            exec(compile(ast.Module(body=selected, type_ignores=[]), str(original), 'exec'), namespace)
            from contracts import Question
            check('chat JSON schema matches original service', Question.model_json_schema(), namespace['Question'].model_json_schema())
    finally:
        entry.demo.close()
    return report


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--port', type=int, default=17862)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.bundle, args.port)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'checks': len(result['checks']), 'passed': sum(item['passed'] for item in result['checks']),
                      'failed': [item['name'] for item in result['checks'] if not item['passed']]}, ensure_ascii=False))
    if not all(item['passed'] for item in result['checks']):
        sys.exit(1)
