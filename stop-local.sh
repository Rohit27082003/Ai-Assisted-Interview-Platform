#!/bin/bash

# AI-Assisted Interview Platform - Local Development Stop Script
# This script stops all running services

set -e

echo "🛑 Stopping AI-Assisted Interview Platform (Local Development Mode)"
echo "===================================================================="

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Stop Docker containers
echo -e "\n${YELLOW}Stopping Docker containers (PostgreSQL & Redis)...${NC}"
docker-compose -f docker-compose.dev.yml down

# Kill backend process (uvicorn)
echo -e "${YELLOW}Stopping backend server...${NC}"
pkill -f "uvicorn app.main:app" || echo -e "${RED}No backend process found${NC}"

# Kill frontend process (vite)
echo -e "${YELLOW}Stopping frontend server...${NC}"
pkill -f "vite" || echo -e "${RED}No frontend process found${NC}"

echo -e "\n${GREEN}✓ All services stopped successfully!${NC}"
echo "===================================================================="
