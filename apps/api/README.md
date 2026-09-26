# API service

This directory represents the production API service for the competitive intelligence platform.

## Responsibilities

- FastAPI app and endpoints
- database access
- authentication and authorization if added later
- business logic and monitoring workflows
- queue workers and scheduler orchestration
- export and digest endpoints

## Recommended structure

```text
apps/api/
  app/
    main.py
    config.py
    db.py
    models.py
    schemas.py
    services/
    workers/
  requirements.txt
  .env.example
  Dockerfile
```

## Dev command

```bash
cd apps/api
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Production notes

- Keep this service focused on API execution only.
- Do not include Jinja templates or frontend assets here.
- Use external Postgres and Redis services.
- Enable CORS only for the frontend domain(s).
