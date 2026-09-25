from __future__ import annotations

from email.message import EmailMessage
import smtplib
from typing import Any

from app.config import get_settings


def compose_alert_message(competitor_name: str, category: str, summary: str) -> str:
    settings = get_settings()
    header = f"[{settings.environment.upper()}] SignalSentry alert"
    return (
        f"{header}\n"
        f"Competitor: {competitor_name}\n"
        f"Category: {category}\n"
        f"Summary: {summary}\n"
        "\n"
        "This change was detected by the competitive monitoring pipeline."
    )


def send_email_alert(to_address: str, competitor_name: str, category: str, summary: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.smtp_host or not to_address:
        return {"status": "skipped", "reason": "smtp disabled or recipient missing"}

    return _send_email_message(
        to_address=to_address,
        subject=f"SignalSentry alert: {competitor_name} ({category})",
        body=compose_alert_message(competitor_name, category, summary),
    )


def _send_email_message(*, to_address: str, subject: str, body: str) -> dict[str, Any]:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or "signalsentry@local.dev"
    msg["To"] = to_address
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 25, timeout=10) as smtp:
        if settings.smtp_user and settings.smtp_password:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    return {"status": "sent", "recipient": to_address}


def send_slack_alert(webhook_url: str, competitor_name: str, category: str, summary: str) -> dict[str, Any]:
    if not webhook_url:
        return {"status": "skipped", "reason": "webhook missing"}

    import httpx

    payload = {
        "text": compose_alert_message(competitor_name, category, summary),
    }
    response = httpx.post(webhook_url, json=payload, timeout=10)
    response.raise_for_status()
    return {"status": "sent", "provider": "slack"}
