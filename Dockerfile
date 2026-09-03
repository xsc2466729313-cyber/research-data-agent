FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /workspace

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY pyproject.toml /workspace/pyproject.toml
COPY backend /workspace/backend
COPY configs /workspace/configs
COPY goldset /workspace/goldset
COPY mock /workspace/mock
COPY schemas /workspace/schemas
COPY frontend /workspace/frontend

EXPOSE 8000

CMD ["sh", "-c", "exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
