"""Gradio ZeroGPU quiz/narration studio + authenticated REST bridge for BE."""
import json
import os
import secrets
from typing import Literal
import spaces  # Must initialize ZeroGPU before loading the PyTorch model.
import gradio as gr
import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app.engine import ChatFailure
from app.studio import generate_draft
from pytorch_engine import TorchQuizEngine
from quiz_set import generate_quiz_set

ENGINE = TorchQuizEngine()  # CUDA placement at module scope, per ZeroGPU guidance.
KEY = os.environ.get('AI_CHAT_SERVICE_KEY', '')
DIFFICULTIES = ['easy', 'medium', 'hard']
PORT = int(os.environ.get('GRADIO_SERVER_PORT', os.environ.get('PORT', '7860')))


def checked(name, source, difficulty, excluded_json='[]'):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 300:
        raise ValueError('Nhập tên hiện vật từ 1 đến 300 ký tự.')
    if not isinstance(source, str) or not 20 <= len(source.strip()) <= 12000:
        raise ValueError('Nhập tư liệu từ 20 đến 12.000 ký tự.')
    if difficulty not in DIFFICULTIES: raise ValueError('Mức độ không hợp lệ.')
    try: excluded = json.loads(excluded_json)
    except (ValueError, TypeError) as error: raise ValueError('Danh sách câu hỏi đã có phải là JSON array.') from error
    if not isinstance(excluded, list) or len(excluded) > 5 or any(not isinstance(q,str) or not q.strip() or len(q)>1000 for q in excluded):
        raise ValueError('Danh sách có tối đa 5 câu hỏi, mỗi câu 1–1000 ký tự.')
    return name.strip(), source.strip(), difficulty, excluded


@spaces.GPU(duration=lambda name, source, difficulty, excluded, count: 45 if count == 1 else 90)
def gpu_quiz(name, source, difficulty, excluded, count):
    try:
        return generate_quiz_set(ENGINE, name, source, difficulty, excluded, count,
                                 budget_seconds=40 if count == 1 else 85)
    except ChatFailure as error:
        # Convert inside the worker: ZeroGPU otherwise discards custom error text.
        raise gr.Error(str(error)) from error


def submit(name, source, difficulty, excluded_json='[]', count=5):
    try:
        name, source, difficulty, excluded = checked(name, source, difficulty, excluded_json)
        if type(count) is not int or count not in (1, 3, 5):
            raise ValueError('Chọn bộ 1, 3 hoặc 5 câu hỏi.')
        return gpu_quiz(name, source, difficulty, excluded, count)
    except gr.Error:
        raise
    except (ValueError, ChatFailure) as error:
        raise gr.Error(str(error)) from error


@spaces.GPU(duration=45)
def gpu_narration(payload):
    try:
        request = QuizPayload.model_validate(payload)
        return {'ok': True, 'result': generate_draft(ENGINE, request)}
    except ChatFailure as error:
        return {'ok': False, 'error': {'status': error.status, 'detail': str(error)}}


def submit_narration(name, source, audience='general', tone='vivid'):
    try:
        request = QuizPayload(artifactId=1, artifactName=name, sourceText=source,
                              mode='narration', audience=audience, tone=tone)
    except ValueError as error:
        raise gr.Error('Kiểm tra tên hiện vật, tư liệu và phong cách thuyết minh.') from error
    return gpu_narration(request.model_dump())


