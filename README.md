# Signal-Sentry

Signal-Sentry is an open competitive intelligence dashboard for tracking competitor pricing, product changes, and market signals in one place.

The app combines a public landing page, a live dashboard, and background monitoring workflows to surface important changes across competitor websites without requiring a company-auth flow.

## What this project does

Signal-Sentry helps teams monitor:

- pricing and promotion changes
- product and positioning updates
- hiring-page and company signal changes
- market activity that may affect revenue or strategy
- digest summaries and exportable insight reports

## Core features

- public landing page and marketing shell
- live dashboard overview with monitoring metrics
- competitor and page tracking
- snapshot capture and historical comparisons
- diffing and signal classification
- digest generation and export endpoints
- Redis/RQ-backed queue execution for monitoring jobs
- scheduler-driven background processes
- Docker-ready local stack for development and demo use

## Tech stack

- Python 3.12
- FastAPI
- Jinja2 templates
- SQLAlchemy
- SQLite for local development
- PostgreSQL-ready configuration
- APScheduler + Redis + RQ for background jobs
- BeautifulSoup and Playwright for web monitoring
- Docker Compose for local deployment

## Project structure

```text
app/
  config.py
  db.py
  main.py
  models.py
  queue.py
  schemas.py
  services/
  static/
  templates/
  workers/

scripts/
  seed_demo_data.py

tests/
  test_api.py
  test_digests.py
  test_metrics.py
  test_scheduler_job.py
  test_seed_script.py
  test_smoke.py

Dockerfile
docker-compose.yml
requirements.txt
README.md
.env.example
```

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Then open:

- http://localhost:8001/
- http://localhost:8001/dashboard
- http://localhost:8001/docs

## Configuration

Copy the example environment file and populate the local settings you need for monitoring and queue execution.

```bash
copy .env.example .env
```

Typical values include:

- app environment name and mode
- database URL
- Redis URL
- monitoring queue settings
- optional SMTP or Slack hooks

## Running background jobs

```bash
python -m app.workers.queue_worker
```

## Demo data

Reset the local database with realistic sample monitoring data:

```bash
python -m scripts.seed_demo_data
```

`--keep-existing` can be added to preserve current rows while filling missing demo data.

## Docker deployment

```bash
docker compose up --build
```

This starts the app, worker processes, database, and queue services for a mock production-like environment.

## Monitoring flow

```text
discovery → scrape → snapshot → diff → classify → alert → digest
```

## Security note

This repository intentionally excludes real secrets and local environment files. Only `.env.example` is included as a template.

## License

This project is provided as an internal prototype and demo for competitive intelligence workflows.

## Contributing

Contributions are welcome for:

- better discovery heuristics
- stronger diffing logic
- richer digest summaries
- queue and scheduling improvements
- dashboard and UX polish
