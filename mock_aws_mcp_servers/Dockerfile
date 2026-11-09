FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "fastmcp>=2.2.0" "starlette>=0.37.0" "uvicorn>=0.30.0" "httpx>=0.27.0"

COPY server.py ./
COPY sample_payloads ./sample_payloads

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
