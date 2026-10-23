FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_MODE=standalone \
    APP_ENV=production

WORKDIR /app

RUN groupadd --gid 10001 zhiku \
    && useradd --uid 10001 --gid zhiku --no-create-home --shell /usr/sbin/nologin zhiku

COPY requirements-standalone.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements-standalone.txt

COPY app ./app
COPY examples ./examples
COPY web/page/showcase.html ./web/page/showcase.html

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
