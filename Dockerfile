FROM python:3.12-slim-bookworm

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV DEEPEGE_MCP_HOST=0.0.0.0 \
    DEEPEGE_MCP_PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

USER nobody

CMD ["deepege-connector"]
