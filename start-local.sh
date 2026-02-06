#!/bin/bash

# AI-Assisted Interview Platform - Local Development Start Script
# This script starts the infrastructure in Docker and the application locally

set -e

echo "🚀 Starting AI-Assisted Interview Platform (Local Development Mode)"
echo "=================================================================="

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Start Docker containers (PostgreSQL and Redis)
echo -e "\n${BLUE}Step 1: Starting infrastructure (PostgreSQL & Redis) in Docker...${NC}"
docker-compose -f docker-compose.dev.yml up -d

# Wait for databases to be ready
echo -e "${YELLOW}Waiting for PostgreSQL and Redis to be ready...${NC}"
sleep 5

# Step 2: Start Backend
echo -e "\n${BLUE}Step 2: Starting Backend (FastAPI)...${NC}"
echo -e "${YELLOW}Backend will run on http://localhost:8000${NC}"
cd backend

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment and install dependencies
source venv/bin/activate
echo -e "${YELLOW}Installing Python dependencies...${NC}"
pip install -r requirements.txt > /dev/null 2>&1

# Start backend in background
echo -e "${GREEN}✓ Starting backend server...${NC}"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Step 3: Start Frontend
echo -e "\n${BLUE}Step 3: Starting Frontend (React + Vite)...${NC}"
echo -e "${YELLOW}Frontend will run on http://localhost:5173${NC}"
cd frontend

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing Node dependencies...${NC}"
    npm install
fi

# Start frontend in background
echo -e "${GREEN}✓ Starting frontend server...${NC}"
npm run dev &
FRONTEND_PID=$!
cd ..

# Summary
echo -e "\n${GREEN}=================================================================="
echo -e "✓ All services started successfully!${NC}"
echo -e "\n${BLUE}Services:${NC}"
echo -e "  • PostgreSQL:  ${GREEN}localhost:5432${NC}"
echo -e "  • Redis:       ${GREEN}localhost:6379${NC}"
echo -e "  • Backend API: ${GREEN}http://localhost:8000${NC}"
echo -e "  • Frontend:    ${GREEN}http://localhost:5173${NC}"
echo -e "\n${BLUE}API Documentation:${NC}"
echo -e "  • Swagger UI:  ${GREEN}http://localhost:8000/docs${NC}"
echo -e "  • ReDoc:       ${GREEN}http://localhost:8000/redoc${NC}"
echo -e "\n${YELLOW}Process IDs:${NC}"
echo -e "  • Backend PID:  ${BACKEND_PID}"
echo -e "  • Frontend PID: ${FRONTEND_PID}"
echo -e "\n${YELLOW}To stop all services, run:${NC} ./stop-local.sh"
echo -e "${YELLOW}Or manually stop infrastructure:${NC} docker-compose -f docker-compose.dev.yml down"
echo -e "=================================================================="

# Keep script running
wait
