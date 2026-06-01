# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MCP_TRANSPORT=streamable-http \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# App source
COPY . .

# Cloud platforms route to whatever $PORT they inject; default 8000.
EXPOSE 8000

# Streamable-HTTP MCP endpoint is served at  http://HOST:PORT/mcp
CMD ["python", "server.py"]
