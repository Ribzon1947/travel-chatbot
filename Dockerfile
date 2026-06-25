FROM python:3.12-slim

# Install Node.js 20, nginx, supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates supervisor nginx \
    libgomp1 \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Node dependencies
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Application files
COPY app/ ./app/
COPY frontend/ ./frontend/
COPY frontend-server.js .
COPY pricing_data.json .

RUN mkdir -p /app/uploads /data /tmp/chatbot

# Default paths (overridden by docker-compose for local, and by render.yaml on Render)
ENV DATABASE_URL=sqlite:////data/chatbot.db
ENV FHE_DIR=/data/.fhe

# Nginx + Supervisor config
COPY nginx.conf /etc/nginx/sites-available/default
COPY supervisord.conf /etc/supervisor/conf.d/app.conf

EXPOSE 8080

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
