from __future__ import annotations

from redis import Redis
from rq import Connection, Worker

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    connection = Redis.from_url(settings.redis_url, decode_responses=True)
    with Connection(connection):
        worker = Worker([settings.redis_queue_name])
        worker.work(logging_level="INFO")


if __name__ == "__main__":
    main()
