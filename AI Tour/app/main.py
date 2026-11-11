import hmac
import os
from fastapi import FastAPI, Header, HTTPException
from starlette.responses import JSONResponse
from .engine import recommend
from .schemas import PlanRequest, PlanResult

app = FastAPI(title="SMGS Personalized Tour", docs_url=None, redoc_url=None)


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        events = []
        size = 0
        while True:
            event = await receive()
            if event['type'] == 'http.disconnect':
                return
            size += len(event.get('body', b''))
            if size > 2_000_000:
                return await JSONResponse({'detail': 'Request too large'}, status_code=413)(scope, receive, send)
            events.append(event)
            if not event.get('more_body', False):
                break

        async def replay():
            return events.pop(0) if events else await receive()

        return await self.app(scope, replay, send)


app.add_middleware(BodyLimit)


@app.get("/ready")
@app.get("/live")
def ready():
    if len(os.environ.get("AI_TOUR_SERVICE_KEY", "")) < 32:
        raise HTTPException(503, "Configure internal tour service key")
    return {"status": "ready", "engineVersion": "content-tfidf-v1", "requiresGpu": False}


@app.post("/api/v1/tours/recommend", response_model=PlanResult)
def plan(body: PlanRequest, x_service_key: str = Header(default="")):
    expected = os.environ.get("AI_TOUR_SERVICE_KEY", "")
    if len(expected) < 32:
        raise HTTPException(503, "Tour service is not configured")
    if not hmac.compare_digest(x_service_key.encode(), expected.encode()):
        raise HTTPException(401, "Invalid service credentials")
    return recommend(body)
