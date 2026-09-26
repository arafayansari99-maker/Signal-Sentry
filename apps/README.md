# Production split layout

This repository is structured to support a cleaner production architecture: separate frontend and API applications, each with its own runtime, dependency graph, and deployment target.

## Recommended layout

```text
apps/
  api/
    app/
    requirements.txt
    .env.example
    Dockerfile
    README.md
  web/
    app/
    package.json
    .env.example
    Dockerfile
    README.md
```

## Why this is the cleanest production pattern

- Frontend and API can scale independently.
- Deployment boundaries are clearer for Vercel, Render, Railway, or Docker hosts.
- API credentials and CORS config stay isolated from the frontend build.
- Background jobs, monitoring workers, and database access remain in the backend service.
- The public marketing and dashboard UI can live in a static or SSR frontend without coupling to the FastAPI backend.

## Recommended runtime split

- API: FastAPI service for business logic, monitoring endpoints, DB access, queue integration, and exports.
- Frontend: a dedicated React/Next.js frontend that consumes API endpoints from a separate domain or origin.

## Current repo status

The split is now active for local development:

- `apps/web` serves the landing page and dashboard on port 3000.
- The existing FastAPI app serves the API on port 8001.
- Dashboard metrics, competitors, digests, monitoring cycles, and exports are loaded through the API.

The legacy Jinja routes remain available as a backend compatibility fallback, but the primary user experience is now the separate frontend.

## Migration plan

1. Keep the current FastAPI app as the source for the backend logic.
2. Keep database and queue orchestration in the API service.
3. Use the dedicated frontend app under `apps/web`.
4. Keep dashboard interactions and exports API-driven.
5. Set `NEXT_PUBLIC_API_URL` in the frontend environment.
6. Deploy the frontend and backend to separate hosts.

## Environment variables

### API

```env
ENVIRONMENT=production
DATABASE_URL=postgresql://user:password@host:5432/app_db
REDIS_URL=redis://host:6379/0
APP_NAME=Signal-Sentry
BACKEND_CORS_ORIGINS=https://your-frontend-domain.com
```

### Frontend

```env
NEXT_PUBLIC_API_URL=https://api.your-domain.com
NEXT_PUBLIC_APP_NAME=Signal-Sentry
```

## Suggested production hosting

- API: Render, Railway, Fly.io, AWS ECS, or Azure App Service
- Frontend: Vercel, Netlify, or Cloudflare Pages
- Database: managed PostgreSQL
- Queue/cache: managed Redis

This keeps the platform simple, fast, and easy to operate without mixing UI rendering and API execution in the same process.
