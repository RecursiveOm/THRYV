FROM ghcr.io/astral-sh/uv:0.12.9 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
ARG INSTALL_VOICE=false
RUN if [ "$INSTALL_VOICE" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends libgomp1 build-essential cmake && \
      uv sync --locked --no-dev --no-install-project --extra voice && \
      apt-get purge -y --auto-remove build-essential cmake && rm -rf /var/lib/apt/lists/*; \
    else uv sync --locked --no-dev --no-install-project; fi
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN chmod -R a+rX app migrations && chmod a+r alembic.ini
RUN useradd --create-home --uid 10001 thryv && mkdir /data && chown thryv:thryv /data && chmod 700 /data
USER thryv
ENV PATH="/app/.venv/bin:$PATH" PORT=8000 DATABASE_URL=sqlite+aiosqlite:////data/thryv.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/health', timeout=3)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
