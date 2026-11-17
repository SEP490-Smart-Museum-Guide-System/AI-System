"""Check real Gradio HTTP/queue integration with a labelled model fixture.

Install the Gradio bundle requirements, then run:
python deploy/huggingface/check_gradio_contract.py --bundle <exported-folder>
This does NOT download a model, use CUDA or verify HF quota/inference quality.
"""
import argparse
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import types
import httpx


def run(bundle, port):
    sys.path.insert(0, str(bundle.resolve()))
    os.environ['PORT'] = str(port)
    os.environ['GRADIO_SERVER_PORT'] = str(port)
    os.environ['AI_CHAT_SERVICE_KEY'] = secrets.token_urlsafe(32)
    os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
    # HF may enable SSR by environment; the app must still start one listener.
    os.environ['GRADIO_SSR_MODE'] = 'true'
    fixture = {'question': 'Bình gốm dùng để làm gì?', 'options': ['Đựng nước', 'Dệt vải', 'Ghi chép', 'Nấu cơm'],
        'correctIndex': 0, 'explanation': 'Bình gốm được dùng để đựng nước.',
        'evidenceQuote': 'Bình gốm được dùng để đựng nước.'}
    fixtures = [fixture,
        {**fixture, 'question': 'Bình gốm được làm bằng chất liệu gì?', 'options': ['Đất nung', 'Sắt', 'Nhựa', 'Thủy tinh'], 'evidenceQuote': 'Chất liệu là đất nung.'},
        {**fixture, 'question': 'Miệng bình có đặc điểm gì?', 'options': ['Loe rộng', 'Bịt kín', 'Có nắp gỗ', 'Hình vuông'], 'evidenceQuote': 'Miệng bình loe rộng.'},
        {**fixture, 'question': 'Thân bình có loại hoa văn gì?', 'options': ['Khắc chìm', 'In nổi', 'Dát vàng', 'Không trang trí'], 'evidenceQuote': 'Thân bình có hoa văn khắc chìm.'},
        {**fixture, 'question': 'Bình được làm bằng kỹ thuật gì?', 'options': ['Bàn xoay', 'Đúc khuôn kim loại', 'Thổi thủy tinh', 'In máy'], 'evidenceQuote': 'Bình được làm bằng kỹ thuật bàn xoay.'}]
    for item in fixtures[1:]: item['explanation'] = item['evidenceQuote']
    full_source = ' '.join(item['evidenceQuote'] for item in fixtures)

    class FixtureEngine:
        device = 'cpu-fixture'
        def __init__(self):
            self.lock = threading.Lock()
            self.force_duplicate = False
            self.fail_after = None
            self.fail_once = False
            self.wrong_evidence = False
        def generate_json(self, prompt, validator, **kwargs):
            from app.engine import ChatFailure
            payload = json.loads(prompt.rsplit('<|im_start|>user\n', 1)[1].split('<|im_end|>')[0])
            excluded = payload['EXCLUDED']
            if self.fail_once:
                self.fail_once = False
                raise ChatFailure('Invalid first fixture draft.', 502)
            if self.fail_after is not None and len(excluded) >= self.fail_after:
                raise ChatFailure('GPU quota fixture exhausted.', 503)
            candidate = fixture if self.force_duplicate else next((item for item in fixtures if item['question'] not in excluded), fixture)
            if 'EVIDENCE' in payload:
                index = next((part['id'] for part in payload['EVIDENCE'] if part['text'] == candidate['evidenceQuote']), 0)
                if self.wrong_evidence:
                    index = (index + 1) % len(payload['EVIDENCE'])
                candidate = {key: candidate[key] for key in ('question', 'options', 'correctIndex')}
                candidate['evidenceIndex'] = index
            return validator(json.dumps(candidate, ensure_ascii=False))

    replacement = types.ModuleType('pytorch_engine')
    replacement.TorchQuizEngine = FixtureEngine
    sys.modules['pytorch_engine'] = replacement
    spec = importlib.util.spec_from_file_location('space_entry', bundle / 'app.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    # Exercise the actual SDK hook used by ZeroGPU, without claiming GPU access.
    from spaces.zero.gradio import one_launch
    hook_calls = []
    one_launch(lambda: hook_calls.append('startup'))
    entry.launch(prevent_thread_lock=True)
    report = {'model_fixture': True, 'real_model_inference': False, 'hf_zerogpu_tested': False,
        'dependencies': {name: importlib.metadata.version(name) for name in
            ('gradio', 'spaces', 'torch', 'transformers', 'huggingface-hub')}, 'checks': []}

    def check(label, actual, expected):
        report['checks'].append({'name': label, 'actual': actual, 'expected': expected, 'passed': actual == expected})

    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=40, trust_env=False) as client:
            check('UI', client.get('/').status_code, 200)
            check('ZeroGPU launch hook runs once (probe)', hook_calls, ['startup'])
            check('SSR disabled despite environment default', entry.demo.ssr_mode, False)
            config = client.get('/config').json()
            count_component = next(component for component in config['components'] if component['props'].get('label') == 'Số lượng câu hỏi')
            check('default quiz set size', count_component['props']['value'], 5)
            check('readiness', client.get('/ready').status_code, 200)
            payload = {'artifactId': 1, 'artifactName': 'Bình gốm DEMO',
                'sourceText': 'Bình gốm được dùng để đựng nước. Đây là tư liệu giả lập để kiểm thử phần mềm.',
                'mode': 'quiz', 'difficulty': 'easy'}
            route = '/api/v1/studio/drafts'
            headers = {'X-Service-Key': os.environ['AI_CHAT_SERVICE_KEY']}
            check('missing service key', client.post(route, json=payload).status_code, 401)
            check('narration unsupported', client.post(route, headers=headers, json={**payload, 'mode': 'narration'}).status_code, 422)
            check('short source', client.post(route, headers=headers, json={**payload, 'sourceText': 'short'}).status_code, 422)
            check('invalid difficulty', client.post(route, headers=headers, json={**payload, 'difficulty': 'invalid'}).status_code, 422)
            check('too many exclusions', client.post(route, headers=headers, json={**payload, 'excludeQuestions': ['x'] * 6}).status_code, 422)
            result = client.post(route, headers=headers, json=payload)
            check('REST through real Gradio queue', result.status_code, 200)
            report['quiz_response'] = result.json()
            check('raw quiz response', result.json(), fixture)
            duplicate = client.post(route, headers=headers, json={**payload, 'excludeQuestions': [fixture['question']]})
            check('duplicate fixture quiz rejected', duplicate.status_code, 503)
            batch_route = '/api/v1/studio/quiz-sets'
            batch_payload = {**payload, 'sourceText': full_source}
            check('batch requires service key', client.post(batch_route, json=batch_payload).status_code, 401)
            batch = client.post(batch_route, headers=headers, json=batch_payload)
            check('batch HTTP', batch.status_code, 200)
            batch = batch.json()
            report['five_question_fixture_response'] = batch
            check('default batch generates five', batch['generatedCount'], 5)
            check('five-question batch is complete', batch['complete'], True)
            check('five unique questions', len(set(q['question'] for q in batch['questions'])), 5)
            check('four options per question', [len(q['options']) for q in batch['questions']], [4]*5)
            check('batch count three', client.post(batch_route, headers=headers, json={**batch_payload,'count':3}).json()['generatedCount'], 3)
            check('unsupported count', client.post(batch_route, headers=headers, json={**batch_payload,'count':2}).status_code, 422)
            # The current FE still requests five single-item BE drafts with exclusions.
            previous=[]
            for _ in range(5):
                item=client.post(route, headers=headers, json={**batch_payload,'excludeQuestions':previous})
                if item.status_code != 200: break
                previous.append(item.json()['question'])
            check('legacy FE five sequential drafts', len(set(previous)), 5)
            entry.ENGINE.force_duplicate = True
            partial=client.post(batch_route, headers=headers,json=batch_payload).json()
            check('duplicate does not pad batch', partial['generatedCount'], 1)
            check('duplicate batch marked incomplete', partial['complete'], False)
            check('partial batch explains failure', bool(partial['warnings']), True)
            entry.ENGINE.force_duplicate = False
            entry.ENGINE.fail_after = 2
            partial=client.post(batch_route, headers=headers,json=batch_payload).json()
            check('quota failure preserves two valid questions', partial['generatedCount'], 2)
            check('quota failure is incomplete', partial['complete'], False)
            entry.ENGINE.fail_after = None
            from quiz_set import generate_quiz_set
            from app.engine import ChatFailure
            try:
                generate_quiz_set(entry.ENGINE, 'Bình', full_source, 'easy', [], 5, budget_seconds=0)
                expired = False
            except ChatFailure as error:
                expired = error.status == 504
            check('batch deadline enforced', expired, True)
            from grounded_quiz import validate_indexed_question, evidence_passages
            passages = evidence_passages(full_source)
            raw={'question':fixture['question'],'options':fixture['options'],'correctIndex':0,'evidenceIndex':0}
            grounded, _ = validate_indexed_question(json.dumps(raw), full_source, passages, [])
            check('quote is copied exactly from selected source', grounded['evidenceQuote'], passages[0])
            for label, bad in [('out-of-range evidence index', {**raw,'evidenceIndex':999}),
                ('wrong evidence for correct option', {**raw,'evidenceIndex':1}),
                ('invented quote field', {**raw,'evidenceQuote':'Invented text.'})]:
                try:
                    validate_indexed_question(json.dumps(bad), full_source, passages, [])
                    rejected=False
                except ChatFailure:
                    rejected=True
                check(label+' rejected', rejected, True)
            long_source='A'*1100+' '+full_source
            check('long source passages are exact substrings', all(part in long_source and 6<=len(part)<=1000 for part in evidence_passages(long_source)),True)
            entry.ENGINE.fail_once=True
            retried=client.post(batch_route,headers=headers,json=batch_payload).json()
            check('one invalid draft retried within batch budget', retried['generatedCount'],5)
            entry.ENGINE.wrong_evidence=True
            try:
                entry.gpu_quiz('Bình',full_source,'easy',[],5)
                worker_message=False
            except entry.gr.Error as error:
                worker_message='đoạn tư liệu' in str(error)
            finally:
                entry.ENGINE.wrong_evidence=False
            check('GPU worker preserves actionable validation error',worker_message,True)
    finally:
        entry.demo.close()
    return report


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--port', type=int, default=17861)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = run(args.bundle, args.port)
    if args.output: args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not all(item['passed'] for item in result['checks']): sys.exit(1)
