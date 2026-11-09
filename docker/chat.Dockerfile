FROM python:3.12-slim-bookworm
WORKDIR /app
COPY ["AI Chat/requirements.txt", "requirements.txt"]
RUN pip install --no-cache-dir -r requirements.txt
COPY ["AI Chat/app", "app"]
COPY ["tools/download_chat_model.py", "tools/download_chat_model.py"]
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8003
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "1", "--no-access-log"]
