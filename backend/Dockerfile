FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY backend/requirements.txt /tmp/requirements.txt
COPY backend/requirements-rag.txt /tmp/requirements-rag.txt
ARG INSTALL_RAG_EXTRAS=0
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    if [ "$INSTALL_RAG_EXTRAS" = "1" ]; then \
        pip install --no-cache-dir -r /tmp/requirements-rag.txt; \
    fi

COPY pyproject.toml /workspace/pyproject.toml
COPY backend /workspace/backend
COPY configs /workspace/configs
COPY goldset /workspace/goldset
COPY mock /workspace/mock
COPY schemas /workspace/schemas
COPY frontend /workspace/frontend

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
