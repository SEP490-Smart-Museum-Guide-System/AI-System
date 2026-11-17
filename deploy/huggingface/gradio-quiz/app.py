"""Gradio ZeroGPU quiz demo + authenticated REST bridge for the existing BE."""
import json
import os
import secrets
from typing import Literal
import spaces  # Must initialize ZeroGPU before loading the PyTorch model.
import gradio as gr
import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.engine import ChatFailure
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


@spaces.GPU(duration=90)
def gpu_quiz(name, source, difficulty, excluded, count):
    try:
        return generate_quiz_set(ENGINE, name, source, difficulty, excluded, count)
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


demo = gr.Interface(fn=submit,
    inputs=[gr.Textbox(label='Tên hiện vật', value='Bình gốm DEMO', max_length=300),
        gr.Textbox(label='Tư liệu hiện vật đã kiểm duyệt', lines=7, max_length=12000,
            value='Bình gốm được dùng để đựng nước. Chất liệu là đất nung. Miệng bình loe rộng. Thân bình có hoa văn khắc chìm. Bình được làm bằng kỹ thuật bàn xoay. Đây là tư liệu giả lập để kiểm thử phần mềm, không phải hồ sơ hiện vật thật.'),
        gr.Dropdown(DIFFICULTIES, value='easy', label='Mức độ'),
        gr.Textbox(label='Câu hỏi đã có (JSON array, tùy chọn)', value='[]', max_length=6000),
        gr.Dropdown([1, 3, 5], value=5, label='Số lượng câu hỏi')],
    outputs=gr.JSON(label='Bộ quiz nháp — kiểm tra số câu, đáp án và nguồn trước khi lưu'),
    title='SMGS · Tạo quiz từ tư liệu hiện vật',
    description='Mặc định tạo bộ 5 câu trắc nghiệm tiếng Việt, mỗi câu có 4 lựa chọn, đáp án và trích dẫn nguồn. Cả bộ dùng một lượt cấp GPU. Nếu chưa đủ câu, kết quả ghi complete=false và số câu thực tế. Chỉ dán tư liệu được phép đưa lên Space công khai; ZeroGPU có quota và hàng đợi.',
    submit_btn='Tạo bộ câu hỏi',
    flagging_mode='never', api_name='tao_quiz', concurrency_limit=1)
demo.queue(max_size=8, default_concurrency_limit=1)
api = FastAPI(title='SMGS Gradio quiz bridge')


@api.get('/ready')
def ready():
    return {'status': 'ok', 'model_ready': True, 'model': 'Qwen2.5-1.5B-Instruct / PyTorch',
        'device': ENGINE.device, 'note': 'Readiness does not guarantee available ZeroGPU quota.'}


class QuizPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artifactId: int = Field(gt=0)
    artifactName: str = Field(min_length=1, max_length=300)
    sourceText: str = Field(min_length=20, max_length=12000)
    mode: str = 'quiz'
    difficulty: str = 'medium'
    audience: str = 'general'
    tone: str = 'vivid'
    excludeQuestions: list[str] = Field(default_factory=list, max_length=5)


class QuizSetPayload(QuizPayload):
    count: Literal[1, 3, 5] = 5


async def queued_quiz(body, x_service_key, count):
    if not KEY: raise HTTPException(503, 'Chưa cấu hình AI_CHAT_SERVICE_KEY trong Secrets.')
    if not secrets.compare_digest(x_service_key.encode(), KEY.encode()): raise HTTPException(401, 'Service key không hợp lệ.')
    if body.mode != 'quiz': raise HTTPException(422, 'Space này chỉ triển khai mode quiz.')
    try: name, source, difficulty, excluded = checked(body.artifactName, body.sourceText, body.difficulty, json.dumps(body.excludeQuestions))
    except ValueError as error: raise HTTPException(422, str(error)) from error
    # Enter through Gradio's queue so ZeroGPU gets the proper Gradio execution context.
    # This bridge uses anonymous HF quota; it does not confer unlimited backend GPU access.
    base = f'http://127.0.0.1:{PORT}'
    try:
        async with httpx.AsyncClient(base_url=base, timeout=210) as client:
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


@api.post('/api/v1/studio/drafts')
async def rest_quiz(body: QuizPayload, x_service_key: str = Header(default='')):
    # Existing BE/FE requests one item at a time with prior questions excluded.
    # Preserve that contract rather than unexpectedly returning an array here.
    result = await queued_quiz(body, x_service_key, 1)
    if result.get('generatedCount') != 1 or not result.get('complete'):
        raise HTTPException(502, 'Chưa nhận được một câu hỏi hợp lệ.')
    return result['questions'][0]


@api.post('/api/v1/studio/quiz-sets')
async def rest_quiz_set(body: QuizSetPayload, x_service_key: str = Header(default='')):
    return await queued_quiz(body, x_service_key, body.count)


def launch(*, prevent_thread_lock=False):
    # ZeroGPU's startup_report hooks Blocks.launch; direct uvicorn bypasses it.
    # Keep a single server. SSR's Node listener must not compete for port 7860.
    routes = [route for route in api.routes if route.path == '/ready' or route.path.startswith('/api/v1/')]
    return demo.launch(server_name='0.0.0.0', server_port=PORT, ssr_mode=False,
        app_kwargs={'routes': routes}, prevent_thread_lock=prevent_thread_lock)


if __name__ == '__main__':
    launch()