demo = gr.Interface(fn=submit,
    inputs=[gr.Textbox(label='Tên hiện vật', value='Bình gốm DEMO', max_length=300),
        gr.Textbox(label='Tư liệu hiện vật đã kiểm duyệt', lines=7, max_length=12000,
            value='Bình gốm được dùng để đựng nước. Chất liệu là đất nung. Miệng bình loe rộng. Thân bình có hoa văn khắc chìm. Bình được làm bằng kỹ thuật bàn xoay. Đây là tư liệu giả lập để kiểm thử phần mềm, không phải hồ sơ hiện vật thật.'),
        gr.Dropdown(DIFFICULTIES, value='easy', label='Mức độ'),
        gr.Textbox(label='Câu hỏi đã có (JSON array, tùy chọn)', value='[]', max_length=6000),
        gr.Dropdown([1, 3, 5], value=5, label='Số lượng câu hỏi')],
    outputs=gr.JSON(label='Bộ quiz nháp — kiểm tra số câu, đáp án và nguồn trước khi lưu'),
    title='SMGS · Quiz và thuyết minh từ tư liệu hiện vật',
    description='Mặc định tạo bộ 5 câu trắc nghiệm tiếng Việt, mỗi câu theo một dữ kiện riêng. AI soạn câu hỏi; đáp án và trích dẫn bám nguồn. Với dữ kiện nhận diện được, lựa chọn nhiễu lấy từ danh sách tiếng Việt có kiểm soát. Kết quả cần người duyệt. Cả bộ dùng một lượt cấp GPU; nếu thiếu câu sẽ ghi complete=false. Chỉ dán tư liệu được phép công khai; ZeroGPU có quota và hàng đợi.',
    submit_btn='Tạo bộ câu hỏi',
    flagging_mode='never', api_name='tao_quiz', concurrency_limit=1)

with demo:
    with gr.Accordion('Soạn thuyết minh từ tư liệu', open=False):
        narration_name = gr.Textbox(label='Tên hiện vật', value='Bình gốm DEMO', max_length=300)
        narration_source = gr.Textbox(label='Tư liệu thuyết minh', lines=6, max_length=12000)
        narration_audience = gr.Dropdown(['children', 'general', 'scholar'], value='general', label='Đối tượng')
        narration_tone = gr.Dropdown(['vivid', 'inspiring', 'academic'], value='vivid', label='Phong cách')
        narration_result = gr.JSON(label='Bản nháp có trích dẫn — cần người duyệt')
        gr.Button('Soạn thuyết minh').click(submit_narration,
            [narration_name, narration_source, narration_audience, narration_tone], narration_result,
            api_name='soan_thuyet_minh', concurrency_limit=1)
demo.queue(max_size=8, default_concurrency_limit=1)
api = FastAPI(title='SMGS Gradio quiz bridge')


@api.get('/ready')
def ready():
    return {'status': 'ok', 'model_ready': True, 'model': 'Qwen2.5-1.5B-Instruct / PyTorch',
        'device': ENGINE.device, 'studio_modes': ['quiz', 'narration'],
        'note': 'Readiness does not guarantee available ZeroGPU quota.'}


class QuizPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artifactId: int = Field(gt=0)
    artifactName: str = Field(min_length=1, max_length=300)
    sourceText: str = Field(min_length=20, max_length=12000)
    mode: Literal['quiz', 'narration'] = 'quiz'
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    audience: Literal['children', 'general', 'scholar'] = 'general'
    tone: Literal['vivid', 'inspiring', 'academic'] = 'vivid'
    excludeQuestions: list[str] = Field(default_factory=list, max_length=5)


class QuizSetPayload(QuizPayload):
    count: Literal[1, 3, 5] = 5


async def queued_quiz(body, x_service_key, count, ip_token=''):
    if not KEY: raise HTTPException(503, 'Chưa cấu hình AI_CHAT_SERVICE_KEY trong Secrets.')
    if not secrets.compare_digest(x_service_key.encode(), KEY.encode()): raise HTTPException(401, 'Service key không hợp lệ.')
    if body.mode != 'quiz': raise HTTPException(422, 'Space này chỉ triển khai mode quiz.')
    try: name, source, difficulty, excluded = checked(body.artifactName, body.sourceText, body.difficulty, json.dumps(body.excludeQuestions))
    except ValueError as error: raise HTTPException(422, str(error)) from error
    # Enter through Gradio's queue so ZeroGPU gets the proper Gradio execution context.
    # This bridge uses anonymous HF quota; it does not confer unlimited backend GPU access.
    base = f'http://127.0.0.1:{PORT}'
    try:
        async with httpx.AsyncClient(base_url=base, timeout=210, trust_env=False,
                headers={'x-ip-token': ip_token} if ip_token else {}) as client:
            event = await client.post('/gradio_api/call/tao_quiz', json={'data': [name, source, difficulty, json.dumps(excluded,ensure_ascii=False), count]})
            event.raise_for_status(); identifier = event.json()['event_id']
            async with client.stream('GET', '/gradio_api/call/tao_quiz/' + identifier) as result:
                result.raise_for_status(); kind = ''
                async for line in result.aiter_lines():
                    if line.startswith('event: '): kind = line[7:]
                    elif line.startswith('data: ') and kind == 'complete':
                        value = json.loads(line[6:])
                        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict): break
                        return value[0]
                    elif line.startswith('data: ') and kind == 'error':
                        raise HTTPException(503, 'ZeroGPU chưa tạo được quiz: kiểm tra quota/hàng đợi và log Space.')
    except httpx.TimeoutException as error: raise HTTPException(504, 'Space phản hồi quá thời gian.') from error
    except (httpx.HTTPError, ValueError, KeyError) as error: raise HTTPException(502, 'Gradio chưa trả được kết quả hợp lệ.') from error
    raise HTTPException(502, 'Chưa nhận được quiz hoàn chỉnh từ Gradio.')


