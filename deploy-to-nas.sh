#!/bin/bash
# Deploy Quantum Alpha Hunter to TARS (NAS)
# Run this from the quantum-alpha-hunter directory when on home network

set -e

NAS_USER="Jbapckfan"
NAS_HOST="192.168.100.35"
NAS_PATH="/home/Jbapckfan/quantum-alpha-hunter"
CONTAINER="quantum-alpha-hunter"

echo "=== Quantum Alpha Hunter — Deploy to TARS ==="

# Test connectivity
echo "[1/4] Testing NAS connection..."
ssh -o ConnectTimeout=5 ${NAS_USER}@${NAS_HOST} "echo 'Connected to TARS'" || {
    echo "ERROR: Cannot reach NAS at ${NAS_HOST}. Are you on the home network?"
    exit 1
}

# Create directory on NAS
echo "[2/4] Preparing NAS directory..."
ssh ${NAS_USER}@${NAS_HOST} "mkdir -p ${NAS_PATH}/data"

# Package and send (SCP fails on this NAS, use tar pipe)
echo "[3/4] Deploying code to NAS..."
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
    | ssh ${NAS_USER}@${NAS_HOST} "cd ${NAS_PATH} && tar xzf -"

# Build and start container
echo "[4/4] Building and starting container..."
ssh ${NAS_USER}@${NAS_HOST} "cd ${NAS_PATH} && docker compose up -d --build"

echo ""
echo "=== Deployed! ==="
echo "API:  http://${NAS_HOST}:8200/"
echo "Docs: http://${NAS_HOST}:8200/docs"
echo "Container: ${CONTAINER}"
