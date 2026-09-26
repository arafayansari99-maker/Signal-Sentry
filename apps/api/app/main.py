from fastapi import FastAPI

app = FastAPI(title="Signal-Sentry API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api")
def root() -> dict[str, str]:
    return {"message": "Signal-Sentry API is running."}
