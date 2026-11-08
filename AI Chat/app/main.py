from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import secrets

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.datastructures import Headers

from app.engine import ChatFailure, OnnxChat

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
REVISION = 'd54957e3af1be04546436e874a60fe386041b244'
DEFAULT_MODEL = ROOT / 'state/models/chat/models--onnx-community--Qwen2.5-1.5B-Instruct/snapshots' / REVISION
SERVICE_KEY = os.environ.get('AI_CHAT_SERVICE_KEY', '')


class Context(BaseModel):
    model_config = ConfigDict(extra='forbid')
    artifactId: int = Field(gt=0)
    artifactName: str = Field(max_length=1000)
    title: str = Field(max_length=1000)
    description: str = Field(max_length=24000)
    narrationText: str = Field(default='', max_length=24000)

    @model_validator(mode='after')
    def bound_source(self):
        if sum(len(v) for v in [self.artifactName, self.title, self.description, self.narrationText]) > 24000:
            raise ValueError('Source too long')
        return self


class Turn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: str = Field(pattern='^(user|assistant)$')
    text: str = Field(min_length=1, max_length=4000)


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid')
    context: Context
    question: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def validate_history(self):
        if not self.question.strip() or len(self.history) % 2 or any(
            t.role != ('user' if i % 2 == 0 else 'assistant') or not t.text.strip() for i, t in enumerate(self.history)
        ):
            raise ValueError('Invalid question/history')
        return self


class ServiceGuard:
    """Authenticate before parsing; bound body size even with chunked transfer."""
    def __init__(self, app, key):
        self.app, self.key = app, key

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'):
            return await self.app(scope, receive, send)
        provided = Headers(scope=scope).get('x-service-key', '')
        if not self.key or not provided or not secrets.compare_digest(provided.encode(), self.key.encode()):
            return await JSONResponse({'detail': 'Thông tin xác thực dịch vụ không hợp lệ.'}, 401)(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > 144000:
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
        await self.app(scope, replay, send)


@asynccontextmanager
async def lifespan(app):
    if not SERVICE_KEY:
        raise RuntimeError('Configure AI_CHAT_SERVICE_KEY')
    try:
        app.state.engine = OnnxChat(os.environ.get('AI_CHAT_MODEL_DIR', str(DEFAULT_MODEL)))
        app.state.model_ready = True
    except Exception:
        LOGGER.error('Local chat model unavailable; configure/download model assets before using /ready.')
    yield
    app.state.model_ready = False
    app.state.engine = None


app = FastAPI(title='SMGS Local Artifact Guide', lifespan=lifespan)
app.state.model_ready = False
app.state.engine = None
app.add_middleware(ServiceGuard, key=SERVICE_KEY)


@app.get('/live')
async def live():
    return {'status': 'ok', 'service': 'artifact-chat'}


@app.get('/health')
@app.get('/ready')
def ready():
    if not app.state.model_ready:
        raise HTTPException(503, 'Model chatbot local chưa sẵn sàng.')
    return {'status': 'ok', 'model_ready': True, 'model': app.state.engine.model_name,
            'runtime': app.state.engine.runtime, 'providers': app.state.engine.providers}


@app.post('/api/v1/guide/answers')
def answer(request: Question):
    if not app.state.model_ready or app.state.engine is None:
        raise HTTPException(503, 'Model chatbot local chưa sẵn sàng.')
    try:
        return app.state.engine.answer(request.context.model_dump(), request.question.strip(), [t.model_dump() for t in request.history])
    except ChatFailure as exc:
        return JSONResponse({'detail': str(exc)}, status_code=exc.status, headers={'Retry-After': '2'} if exc.status == 503 else None)
    except Exception:
        LOGGER.error('Local chat inference failed.')
        return JSONResponse({'detail': 'Chưa thể tạo câu trả lời. Vui lòng thử lại.'}, status_code=503)