async def queued_narration(body, x_service_key, ip_token=''):
    if not KEY: raise HTTPException(503, 'Chưa cấu hình AI_CHAT_SERVICE_KEY trong Secrets.')
    if not secrets.compare_digest(x_service_key.encode(), KEY.encode()):
        raise HTTPException(401, 'Service key không hợp lệ.')
    # Use the same Gradio queue context required by ZeroGPU, rather than calling
    # a decorated GPU function directly from a FastAPI thread.
    try:
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{PORT}', timeout=180, trust_env=False,
                headers={'x-ip-token': ip_token} if ip_token else {}) as client:
            event = await client.post('/gradio_api/call/soan_thuyet_minh', json={'data': [
                body.artifactName, body.sourceText, body.audience, body.tone]})
            event.raise_for_status()
            identifier = event.json()['event_id']
            async with client.stream('GET', '/gradio_api/call/soan_thuyet_minh/' + identifier) as response:
                response.raise_for_status()
                kind = ''
                async for line in response.aiter_lines():
                    if line.startswith('event: '): kind = line[7:]
                    elif line.startswith('data: ') and kind == 'complete':
                        values = json.loads(line[6:])
                        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict): break
                        result = values[0]
                        if result.get('ok') is True:
                            return result['result']
                        error = result.get('error', {})
                        raise HTTPException(error.get('status', 503), error.get('detail', 'Chưa tạo được thuyết minh.'))
                    elif line.startswith('data: ') and kind == 'error':
                        raise HTTPException(503, 'ZeroGPU chưa tạo được thuyết minh: kiểm tra quota/hàng đợi Space.')
    except httpx.TimeoutException as error:
        raise HTTPException(504, 'Space phản hồi quá thời gian.') from error
    except (httpx.HTTPError, ValueError, KeyError) as error:
        raise HTTPException(502, 'Gradio chưa trả được thuyết minh hợp lệ.') from error
    raise HTTPException(502, 'Chưa nhận được thuyết minh hoàn chỉnh từ Gradio.')


@api.post('/api/v1/studio/drafts')
async def rest_quiz(body: QuizPayload, request: Request, x_service_key: str = Header(default='')):
    if body.mode == 'narration':
        return await queued_narration(body, x_service_key, request.headers.get('x-ip-token', ''))
    # Existing BE/FE requests one item at a time with prior questions excluded.
    # Preserve that contract rather than unexpectedly returning an array here.
    result = await queued_quiz(body, x_service_key, 1, request.headers.get('x-ip-token', ''))
    if result.get('generatedCount') != 1 or not result.get('complete'):
        raise HTTPException(502, 'Chưa nhận được một câu hỏi hợp lệ.')
    return result['questions'][0]


@api.post('/api/v1/studio/quiz-sets')
async def rest_quiz_set(body: QuizSetPayload, request: Request, x_service_key: str = Header(default='')):
    return await queued_quiz(body, x_service_key, body.count, request.headers.get('x-ip-token', ''))


def launch(*, prevent_thread_lock=False):
    # ZeroGPU's startup_report hooks Blocks.launch; direct uvicorn bypasses it.
    # Keep a single server. SSR's Node listener must not compete for port 7860.
    routes = [route for route in api.routes if route.path == '/ready' or route.path.startswith('/api/v1/')]
    return demo.launch(server_name='0.0.0.0', server_port=PORT, ssr_mode=False,
        app_kwargs={'routes': routes}, prevent_thread_lock=prevent_thread_lock)


if __name__ == '__main__':
    launch()
