"""Shared helper for authenticating module-level TestClients.

The auth gate (app/main.py middleware) protects every non-public route, so
test modules that hit those routes stamp a valid Bearer token onto their
client once at import time.
"""

import uuid

from fastapi.testclient import TestClient


def ensure_authenticated(client: TestClient) -> str:
    """Sign up a fresh QA account (or log in if it already exists) and set the
    client's Authorization header so every subsequent request passes the gate.
    Returns the account email used."""
    email = f"qa-{uuid.uuid4().hex[:10]}@signalsentry.test"
    password = "QAPassword123!"
    payload = {
        "company_name": "QA Coverage Co",
        "full_name": "QA Runner",
        "email": email,
        "password": password,
    }
    response = client.post("/auth/signup", json=payload)
    if response.status_code == 409:
        response = client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
    response.raise_for_status()
    client.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return email
