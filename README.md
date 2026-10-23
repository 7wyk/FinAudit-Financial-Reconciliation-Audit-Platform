# FinAudit — Financial Reconciliation & Audit Platform

Enterprise-style financial reconciliation and audit platform for comparing financial records from ERP/accounting systems and bank statements.

## Architecture

```
FinAudit/
├── backend/            # Django + DRF API
│   ├── apps/           # Django applications
│   │   └── common/     # Shared utilities, base models
│   ├── config/         # Django settings, URLs, Celery
│   ├── conftest.py     # Shared pytest fixtures
│   ├── manage.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/           # React + Vite + TypeScript
│   ├── src/
│   │   ├── api/        # Axios API client
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── vite.config.ts
│   ├── Dockerfile
│   └── .env.example
├── docker-compose.yml
├── PROJECT_SPEC.md
└── .gitignore
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16+
- Redis 7+
- Docker & Docker Compose (optional)

### Option 1: Docker Compose (recommended)

```bash
# Copy environment files
cp backend/.env.example backend/.env

# Start all services
docker compose up -d

# Run migrations
docker compose exec backend python manage.py migrate

# Access
# Backend API: http://localhost:8000
# Frontend:    http://localhost:5173 (run separately, see below)
```

### Option 2: Local Development

**Backend:**

```bash
cd backend
python --version  # Python 3.12 required
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
cp .env.example .env          # Edit DB credentials as needed

python manage.py migrate
python manage.py runserver
```

**Frontend:**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Running Tests

```bash
cd backend
pytest
```

If the local `.venv` references a removed interpreter, remove that local
environment and recreate it with Python 3.12 before installing requirements.

### API Endpoints

| Endpoint         | Description      |
|------------------|------------------|
| `GET /api/health/` | Health check   |
| `GET /api/v1/...`  | API v1 routes (Phase 2+) |

## Technology Stack

| Layer     | Technology                          |
|-----------|-------------------------------------|
| Backend   | Django, Django REST Framework, Celery |
| Frontend  | React, Vite, TypeScript, Tailwind CSS |
| Database  | PostgreSQL (Supabase in production) |
| Cache     | Redis (Upstash in production)       |
| Auth      | JWT (simplejwt)                     |
| Testing   | pytest, pytest-django               |
| Deploy    | Render (API), Vercel (frontend)     |

## Development Phases

1. **Foundation** — Project structure, configuration, Docker ✅
2. **Identity + Ingestion** — Auth, RBAC, file upload, import pipeline
3. **Reconciliation Core** — Matching engine, scoring, state management
4. **Enterprise Workflow** — Review, approvals, audit trail, reports
5. **Frontend + AI** — React UI screens, AI investigation assistant
6. **Production** — Security review, deployment, CI/CD
