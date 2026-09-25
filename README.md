# Signal-Sentry

Signal-Sentry is a competitive intelligence monitoring platform that helps teams track competitor pricing, product positioning, and public website changes in near real time.

It continuously watches competitor pages, captures content snapshots, identifies important changes, and turns them into clear alerts and digests for sales, product, and growth teams.

## Why this project exists

Most competitive monitoring is still manual and reactive. Signal-Sentry automates the monitoring loop so teams can spot:

- pricing changes
- feature or copy updates
- new product pages or positioning shifts
- hiring and hiring-page updates
- market signals that may impact revenue or strategy

## Core features

- competitor and URL tracking
- URL discovery for pricing, product, and careers pages
- page snapshot capture and history tracking
- change detection and materiality scoring
- digest generation for alerts and summaries
- email and Slack-ready alerting hooks
- queue-based background job execution for scheduled monitoring
- dashboard for live status and competitor monitoring

## Tech stack

- Python 3.12
- FastAPI
- SQLAlchemy
- SQLite for local development
- PostgreSQL-ready production configuration
- APScheduler and Redis/RQ-friendly background workers
- BeautifulSoup and scraping helpers for page extraction
- Docker Compose for local and deployment simulation

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
  templates/
  workers/

tests/
  test_api.py
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

Copy the example environment file and fill in your secrets locally. Do not commit your actual `.env` file.

```bash
copy .env.example .env
```

Example values include:

- app environment settings
- database connection URL
- Redis URL
- SMTP credentials
- Slack webhook URL

## Running background jobs

The project includes a queue-backed monitoring flow for scheduled checks.

```bash
python -m app.workers.queue_worker
```

## Docker deployment

```bash
docker compose up --build
```

This starts the API service, worker, database, and Redis in a mock production-style stack.

## Monitoring flow

```text
discovery → scrape → snapshot → diff → classify → alert → digest
```

## Security note

This repository intentionally excludes secrets and local environment files. Only `.env.example` is included as a template.

## License

This project is currently provided as a demo and internal prototype for competitive intelligence workflows.

## Contributing

Pull requests are welcome for:

- better competitor discovery heuristics
- smarter diffing logic
- richer digest summaries
- queue and deployment improvements
- UI and dashboard enhancements
