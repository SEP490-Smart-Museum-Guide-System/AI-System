"""Independent Gradio Space: source-constrained chatbot + CPU personalized tours."""
import json
import logging
import os
from pathlib import Path
import secrets

import spaces  # Initialize ZeroGPU before importing/loading the PyTorch model.
import gradio as gr
import httpx
from fastapi import FastAPI, HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.engine import ChatFailure
from contracts import Question
from pytorch_engine import TorchGuideEngine
from tour.engine import recommend
from tour.schemas import PlanRequest, PlanResult

LOGGER = logging.getLogger(__name__)
ENGINE = TorchGuideEngine()  # CUDA at module scope, as required by ZeroGPU.
CHAT_KEY = os.environ.get('AI_CHAT_SERVICE_KEY', '')
TOUR_KEY = os.environ.get('AI_TOUR_SERVICE_KEY', '')
PORT = int(os.environ.get('GRADIO_SERVER_PORT', os.environ.get('PORT', '7860')))
EXAMPLES = json.loads((Path(__file__).parent / 'examples.json').read_text(encoding='utf-8'))


class ApiGuard:
    """Protect REST before parsing and bound streamed bodies; keys never enter Gradio UI."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if scope['type'] != 'http' or not path.startswith('/api/'):
            return await self.app(scope, receive, send)
        expected = TOUR_KEY if path.startswith('/api/v1/tours/') else CHAT_KEY
        provided = Headers(scope=scope).get('x-service-key', '')
        if len(expected) < 32:
            return await JSONResponse({'detail': 'Chưa cấu hình khóa dịch vụ trong HF Secrets.'}, 503)(scope, receive, send)
        if not secrets.compare_digest(provided.encode(), expected.encode()):
            return await JSONResponse({'detail': 'Service key không hợp lệ.'}, 401)(scope, receive, send)
        limit = 2_000_000 if path.startswith('/api/v1/tours/') else 144000
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > limit:
                return await JSONResponse({'detail': 'Yêu cầu vượt giới hạn dung lượng.'}, 413)(scope, receive, send)
            if not message.get('more_body'):
                break
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        return await self.app(scope, replay, send)


@spaces.GPU(duration=60)
def gpu_chat(payload):
    try:
        request = Question.model_validate(payload)
        result = ENGINE.answer(request.context.model_dump(), request.question.strip(), [t.model_dump() for t in request.history])
        return {'ok': True, 'result': result}
    except ChatFailure as error:
        # A JSON envelope preserves known error messages/status across the GPU process.
        return {'ok': False, 'error': {'status': error.status, 'detail': str(error)}}
    except Exception:
        LOGGER.exception('Chat inference failed')
        return {'ok': False, 'error': {'status': 503, 'detail': 'Chưa thể tạo câu trả lời. Vui lòng thử lại.'}}


def submit_chat(context_json, question, history_json):
    try:
        if len(context_json) + len(question) + len(history_json) > 100000:
            raise ValueError('Nội dung nhập quá dài.')
        payload = Question(context=json.loads(context_json), question=question, history=json.loads(history_json))
    except (ValueError, TypeError) as error:
        raise gr.Error('Kiểm tra tư liệu, câu hỏi và lịch sử JSON; lịch sử gồm các cặp user/assistant.') from error
    return gpu_chat(payload.model_dump())


def submit_tour(request_json):
    try:
        if len(request_json.encode('utf-8')) > 2_000_000:
            raise ValueError('Danh sách hiện vật quá dài.')
        request = PlanRequest.model_validate_json(request_json)
    except (ValueError, TypeError) as error:
        raise gr.Error('JSON tour chưa hợp lệ: kiểm tra bảo tàng, hiện vật, sở thích và quỹ thời gian.') from error
    return recommend(request).model_dump(by_alias=True)


with gr.Blocks(title='SMGS · Chatbot và Tour cá nhân') as demo:
    gr.Markdown('# SMGS · Chatbot và Tour cá nhân\n'
                'Chatbot chỉ trích tư liệu được cung cấp. Tour dùng sở thích và thời gian, chạy CPU. '
                '**Ví dụ là dữ liệu giả lập.** Chỉ nhập tư liệu được phép đưa lên demo công khai. '
                'ZeroGPU có quota, hàng đợi và thời gian khởi động.')
    with gr.Tab('Chatbot hiện vật'):
        gr.Markdown('`supported=false` nghĩa là chưa có đáp án được chấp nhận từ nguồn. '
                    'Kiểm tra nội dung câu trả lời; trích đúng nguồn chưa bảo đảm trả lời đúng ý hỏi.')
        context = gr.Textbox(label='Tư liệu hiện vật (JSON)', lines=9, max_length=100000,
                             value=json.dumps(EXAMPLES['chat']['context'], ensure_ascii=False, indent=2))
        question = gr.Textbox(label='Câu hỏi', max_length=1000, value=EXAMPLES['chat']['question'])
        history = gr.Textbox(label='Lịch sử user/assistant (JSON array, tùy chọn)', lines=2, max_length=40000, value='[]')
        chat_output = gr.JSON(label='Kết quả chatbot — ok/result hoặc error')
        gr.Button('Hỏi hiện vật', variant='primary').click(
            submit_chat, [context, question, history], chat_output,
            api_name='hoi_hien_vat', concurrency_limit=1, concurrency_id='chat-inference')
    with gr.Tab('Tour cá nhân'):
        gr.Markdown('Danh sách hiện vật do bên gọi cung cấp. Thuật toán không tự đọc DB, '
                    'không xác minh quyền hay trạng thái xuất bản. Thời gian đi bộ là ước tính theo phòng/tầng.')
        tour_request = gr.Textbox(label='Yêu cầu tour (JSON)', lines=18, max_length=2000000,
                                  value=json.dumps(EXAMPLES['tour'], ensure_ascii=False, indent=2))
        tour_output = gr.JSON(label='Hành trình gợi ý')
        gr.Button('Gợi ý hành trình', variant='primary').click(
            submit_tour, tour_request, tour_output, api_name='goi_y_tour', concurrency_limit=2)
demo.queue(max_size=8, default_concurrency_limit=1)
api = FastAPI(title='SMGS HF Guide API')
api.add_middleware(ApiGuard)


@api.get('/live')
async def live():
    return {'status': 'ok', 'service': 'smgs-ai-guide'}


@api.get('/ready')
async def ready():
    configured = len(CHAT_KEY) >= 32 and len(TOUR_KEY) >= 32
    return JSONResponse(status_code=200 if configured else 503, content={
        'status': 'ok' if configured else 'configuration_required', 'model_ready': True,
        'model': 'Qwen2.5-1.5B-Instruct / PyTorch', 'device': ENGINE.device,
        'chat_api_configured': len(CHAT_KEY) >= 32, 'tour_api_configured': len(TOUR_KEY) >= 32,
        'tour_engine': 'content-tfidf-v1', 'note': 'Readiness does not guarantee ZeroGPU quota or uptime.',
    })


async def queued_answer(body: Question):
    # Use Gradio's queue to retain the ZeroGPU request context, as in the quiz Space.
    # Loopback requests consume anonymous HF quota, not an unlimited API allocation.
    try:
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{PORT}', timeout=180, trust_env=False) as client:
            event = await client.post('/gradio_api/call/hoi_hien_vat', json={'data': [
                json.dumps(body.context.model_dump(), ensure_ascii=False), body.question,
                json.dumps([t.model_dump() for t in body.history], ensure_ascii=False),
            ]})
            event.raise_for_status()
            identifier = event.json()['event_id']
            async with client.stream('GET', '/gradio_api/call/hoi_hien_vat/' + identifier) as response:
                response.raise_for_status()
                kind = ''
                async for line in response.aiter_lines():
                    if line.startswith('event: '):
                        kind = line[7:]
                    elif line.startswith('data: ') and kind == 'complete':
                        values = json.loads(line[6:])
                        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
                            break
                        value = values[0]
                        if value.get('ok') is False:
                            error = value.get('error', {})
                            status = error.get('status', 503)
                            raise HTTPException(status if status in (422, 502, 503, 504) else 503,
                                                error.get('detail', 'Chưa thể tạo câu trả lời.'))
                        if value.get('ok') is True:
                            from app.engine import ground_answer, parse_answer
                            # Validate once more at the HTTP boundary; preserve the original response shape.
                            return ground_answer(parse_answer(json.dumps(value['result'], ensure_ascii=False)), body.context.model_dump())
                        break
                    elif line.startswith('data: ') and kind == 'error':
                        raise HTTPException(503, 'ZeroGPU chưa xử lý được: kiểm tra quota, hàng đợi và log Space.')
    except httpx.TimeoutException as error:
        raise HTTPException(504, 'Hàng đợi hoặc model phản hồi quá thời gian.') from error
    except ChatFailure as error:
        raise HTTPException(error.status, str(error)) from error
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, 'Gradio chưa trả được kết quả hợp lệ.') from error
    raise HTTPException(502, 'Chưa nhận được câu trả lời hoàn chỉnh từ Gradio.')


@api.post('/api/v1/guide/answers')
async def answer(body: Question):
    return await queued_answer(body)


@api.post('/api/v1/tours/recommend', response_model=PlanResult)
def plan(body: PlanRequest):
    return recommend(body)


def launch(*, prevent_thread_lock=False):
    routes = [route for route in api.routes if route.path in ('/live', '/ready') or route.path.startswith('/api/v1/')]
    return demo.launch(server_name='0.0.0.0', server_port=PORT, ssr_mode=False,
                       app_kwargs={'routes': routes, 'middleware': api.user_middleware},
                       prevent_thread_lock=prevent_thread_lock)


if __name__ == '__main__':
    launch()
