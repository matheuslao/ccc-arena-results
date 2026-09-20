FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY LICENSE ./
COPY src ./src
COPY config ./config
COPY tests ./tests

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["ccc-arena", "config", "check"]
