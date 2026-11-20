"""Read Gradio queue failures instead of losing them as simple-API data:null."""
import json
import logging
import uuid

import httpx
from fastapi import HTTPException

LOGGER = logging.getLogger(__name__)


def queue_failure(error):
    # Classify known infrastructure errors without logging source text, headers
    # or opaque exception bodies from third-party libraries.
    text = str(error or '').casefold()
    if 'quota' in text or 'gpu time' in text or 'daily limit' in text:
        status, code = 429, 'HF_GPU_QUOTA'
        detail = 'HF ZeroGPU đã hết hạn mức cho lượt gọi API. Cần chờ hạn mức được cấp lại.'
    elif 'duration' in text and ('exceed' in text or 'larger' in text or 'maximum' in text):
        status, code = 503, 'HF_GPU_DURATION'
        detail = 'HF chưa cấp được lượt GPU với thời gian yêu cầu.'
    elif any(word in text for word in ('bản nháp', 'căn cứ', 'trích dẫn', 'câu hỏi', 'dữ kiện')):
        status, code = 502, 'MODEL_DRAFT_REJECTED'
        detail = 'Model chưa trả bản nháp đúng cấu trúc và trích dẫn. Chưa tạo kết quả.'
    else:
        status, code = 503, 'HF_GPU_UNAVAILABLE'
        detail = 'HF chưa cấp được tiến trình suy luận. Vui lòng thử lại sau.'
    LOGGER.warning('HF queue failed code=%s', code)
    return HTTPException(status, detail, headers={'X-AI-Error-Code': code})


async def queued_result(port, api_name, data, ip_token='', timeout=180):
    session = uuid.uuid4().hex
    try:
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', timeout=timeout, trust_env=False,
                                    headers={'x-ip-token': ip_token} if ip_token else {}) as client:
            config = await client.get('/config')
            config.raise_for_status()
            function = next(dep['id'] for dep in config.json()['dependencies'] if dep.get('api_name') == api_name)
            joined = await client.post('/gradio_api/queue/join', json={'data': data, 'fn_index': function,
                                                                       'session_hash': session})
            if joined.status_code == 503:
                raise queue_failure('queue full')
            joined.raise_for_status()
            event = joined.json()['event_id']
            LOGGER.info('HF queue submitted api=%s event=%s hasIpToken=%s', api_name, event, bool(ip_token))
            async with client.stream('GET', '/gradio_api/queue/data', params={'session_hash': session}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith('data: '):
                        continue
                    message = json.loads(line[6:])
                    if message.get('event_id') not in (None, event):
                        continue
                    if message.get('msg') == 'process_completed':
                        output = message.get('output', {})
                        if message.get('success') is not True:
                            raise queue_failure(output.get('error'))
                        result = output.get('data')
                        if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
                            return result[0]
                        break
                    if message.get('msg') in ('unexpected_error', 'server_stopped'):
                        raise queue_failure(message.get('message'))
    except httpx.TimeoutException as error:
        raise HTTPException(504, 'HF phản hồi quá thời gian.', headers={'X-AI-Error-Code': 'HF_QUEUE_TIMEOUT'}) from error
    except (httpx.HTTPError, ValueError, KeyError, StopIteration) as error:
        raise HTTPException(502, 'Hàng đợi HF chưa trả dữ liệu hợp lệ.', headers={'X-AI-Error-Code': 'HF_QUEUE_PROTOCOL'}) from error
    raise HTTPException(502, 'Chưa nhận được bản nháp hoàn chỉnh từ HF.', headers={'X-AI-Error-Code': 'HF_QUEUE_INCOMPLETE'})
