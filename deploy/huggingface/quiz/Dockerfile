FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
ENV HOME=/home/user PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 \
    AI_CHAT_NUM_THREADS=2 AI_CHAT_CACHE_DIR=/home/user/model-cache \
    AI_CHAT_MODEL_DIR=/home/user/model-cache/models--onnx-community--Qwen2.5-1.5B-Instruct/snapshots/d54957e3af1be04546436e874a60fe386041b244
COPY --chown=user:user tools/download_chat_model.py ./tools/download_chat_model.py
USER user
# Download the pinned ONNX graph/tokenizer into the image; no DB or user data.
RUN python tools/download_chat_model.py
COPY --chown=user:user app ./app
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1", "--no-access-log"]
