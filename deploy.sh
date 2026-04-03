#!/bin/bash
# Deploy Quantum Alpha Hunter to TARS (Mac Mini)
# Run this from the quantum-alpha-hunter directory when on home network

set -e

TARS_USER="Jbapckfan"
TARS_HOST="192.168.100.66"
TARS_PATH="/Users/Jbapckfan/quantum-alpha-hunter"
CONTAINER="quantum-alpha-hunter"

echo "=== Quantum Alpha Hunter — Deploy to TARS ==="

# Test connectivity
echo "[1/4] Testing TARS connection..."
ssh -o ConnectTimeout=5 ${TARS_USER}@${TARS_HOST} "echo 'Connected to TARS'" || {
    echo "ERROR: Cannot reach TARS at ${TARS_HOST}. Are you on the home network?"
    exit 1
}

# Create directory on TARS
echo "[2/4] Preparing TARS directory..."
ssh ${TARS_USER}@${TARS_HOST} "mkdir -p ${TARS_PATH}/data"

# Package and send
echo "[3/4] Deploying code to TARS..."
tar czf - \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='frontend/dist' \
    --exclude='mcp-server' \
    --exclude='data/*.db' \
    Dockerfile docker-compose.yml pyproject.toml qaht.cfg .env.example \
    qaht/ frontend/package.json frontend/package-lock.json frontend/src/ \
    frontend/index.html frontend/vite.config.ts frontend/tsconfig*.json \
    frontend/tailwind.config.js frontend/postcss.config.js frontend/eslint.config.js \
    frontend/public/ \
    | ssh ${TARS_USER}@${TARS_HOST} "cd ${TARS_PATH} && tar xzf -"

# Build and start container
echo "[4/4] Building and starting container..."
ssh ${TARS_USER}@${TARS_HOST} "cd ${TARS_PATH} && docker compose up -d --build"

echo ""
echo "=== Deployed! ==="
echo "Dashboard: http://${TARS_HOST}:8200/app/"
echo "API Docs:  http://${TARS_HOST}:8200/docs"
echo "Container: ${CONTAINER}"
