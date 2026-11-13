# Dual-runtime container: Python 3.12 + Node.js 20
FROM python:3.12-slim

# Install system dependencies, Node.js 20, and npm (needed by QA Engineer agent for Jest)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure output directory exists
RUN mkdir -p output

# Cloud platforms like Render and Railway dynamically inject PORT
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn orchestrator.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
