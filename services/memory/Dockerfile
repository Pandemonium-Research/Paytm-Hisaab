FROM ghcr.io/astral-sh/uv:0.9.7-python3.12-bookworm-slim AS dependencies

WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

FROM dependencies AS tests
RUN uv sync --locked
ENV PYTHONDONTWRITEBYTECODE=1 HISAAB_LIVE=0 MEMORY_BACKEND=stub

FROM dependencies AS runtime
COPY app ./app

EXPOSE 8100
HEALTHCHECK --interval=5s --timeout=3s --retries=12 CMD [".venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/healthz', timeout=2)"]
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]

