# Cloud backend image for bebita.club. The server runs STT+LLM relay only —
# no audio libraries (those live in the Windows capture agent).
FROM python:3.13-slim

WORKDIR /app

# System deps for building cryptography wheels if needed
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY cloud/requirements.txt /app/cloud/requirements.txt
RUN pip install --no-cache-dir -r /app/cloud/requirements.txt

# Source: the cloud package plus the reused pure-logic modules under src/
COPY cloud /app/cloud
COPY src /app/src

# SQLite lives here by default (mount a volume in prod); /data is referenced by DATABASE_URL
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000
CMD ["uvicorn", "cloud.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
