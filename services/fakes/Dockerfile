FROM ghcr.io/astral-sh/uv:0.9.7-python3.12-bookworm-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy

COPY pyproject.toml ./
RUN uv sync --no-dev
COPY app ./app

EXPOSE 8200
HEALTHCHECK --interval=5s --timeout=3s --retries=12 CMD [".venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8200/healthz', timeout=2)"]
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
