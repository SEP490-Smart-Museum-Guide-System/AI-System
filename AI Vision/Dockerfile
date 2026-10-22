FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AI_DATA_DIR=/data \
    MODEL_CACHE_DIR=/models \
    MODEL_NUM_THREADS=2

WORKDIR /service

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN useradd --create-home --uid 10002 appuser \
    && mkdir -p /data /models \
    && chown -R appuser:appuser /service /data /models

USER appuser
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
