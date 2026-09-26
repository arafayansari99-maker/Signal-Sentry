# Vercel deployment guide

Signal-Sentry deploys as two separate Vercel projects:

- **API project:** repository root, using `api/index.py` and `vercel.json`
- **Frontend project:** `apps/web`, using Next.js

Use a managed PostgreSQL database and managed Redis in production. Vercel functions are ephemeral, so SQLite files and long-running schedulers are not production-safe.

## 1. Provision production services

Create these before deploying:

- Managed PostgreSQL database
- Managed Redis instance
- Optional SMTP, Slack, and Sentry services

Keep the database and Redis connection strings private. Do not commit them to Git.

## 2. Deploy the API project

In Vercel, choose **Add New Project** and import the GitHub repository.

Use these project settings:

- **Project name:** `signal-sentry-api`
- **Root directory:** repository root (`.`)
- **Framework preset:** Other
- **Build command:** leave empty
- **Install command:** `pip install -r requirements.txt`
- **Output directory:** leave empty

The existing [vercel.json](vercel.json) routes requests to [api/index.py](api/index.py), which imports the FastAPI app.

Add these environment variables for Production:

```env
APP_NAME=competitive-intelligence-agent
ENVIRONMENT=production
VERCEL=1
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
REDIS_QUEUE_NAME=monitoring
BACKGROUND_QUEUE_ENABLED=false
ALLOWED_ORIGINS=https://your-frontend.vercel.app
```

Add optional integrations only when configured:

```env
SENTRY_DSN=
LLM_API_KEY=
LLM_MODEL=claude-3-5-sonnet
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
ALERT_EMAIL_TO=
SLACK_WEBHOOK_URL=
```

Deploy, then verify:

```text
https://your-api-domain.vercel.app/health
https://your-api-domain.vercel.app/docs
https://your-api-domain.vercel.app/metrics/overview
```

The health endpoint should return a JSON object with `status: ok`.

## 3. Deploy the frontend project

Create a second Vercel project from the same GitHub repository.

Use these project settings:

- **Project name:** `signal-sentry-web`
- **Root directory:** `apps/web`
- **Framework preset:** Next.js
- **Build command:** `npm run build`
- **Install command:** `npm install`
- **Output directory:** leave empty

Set this Production environment variable:

```env
NEXT_PUBLIC_API_URL=https://your-api-domain.vercel.app
```

Deploy and open:

```text
https://your-frontend.vercel.app/
https://your-frontend.vercel.app/dashboard
```

The frontend pages load the monolith-compatible landing and dashboard screens from the API URL, so the existing animations, menu behavior, dashboard actions, queue monitor, evidence panel, and exports remain available.

## 4. Configure CORS after the frontend URL exists

Update the API project's `ALLOWED_ORIGINS` value to the exact frontend origin:

```env
ALLOWED_ORIGINS=https://your-frontend.vercel.app
```

For a custom domain, use the custom domain instead. Multiple origins are comma-separated:

```env
ALLOWED_ORIGINS=https://app.example.com,https://preview.example.com
```

Redeploy the API after changing environment variables.

## 5. Database and worker requirements

Run migrations or schema initialization against PostgreSQL before using production data. Do not depend on a local SQLite file.

Keep `BACKGROUND_QUEUE_ENABLED=false` in the Vercel API project. Move scheduled monitoring and queue workers to a persistent service such as Railway, Render, Fly.io, or a container host. The worker should use the same `DATABASE_URL` and `REDIS_URL` as the API.

A typical worker command is:

```bash
python -m app.workers.queue_worker
```

Use an external cron or persistent scheduler to trigger monitoring work. Do not rely on FastAPI startup to run a permanent scheduler inside a Vercel function.

## 6. Production smoke test

Run these checks after both deployments:

```text
GET https://your-api-domain.vercel.app/health
GET https://your-api-domain.vercel.app/metrics/overview
GET https://your-api-domain.vercel.app/competitors
GET https://your-api-domain.vercel.app/export/competitors
GET https://your-frontend.vercel.app/
GET https://your-frontend.vercel.app/dashboard
```

Then verify in the browser:

- Dashboard metrics load without CORS errors.
- Mobile navigation opens and closes correctly.
- Add competitor uses the API.
- Monitoring cycle and digest actions return status feedback.
- Competitor and digest exports download successfully.

## 7. Preview deployments

Preview deployments use a different frontend URL. Add the preview origin to the API's `ALLOWED_ORIGINS` if preview testing needs cross-origin API access. For a larger team, use a stable custom frontend domain to avoid changing CORS for every preview.

## Troubleshooting

### API returns 500 during import

Check that `DATABASE_URL` is set to PostgreSQL and that all dependencies from `requirements.txt` are installed. Review Vercel function logs.

### Browser reports CORS errors

Check that `ALLOWED_ORIGINS` exactly matches the frontend origin, including `https://` and without a trailing slash.

### API works locally but not in production

Verify PostgreSQL and Redis are reachable from the deployed function, and confirm no production setting points to a local hostname or SQLite file.

### Monitoring jobs do not run

This is expected when `BACKGROUND_QUEUE_ENABLED=false`. Deploy the queue worker separately and trigger it with an external scheduler.
