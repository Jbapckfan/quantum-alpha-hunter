# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + built frontend
FROM python:3.13-slim
WORKDIR /app

# System deps for scipy/numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || \
    pip install --no-cache-dir pandas numpy scikit-learn yfinance praw SQLAlchemy \
    python-dotenv tqdm requests plotly pydantic ta structlog click beautifulsoup4 \
    lxml httpx fastapi "uvicorn[standard]" scipy matplotlib python-multipart

# Copy source
COPY qaht/ ./qaht/
COPY qaht.cfg ./
COPY .env.example ./.env

# Copy built frontend to serve as static
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Data directory for SQLite
RUN mkdir -p /app/data
ENV QAHT_DB_URL=sqlite:////app/data/qaht.db
ENV QAHT_WATCHLIST_FILE=/app/data/watchlist.json
ENV API_HOST=0.0.0.0
ENV API_PORT=3000

EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://0.0.0.0:3000/')" || exit 1

CMD ["python3", "-m", "uvicorn", "qaht.api.main:app", "--host", "0.0.0.0", "--port", "3000"]
