# 🚀 Running the Project Locally

This guide shows you how to run the AI-Assisted Interview Platform locally without containerizing the backend and frontend. Only PostgreSQL and Redis run in Docker containers.

## Prerequisites

- Docker Desktop installed and running
- Python 3.9+ installed
- Node.js 18+ and npm installed
- macOS/Linux environment

## Quick Start

### Option 1: Using the Start Script (Recommended)

```bash
./start-local.sh
```

This will:
1. Start PostgreSQL and Redis in Docker
2. Create Python virtual environment (if needed)
3. Install backend dependencies
4. Start the FastAPI backend on port 8000
5. Install frontend dependencies (if needed)
6. Start the React frontend on port 5173

### Option 2: Manual Setup

#### Step 1: Start Infrastructure (PostgreSQL & Redis)

```bash
docker-compose -f docker-compose.dev.yml up -d
```

Check that containers are running:
```bash
docker ps
```

You should see `interview-postgres` and `interview-redis` containers.

#### Step 2: Start the Backend

```bash
cd backend

# Create virtual environment (first time only)
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip (recommended)
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend will be available at:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

#### Step 3: Start the Frontend (New Terminal)

```bash
cd frontend

# Install dependencies (first time only)
npm install

# Start development server
npm run dev
```

The frontend will be available at http://localhost:5173

## Stopping Services

### Option 1: Using the Stop Script

```bash
./stop-local.sh
```

### Option 2: Manual Stop

1. Stop backend: `Ctrl+C` in the backend terminal
2. Stop frontend: `Ctrl+C` in the frontend terminal
3. Stop Docker containers:
   ```bash
   docker-compose -f docker-compose.dev.yml down
   ```

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | React application |
| Backend API | http://localhost:8000 | FastAPI server |
| API Docs (Swagger) | http://localhost:8000/docs | Interactive API documentation |
| API Docs (ReDoc) | http://localhost:8000/redoc | Alternative API documentation |
| PostgreSQL | localhost:5432 | Database (in Docker) |
| Redis | localhost:6379 | Cache/Queue (in Docker) |

## Environment Configuration

Make sure you have a `.env` file in the root directory with the required environment variables. You can copy from `.env.example`:

```bash
cp .env.example .env
```

Then edit `.env` and add your actual API keys and credentials:
- `GROQ_API_KEY` - Your Groq API key
- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` - AWS credentials
- Other configuration as needed

## Troubleshooting

### Backend won't start - pip install fails

If you get dependency conflicts, try:
```bash
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

### PostgreSQL connection error

Make sure Docker containers are running:
```bash
docker-compose -f docker-compose.dev.yml up -d
```

Wait a few seconds for PostgreSQL to initialize completely.

### Frontend build errors

Clear node_modules and reinstall:
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Port already in use

If ports 5432, 6379, 8000, or 5173 are already in use:
1. Stop the conflicting service
2. Or modify the port in `docker-compose.dev.yml` or the application config

## Development Workflow

1. Make code changes in `backend/` or `frontend/src/`
2. Changes auto-reload (both backend and frontend have hot-reload enabled)
3. View backend logs in the terminal running uvicorn
4. View frontend logs in the terminal running npm dev

## Database Migrations

If you need to run database migrations:

```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

## Viewing Logs

### Docker Container Logs
```bash
# PostgreSQL
docker logs interview-postgres

# Redis
docker logs interview-redis

# All infrastructure logs
docker-compose -f docker-compose.dev.yml logs -f
```

### Application Logs
Backend and frontend logs are shown in their respective terminal windows.
