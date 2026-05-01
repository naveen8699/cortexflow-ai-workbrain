FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Install system deps + Node.js for MCP servers
RUN apt-get update && apt-get install -y \
    libpq-dev gcc curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Slack MCP server globally
RUN npm install -g @modelcontextprotocol/server-slack

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Download MCP Toolbox binary
RUN curl -s https://storage.googleapis.com/genai-toolbox/v0.7.0/linux/amd64/toolbox     -o /app/toolbox && chmod +x /app/toolbox

RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app

USER appuser

CMD ["/app/start.sh"]
