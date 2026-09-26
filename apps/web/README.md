# Frontend service

This directory represents the production web frontend for the Signal-Sentry product.

## Responsibilities

- public landing page
- authenticated or dashboard shell if needed later
- API consumption from backend endpoints
- UI state and client-side interactions
- export calls and dashboard data fetches

## Recommended stack

Use a modern frontend framework such as:

- Next.js
- Vite + React
- Astro + React

## Suggested structure

```text
apps/web/
  app/
    page.tsx
    layout.tsx
    globals.css
  components/
  lib/
  public/
  package.json
  .env.example
  Dockerfile
```

## Example env

```env
NEXT_PUBLIC_API_URL=https://api.your-domain.com
NEXT_PUBLIC_APP_NAME=Signal-Sentry
```

## Production notes

- Keep this app purely presentation and UX.
- Consume the API over HTTP rather than importing Python modules.
- Use environment variables for API host configuration.
- Keep all business logic in the backend API service.

## Vercel deployment

Deploy this directory as its own Vercel project:

- Root directory: `apps/web`
- Framework: Next.js
- Build command: `npm run build`
- Install command: `npm install`
- Environment variable: `NEXT_PUBLIC_API_URL=https://your-api-domain.vercel.app`

The API is deployed separately from the repository root. See [../../VERCEL_DEPLOYMENT.md](../../VERCEL_DEPLOYMENT.md) for the complete production guide.
