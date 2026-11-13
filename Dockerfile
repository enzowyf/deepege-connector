ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" --upgrade pip \
    && pip install --no-cache-dir --index-url "$PIP_INDEX_URL" .

ENV DEEPEGE_MCP_HOST=0.0.0.0 \
    DEEPEGE_MCP_PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

USER nobody

CMD ["deepege-connector"]
