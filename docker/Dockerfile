FROM python:3.12-slim

# Install Node.js 22
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg; \
    mkdir -p /etc/apt/keyrings; \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg; \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends nodejs; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    jinja2 \
    psycopg2-binary \
    httpx \
    pydantic \
    python-multipart \
    aiofiles \
    pypdf \
    pyyaml

# Install beautiful-mermaid renderer
COPY app/mermaid-renderer /app/mermaid-renderer
RUN cd /app/mermaid-renderer && npm install --production

COPY app/app/ .

# Copy LLM Wiki into the image (self-contained container)
COPY llm-wiki /llm-wiki

RUN mkdir -p /var/log/activity

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2", "--timeout-keep-alive", "5", "--limit-max-requests", "10000"]