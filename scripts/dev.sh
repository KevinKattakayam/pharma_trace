#!/bin/bash
# PharmaTrace Local Development Setup
# Starts both backend and frontend dev servers

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PharmaTrace Local Development Server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Backend
echo ""
echo "🔧 Starting backend (FastAPI + Uvicorn)..."
cd "$BACKEND_DIR"

if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install -q -r requirements.txt
fi

echo "   Launching on http://0.0.0.0:8000"
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Frontend
echo ""
echo "🎨 Starting frontend (Vite + React)..."
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    echo "   Installing dependencies..."
    npm install -q
fi

echo "   Launching on http://localhost:5173"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Development servers running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Frontend:  http://localhost:5173"
echo "Backend:   http://localhost:8000"
echo "API Docs:  http://localhost:8000/api/docs"
echo ""
echo "Press Ctrl+C to stop both servers."
echo ""

wait
