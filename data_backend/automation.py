import json
import mimetypes
import os
import re
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage

from .storage import MetadataStore
from .secrets_crypto import decrypt_text


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def parse_recipients(raw: str) -> list[str]:
    seen = set()
    out = []
    parts = re.split(r"[,\n;\t]+", raw or "")
    for part in parts:
        email = part.strip().lower()
        if not email or "@" not in email or email in seen:
            continue
        seen.add(email)
        out.append(email)
    return out


def _resolve_sender_config(store: MetadataStore, sender_email: str) -> dict:
    profile = store.get_automation_sender(sender_email)
    if profile:
        return {
            "host": profile["smtp_host"],
            "port": int(profile["smtp_port"]),
            "username": (profile["smtp_username"] or "").strip(),
            "password": (decrypt_text(profile["password_ciphertext"], profile["password_salt"]) or "").strip().replace(" ", ""),
            "sender": (profile["smtp_from_email"] or "").strip(),
            "use_tls": bool(profile["use_tls"]),
        }

    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip() or username
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false"
    if not host or not username or not password or not sender:
        raise RuntimeError(
            "No sender setup found. Configure sender in Automation page (recommended) or set SMTP env fallback."
        )
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "sender": sender,
        "use_tls": use_tls,
    }


def send_email(
    store: MetadataStore,
    sender_email: str,
    recipients: list[str],
    subject: str,
    body: str,
    attachment_paths: list[str] | None = None,
):
    cfg = _resolve_sender_config(store, sender_email)

    msg = EmailMessage()
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    for p in (attachment_paths or []):
        try:
            mime = mimetypes.guess_type(p)[0] or "application/octet-stream"
            maintype, subtype = mime.split("/", 1)
            with open(p, "rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=os.path.basename(p),
                )
        except Exception:
            continue

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
        smtp.ehlo()
        if cfg["use_tls"]:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        smtp.login(cfg["username"], cfg["password"])
        smtp.send_message(msg)


def process_due_automation_jobs(store: MetadataStore, ingestor):
    now_iso = _utc_now_iso()
    due = store.list_due_automation_jobs(now_iso, limit=100)
    for job in due:
        job_id = job["id"]
        try:
            recipients = json.loads(job.get("recipients_json") or "[]")
            if job.get("channel") != "email":
                raise RuntimeError(f"Unsupported channel: {job.get('channel')}")
            send_email(
                store,
                sender_email=job.get("created_by_email", ""),
                recipients=recipients,
                subject=job.get("subject", ""),
                body=job.get("message", ""),
                attachment_paths=json.loads(job.get("attachments_json") or "[]"),
            )
            sent_at = _utc_now_iso()
            store.update_automation_job_status(job_id, "sent", sent_at=sent_at, error_text=None)
            store.add_automation_event(
                {
                    "id": str(uuid.uuid4()),
                    "job_id": job_id,
                    "event_type": "sent",
                    "details_json": json.dumps({"recipients": recipients, "channel": "email"}),
                    "created_at": sent_at,
                }
            )
            ingestor.ingest_text(
                text=(
                    f"AUTOMATION SENT | job_id={job_id} | channel=email | to={','.join(recipients)} | "
                    f"subject={job.get('subject', '')} | scheduled={job.get('schedule_at', '')} | sent_at={sent_at}"
                ),
                title=f"automation_sent_{job_id}",
            )
        except Exception as e:
            err = str(e)[:1500]
            store.update_automation_job_status(job_id, "failed", error_text=err)
            store.add_automation_event(
                {
                    "id": str(uuid.uuid4()),
                    "job_id": job_id,
                    "event_type": "failed",
                    "details_json": json.dumps({"error": err}),
                    "created_at": _utc_now_iso(),
                }
            )
