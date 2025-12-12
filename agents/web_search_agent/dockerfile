# agents/web_search_agent/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 系統依賴（簡短）
RUN apt-get update && apt-get install -y curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# copy requirements
COPY requirements.txt /app/requirements.txt

# 安裝 Python 套件
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy code
COPY . /app

EXPOSE 8001

# healthcheck hits our FastAPI /health
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# use uvicorn to run FastAPI app
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--loop", "asyncio"]
