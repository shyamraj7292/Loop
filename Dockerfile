FROM python:3.11-slim

# System deps: build tools for a few wheels, libxml/libxslt for trafilatura/lxml.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # sentence-transformers / HF model cache lives on a mounted volume
    HF_HOME=/models

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Default command is the API; workers override it in docker-compose.
CMD ["uvicorn", "loop.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
