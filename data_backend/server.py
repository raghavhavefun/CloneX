import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:
    requests = None
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    def load_dotenv(*args, **kwargs):
        return False
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from modules.memory_retriever import MemoryRetriever
from modules.audio_capture import AudioCapture
from modules.platform_adapter import audio_device_priority, chrome_user_data_root
from config import MEMORY_DIR

from .ingest import IngestionService
from .automation import parse_recipients, process_due_automation_jobs
from .secrets_crypto import encrypt_text
from .settings import load_settings
from .storage import MetadataStore

load_dotenv()
settings = load_settings()
store = MetadataStore(settings.sqlite_path)
ingestor = IngestionService(settings, store)
retriever = MemoryRetriever(top_k=10)
AUTH_REQUIRE_BEARER = os.getenv("AUTH_REQUIRE_BEARER", "false").strip().lower() in {"1", "true", "yes"}
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
LOS_GROQ_MODEL = os.getenv("LOS_GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
AUTOMATION_GROQ_MODEL = os.getenv("AUTOMATION_GROQ_MODEL", LOS_GROQ_MODEL).strip() or LOS_GROQ_MODEL

app = FastAPI(title="Project Aria Data Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_DATA_UPLOAD_FILE_BYTES = 25 * 1024 * 1024  # 25 MB per file
MAX_DATA_UPLOAD_TOTAL_BYTES = 80 * 1024 * 1024  # 80 MB per request


class LinkPayload(BaseModel):
    url: str

class TextPayload(BaseModel):
    text: str
    title: str | None = None

class LosNotePayload(BaseModel):
    text: str
    source_mode: str = "typed"

class LosAgentChatPayload(BaseModel):
    agent_name: str
    message: str
    source_mode: str = "typed"
    autonomy_mode: str = "suggest_actions"


class AutomationCreatePayload(BaseModel):
    requester_email: str
    recipients: str | None = None
    instruction: str | None = None
    mode: str = "ai_schedule"
    subject: str | None = None
    message: str | None = None
    bulk_mode: str = "same_for_all"
    recipient_entries: list[dict[str, str]] | None = None
    shared_attachment_paths: list[str] | None = None
    schedule_at: str | None = None
    timezone: str = "UTC"


class MeetingQueryPayload(BaseModel):
    query: str


class AutomationSenderSetupPayload(BaseModel):
    email: str
    app_password: str
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_from_email: str | None = None
    use_tls: bool = True


class SessionStartPayload(BaseModel):
    meeting_url: str
    profile_email: str
    assistant_name: str = "Aria"
    avatar_mode: str = "3d"
    audio_device_id: int | None = None


class ContactPayload(BaseModel):
    name: str
    email: str


_session_proc: subprocess.Popen | None = None
_session_meta: dict[str, Any] = {"status": "idle"}
_session_lock = threading.Lock()
_session_logs: deque[str] = deque(maxlen=3000)
_session_log_lock = threading.Lock()
_audio_probe_disabled = False
_audio_probe_cache: dict[str, Any] | None = None
SKIP_BACKEND_AUDIO_PROBE = os.getenv("SKIP_BACKEND_AUDIO_PROBE", "true").strip().lower() in {"1", "true", "yes"}

LOS_AUTONOMY_MODES = {
    "suggest_actions": "Suggest actionable plans only. Do not execute actions.",
    "execute_with_approval": "Prepare executable actions, but ask for explicit approval before execution.",
    "autonomous_mode": "Execute allowed actions directly and report outcomes with audit details.",
}

_LOS_PENDING_EXECUTIONS: dict[tuple[str, str], dict[str, str]] = {}

LOS_AGENT_PERSONAS = {
    "command_agent": "You are the Command Agent. Interpret user goals, decompose requests into structured task plans, assign owners (agents), and produce a clear execution sequence.",
    "identity_agent": "You are the Identity Agent. Maintain user goals, behavior patterns, preferences, communication style, and priorities. Keep recommendations personalized and consistent.",
    "calendar_agent": "You are the Calendar Agent. Optimize meetings, focus blocks, scheduling, and availability. Identify low-value meetings and propose better time allocation.",
    "email_communication_agent": "You are the Email and Communication Agent. Handle drafting, prioritization, outreach, follow-ups, and tone strategy for professional communication.",
    "opportunity_agent": "You are the Opportunity Agent. Find and evaluate deals, leads, jobs, sponsorships, partnerships, clients, grants, and collaboration opportunities.",
    "finance_agent": "You are the Finance Agent. Analyze subscriptions, spending, waste, and financial inefficiencies. Recommend measurable savings opportunities.",
    "research_agent": "You are the Research Agent. Perform deep research, comparisons, summaries, market scans, and strategic recommendations with clear rationale.",
    "negotiation_agent": "You are the Negotiation Agent. Draft renegotiation strategy, contract negotiation language, and cost-reduction approaches.",
    "content_agent": "You are the Content Agent. Create posts, scripts, marketing copy, investor materials, landing page copy, newsletters, and social content.",
    "business_builder_agent": "You are the Business Builder Agent. Help launch offers, build funnels, create campaigns, and organize monetization operations.",
    "network_agent": "You are the Network Agent. Track relationships, introductions, strategic follow-ups, and contact opportunities with next-best-actions.",
    "execution_agent": "You are the Execution Agent. Translate approved plans into concrete execution steps via APIs, browser automation, workflows, and integrated tools.",
    "social_media_agent": "You are the Social Media Agent. Analyze social trends and the user's page strategy, suggest what to post, draft interactions, and propose automation safely.",
    "cofounder_agent": "You are the Cofounder Agent. Act as a strategic operating partner for business planning, prioritization, risk checks, and growth execution guidance.",
}


def _verified_email_from_bearer(authorization: str | None) -> str | None:
    auth = (authorization or "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    if requests is None:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {token}",
            },
            timeout=8,
        )
        if r.status_code >= 400:
            return None
        data = r.json() if r.content else {}
        email = str((data or {}).get("email", "")).strip().lower()
        return email if "@" in email else None
    except Exception:
        return None


def _owner_email(
    x_user_email: str | None = None,
    requester_email: str | None = None,
    authorization: str | None = None,
) -> str:
    verified = _verified_email_from_bearer(authorization)
    if verified:
        return verified
    if AUTH_REQUIRE_BEARER:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization bearer token")
    raw = (x_user_email or requester_email or "").strip().lower()
    if "@" in raw:
        return raw
    return "global"

def _los_client() -> Groq:
    key = os.getenv("LOS_GROQ_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=500, detail="LOS_GROQ_API_KEY is missing")
    return Groq(api_key=key)


def _append_session_log(line: str):
    txt = (line or "").replace("\x00", "")
    # Remove non-printable control chars that render as garbage symbols in UI logs.
    txt = "".join(ch if (ch == "\t" or ch == "\n" or 32 <= ord(ch) <= 126) else " " for ch in txt).rstrip()
    txt = " ".join(txt.split())
    if not txt:
        return
    with _session_log_lock:
        _session_logs.append(f"{datetime.utcnow().isoformat()} | {txt}")


def _spawn_session_log_reader(proc: subprocess.Popen):
    def _read_stream(stream):
        try:
            for raw in iter(stream.readline, ""):
                if raw is None:
                    break
                _append_session_log(raw)
        except Exception:
            pass

    if proc.stdout:
        threading.Thread(target=_read_stream, args=(proc.stdout,), daemon=True).start()
    if proc.stderr:
        threading.Thread(target=_read_stream, args=(proc.stderr,), daemon=True).start()


def _list_input_devices() -> list[tuple[int, str]]:
    global _audio_probe_disabled
    if _audio_probe_disabled:
        return []
    try:
        cap = AudioCapture()
    except Exception as e:
        _audio_probe_disabled = True
        _append_session_log(f"[Audio] Device probe disabled (init failure): {e}")
        return []
    try:
        try:
            return cap.list_devices()
        except Exception as e:
            _append_session_log(f"[Audio] Device enumeration failed: {e}")
            _audio_probe_disabled = True
            return []
    finally:
        try:
            cap.pa.terminate()
        except Exception:
            pass


def _auto_pick_vb_device() -> dict[str, Any]:
    global _audio_probe_cache
    os_name = platform.system().lower()
    if _audio_probe_cache is not None and (SKIP_BACKEND_AUDIO_PROBE or _audio_probe_disabled):
        return dict(_audio_probe_cache)
    if os.name == "nt" and SKIP_BACKEND_AUDIO_PROBE:
        devices = []
    else:
        devices = _list_input_devices()
    ranked = sorted(devices, key=lambda x: (audio_device_priority(x[1]), x[0]))
    selected = ranked[0] if ranked else None
    if os_name == "darwin":
        preferred_driver = "BlackHole"
        setup_steps = [
            "Install BlackHole (2ch or 16ch).",
            "Open Audio MIDI Setup and create a Multi-Output Device including your speakers and BlackHole.",
            "Set meeting app Speaker/Output to that Multi-Output Device.",
            "Keep meeting app Microphone/Input on your real microphone.",
            "Return here and run Validate Audio Flow before joining.",
        ]
    else:
        preferred_driver = "VB-CABLE"
        setup_steps = [
            "Install VB-CABLE and restart if prompted.",
            "Set meeting app Speaker/Output to CABLE Input (VB-Audio Virtual Cable).",
            "Keep meeting app Microphone/Input on your real microphone.",
            "Return here and run Validate Audio Flow before joining.",
        ]
    out = {
        "devices": [{"id": i, "name": n} for i, n in devices],
        "selected_device_id": selected[0] if selected else None,
        "selected_device_name": selected[1] if selected else None,
        "preferred_driver": preferred_driver,
        "setup_steps": setup_steps,
    }
    _audio_probe_cache = dict(out)
    return out


def _validate_audio_flow(device_id: int, seconds: float = 2.0) -> dict[str, Any]:
    import time as _time
    import audioop

    cap = AudioCapture(device_index=device_id)
    cap.start()
    deadline = _time.time() + max(1.0, min(seconds, 5.0))
    rms_values: list[float] = []
    chunks = 0
    try:
        while _time.time() < deadline:
            data = cap.get_chunk(timeout=0.35)
            if not data:
                continue
            try:
                rms = float(audioop.rms(data, 2))
            except Exception:
                rms = 0.0
            chunks += 1
            rms_values.append(rms)
    finally:
        try:
            cap.stop()
        except Exception:
            pass

    peak_rms = max(rms_values) if rms_values else 0.0
    avg_rms = (sum(rms_values) / len(rms_values)) if rms_values else 0.0
    flowing = peak_rms >= 120.0 and chunks >= 2
    return {
        "device_id": device_id,
        "chunks": chunks,
        "peak_rms": round(peak_rms, 2),
        "avg_rms": round(avg_rms, 2),
        "flowing": flowing,
        "hint": (
            "Audio signal detected."
            if flowing
            else "No strong audio signal detected. Check output routing to virtual device and try again while meeting audio is playing."
        ),
    }


def _automation_client() -> Groq:
    key = os.getenv("AUTOMATION_GROQ_API_KEY", "").strip() or os.getenv("LOS_GROQ_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=500, detail="AUTOMATION_GROQ_API_KEY (or LOS_GROQ_API_KEY) is missing")
    return Groq(api_key=key)


def _contacts_map(owner_email: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in store.list_contacts(owner_email):
        nm = str(c.get("name", "")).strip().lower()
        em = str(c.get("email", "")).strip().lower()
        if nm and em and "@" in em:
            out[nm] = em
    return out


def _extract_named_recipients(text: str, owner_email: str) -> list[str]:
    t = (text or "").strip().lower()
    if not t:
        return []
    direct = parse_recipients(text)
    if direct:
        return direct
    cmap = _contacts_map(owner_email)
    if not cmap:
        return []
    found: list[str] = []
    words = set(re.findall(r"[a-z0-9._-]+", t))
    for name, email in cmap.items():
        full_match = re.search(rf"\b{re.escape(name)}\b", t) is not None
        first = (name.split() or [""])[0].strip()
        token_match = bool(first and len(first) >= 3 and first in words)
        if full_match or token_match:
            found.append(email)
    seen = set()
    out = []
    for e in found:
        if e in seen:
            continue
        seen.add(e)
        out.append(e)
    return out


def _mentions_named_target_without_email(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if parse_recipients(t):
        return False
    if re.search(r"\b(?:to|email|mail)\s+(?:me|myself|my mail|my email)\b", t):
        return False
    return bool(re.search(r"\b(?:to|mail|email|send to)\s+[a-z][a-z0-9._ -]{1,40}\b", t))


def _explicit_self_target(text: str) -> bool:
    t = (text or "").strip().lower()
    if "remind me" in t:
        return True
    return bool(re.search(r"\b(?:to|email|mail)\s+(?:me|myself|my mail|my email)\b", t))


def _is_recent_duplicate_job(
    requester: str,
    recipient: str,
    subject_txt: str,
    message_txt: str,
    within_seconds: int = 120,
) -> bool:
    rows = store.list_automation_jobs(limit=200)
    now = datetime.utcnow()
    for r in rows:
        if str(r.get("created_by_email", "")).strip().lower() != requester:
            continue
        if str(r.get("subject", "")).strip() != subject_txt.strip():
            continue
        if str(r.get("message", "")).strip() != message_txt.strip():
            continue
        try:
            recs = json.loads(r.get("recipients_json") or "[]")
        except Exception:
            recs = []
        recs = [str(x).strip().lower() for x in (recs or [])]
        if recipient.strip().lower() not in recs:
            continue
        created = str(r.get("created_at", "")).strip()
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            continue
        if (now - dt).total_seconds() <= within_seconds:
            return True
    return False


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def _is_los_reminder_intent(text: str) -> bool:
    t = (text or "").lower()
    cues = [
        "remind me",
        "remind",
        "send an email",
        "send email",
        "schedule an email",
        "schedule email",
        "send mail",
        "email to",
        "email me",
        "mail me",
        "reminder",
        "ping me",
    ]
    return any(c in t for c in cues)


def _is_send_now_intent(text: str) -> bool:
    t = (text or "").lower()
    cues = ["send now", "right now", "immediately", "asap", "now"]
    return any(c in t for c in cues)


def _is_approval_text(text: str) -> bool:
    t = (text or "").strip().lower()
    approvals = {
        "approve",
        "approved",
        "go ahead",
        "go-ahead",
        "yes execute",
        "confirm execute",
        "proceed",
        "do it",
    }
    return t in approvals or any(a in t for a in approvals)


def _is_execution_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    cues = [
        "send",
        "schedule",
        "remind",
        "email",
        "book",
        "search",
        "open",
        "post",
        "publish",
        "apply",
        "reach out",
    ]
    return any(c in t for c in cues)


def _parse_los_schedule_local(text: str) -> tuple[datetime | None, str]:
    import re as _re
    now_local = datetime.now().astimezone()
    tz_name = str(now_local.tzinfo) or "UTC"
    t = (text or "").strip().lower()

    # Time parse: 12h ("7 pm", "7:30 pm") or 24h ("19:30")
    hour = None
    minute = 0
    m12 = _re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if m12:
        h = int(m12.group(1))
        minute = int(m12.group(2) or "0")
        ap = m12.group(3)
        if h == 12:
            h = 0
        hour = h + (12 if ap == "pm" else 0)
    else:
        m24 = _re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
        if m24:
            hour = int(m24.group(1))
            minute = int(m24.group(2))

    # Date parse: today/tomorrow/day-name/ISO or slash dates.
    target_date = None
    if "today" in t:
        target_date = now_local.date()
    elif "tomorrow" in t:
        from datetime import timedelta as _td
        target_date = (now_local + _td(days=1)).date()
    else:
        day_names = {
            "monday": 0, "mon": 0,
            "tuesday": 1, "tue": 1, "tues": 1,
            "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "thurs": 3,
            "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6,
        }
        found = None
        for dn, idx in sorted(day_names.items(), key=lambda x: len(x[0]), reverse=True):
            if _re.search(rf"\b{_re.escape(dn)}\b", t):
                found = idx
                break
        if found is not None:
            from datetime import timedelta as _td
            delta = (found - now_local.weekday()) % 7
            if delta == 0:
                delta = 7
            target_date = (now_local + _td(days=delta)).date()
        else:
            m_iso = _re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
            if m_iso:
                y, mo, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
                try:
                    from datetime import date as _date
                    target_date = _date(y, mo, d)
                except Exception:
                    target_date = None
            else:
                # Supports dd/mm/yyyy, mm/dd/yyyy, dd-mm-yyyy, mm-dd-yyyy, dd/mm, mm/dd.
                m_slash = _re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", t)
                if m_slash:
                    a, b = int(m_slash.group(1)), int(m_slash.group(2))
                    yraw = m_slash.group(3)
                    y = int(yraw) if yraw else now_local.year
                    if y < 100:
                        y += 2000
                    from datetime import date as _date
                    candidates = []
                    # dd/mm interpretation
                    try:
                        candidates.append(_date(y, b, a))
                    except Exception:
                        pass
                    # mm/dd interpretation
                    try:
                        d2 = _date(y, a, b)
                        if d2 not in candidates:
                            candidates.append(d2)
                    except Exception:
                        pass
                    if candidates:
                        # choose nearest non-past date; if all past, choose nearest and roll +1 year
                        future = [c for c in candidates if c >= now_local.date()]
                        if future:
                            target_date = sorted(future)[0]
                        else:
                            chosen = sorted(candidates)[0]
                            try:
                                target_date = chosen.replace(year=chosen.year + 1)
                            except Exception:
                                target_date = chosen

    # Must include at least a date cue to avoid accidental schedules.
    if target_date is None:
        return None, tz_name
    if hour is None:
        hour = 9
        minute = 0

    candidate = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        int(hour),
        int(minute),
        tzinfo=now_local.tzinfo,
    )
    # If user said "today" but time already passed, push by 1 day.
    if candidate <= now_local and "today" in t:
        from datetime import timedelta as _td
        candidate = candidate + _td(days=1)
    return candidate, tz_name


def _schedule_los_reminder_if_any(
    owner: str,
    text: str,
    source_mode: str,
) -> dict[str, Any] | None:
    if owner == "global" or "@" not in owner:
        return None
    if not _is_los_reminder_intent(text):
        return None

    local_dt, tz_name = _parse_los_schedule_local(text)
    now_local = datetime.now().astimezone()
    immediate = _is_send_now_intent(text)
    if local_dt is None and immediate:
        local_dt = now_local

    schedule_at_utc = local_dt.astimezone(timezone.utc).isoformat() if local_dt else None

    explicit_recipients = parse_recipients(text)
    named_recipients = _extract_named_recipients(text, owner) if not explicit_recipients else []
    if _explicit_self_target(text) or "remind me" in text.lower():
        recipients = [owner]
    else:
        recipients = explicit_recipients or named_recipients
        if not recipients and _mentions_named_target_without_email(text):
            return {
                "count": 0,
                "jobs": [],
                "timezone": tz_name,
                "schedule_at_utc": local_dt.astimezone(timezone.utc).isoformat() if local_dt else "",
                "error": "Recipient name not found in Connects. Add contact or provide explicit email.",
            }
        if not recipients:
            recipients = [owner]
    recipients = recipients[:12]
    subject = "Aria Reminder"
    message = (text or "").strip()[:12000]
    try:
        parsed = _parse_automation_instruction(text, owner)
        subject = str(parsed.get("subject", subject)).strip()[:300] or subject
        message = str(parsed.get("message", message)).strip()[:12000] or message
        if parsed.get("schedule_at_utc"):
            schedule_at_utc = parsed["schedule_at_utc"]
    except Exception:
        pass
        
    if schedule_at_utc is None and local_dt is None:
        return None
        
    now_iso = _utc_now_iso()
    jobs = []

    for recipient in recipients:
        job = {
            "id": str(uuid.uuid4()),
            "created_by_email": owner,
            "channel": "email",
            "recipients_json": json.dumps([recipient]),
            "subject": subject,
            "message": message,
            "schedule_at": schedule_at_utc,
            "timezone": tz_name[:64],
            "status": "scheduled",
            "source_prompt": f"LOS {source_mode} reminder: {text}",
            "attachments_json": "[]",
            "created_at": now_iso,
            "sent_at": None,
            "error_text": None,
        }
        store.add_automation_job(job)
        store.add_automation_event(
            {
                "id": str(uuid.uuid4()),
                "job_id": job["id"],
                "event_type": "scheduled",
                "details_json": json.dumps(
                    {"recipient": recipient, "schedule_at": schedule_at_utc, "from": "los_note"}
                ),
                "created_at": now_iso,
            }
        )
        jobs.append({"id": job["id"], "recipient": recipient, "schedule_at": schedule_at_utc})

    if immediate:
        try:
            process_due_automation_jobs(store, ingestor)
        except Exception:
            pass

    return {"count": len(jobs), "jobs": jobs, "timezone": tz_name, "schedule_at_utc": schedule_at_utc}


def _parse_iso_schedule(schedule_at: str) -> str:
    txt = (schedule_at or "").strip()
    if not txt:
        raise HTTPException(status_code=400, detail="schedule_at is required")
    try:
        dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid schedule_at ISO format: {e}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_automation_instruction(instruction: str, default_email: str) -> dict[str, Any]:
    now_iso = _utc_now_iso()
    client = _automation_client()
    completion = client.chat.completions.create(
        model=AUTOMATION_GROQ_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract automation email request into JSON with strict keys: "
                    "subject, message, recipients, schedule_at_utc, timezone. "
                    "recipients must be an array of emails. "
                    "If recipient not explicit, use default email. "
                    "schedule_at_utc must be ISO8601 UTC."
                ),
            },
            {
                "role": "user",
                "content": f"Default email: {default_email}\nNow UTC: {now_iso}\nInstruction: {instruction}",
            },
        ],
    )
    raw = json.loads(completion.choices[0].message.content or "{}")
    recipients = raw.get("recipients") or [default_email]
    if isinstance(recipients, str):
        recipients = [recipients]
    recipients = [r.strip().lower() for r in recipients if isinstance(r, str) and "@" in r]
    if not recipients:
        recipients = [default_email]

    schedule_utc = _parse_iso_schedule(str(raw.get("schedule_at_utc", "")))
    subject = str(raw.get("subject", "Aria Reminder")).strip() or "Aria Reminder"
    message = str(raw.get("message", instruction)).strip() or instruction
    timezone_name = str(raw.get("timezone", "UTC")).strip() or "UTC"
    return {
        "subject": subject[:300],
        "message": message[:12000],
        "recipients": recipients,
        "schedule_at_utc": schedule_utc,
        "timezone": timezone_name[:64],
    }


def _ai_group_messages(instruction: str, recipients: list[str], timezone_name: str) -> list[dict[str, str]]:
    client = _automation_client()
    completion = client.chat.completions.create(
        model=AUTOMATION_GROQ_MODEL,
        temperature=0.25,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Create per-recipient email plan in JSON key 'entries' as list of objects: "
                    "recipient, subject, message. You may group recipients by same message intent, "
                    "but still output one entry per recipient."
                ),
            },
            {
                "role": "user",
                "content": f"Timezone={timezone_name}\nRecipients={recipients}\nInstruction={instruction}",
            },
        ],
    )
    raw = json.loads(completion.choices[0].message.content or "{}")
    entries = raw.get("entries") or []
    out = []
    for e in entries:
        r = str(e.get("recipient", "")).strip().lower()
        s = str(e.get("subject", "")).strip()
        m = str(e.get("message", "")).strip()
        if "@" in r and s and m:
            out.append({"recipient": r, "subject": s[:300], "message": m[:12000]})
    return out

def _los_related_context(limit: int = 16, owner_email: str | None = None) -> str:
    items = store.list_assets(owner_email=owner_email)[:limit]
    if not items:
        return ""
    lines = []
    for i, item in enumerate(items, start=1):
        lines.append(
            f"[{i}] {item.get('source_type')} | {item.get('name')} | {item.get('status')} | {item.get('created_at')}"
        )
    return "\n".join(lines)


def _los_recent_notes_context(limit: int = 20, owner_email: str | None = None) -> str:
    items = store.list_los_items(owner_email=owner_email)[:limit]
    if not items:
        return ""
    lines = []
    for i, item in enumerate(items, start=1):
        lines.append(
            f"[{i}] {item.get('item_type')} | group={item.get('group_name')} | "
            f"title={item.get('title')} | {item.get('created_at')} | {item.get('content')}"
        )
    return "\n".join(lines)




def _meeting_dirs() -> list[Path]:
    root = Path(MEMORY_DIR)
    if not root.exists():
        return []
    dirs = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("meeting_")]
    dirs.sort(key=lambda p: p.name, reverse=True)
    return dirs


def _meeting_payload_from_dir(folder: Path) -> dict[str, Any]:
    notes = folder / "notes.json"
    summary = folder / "summary.md"
    transcript = folder / "transcript.txt"
    diar = folder / "diarization.json"
    item = {
        "id": folder.name,
        "path": str(folder),
        "has_summary": summary.exists(),
        "has_transcript": transcript.exists(),
        "has_diarization": diar.exists(),
        "created_at": datetime.fromtimestamp(folder.stat().st_mtime, tz=timezone.utc).isoformat(),
        "owner_email": None,
    }
    if notes.exists():
        try:
            data = json.loads(notes.read_text(encoding="utf-8"))
            item["url"] = data.get("url", "")
            item["owner_email"] = (data.get("owner_email") or "").strip().lower() or None
        except Exception:
            pass
    return item


def _meeting_text(folder: Path) -> str:
    parts = []
    for name in ["summary.md", "transcript.txt", "notes.json", "diarization.json", "speaker_transcript.txt"]:
        fp = folder / name
        if not fp.exists():
            continue
        try:
            parts.append(fp.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
    return "\n\n".join(parts)[:120000]

def _meeting_semantic_context(meeting_id: str, query: str, max_chunks: int = 24) -> tuple[str, str]:
    chunks: list[dict[str, Any]] = retriever.retrieve(query, top_k=max_chunks) or []
    if not chunks:
        return "", ""
    selected: list[str] = []
    global_lines: list[str] = []
    sel_key = (meeting_id or "").lower()
    for i, c in enumerate(chunks, start=1):
        name = str(c.get("name", ""))
        source_type = str(c.get("source_type", ""))
        txt = (c.get("text", "") or "").replace("\n", " ").strip()
        if not txt:
            continue
        line = f"[{i}] {source_type}:{name} -> {txt[:900]}"
        global_lines.append(line)
        if sel_key and sel_key in name.lower():
            selected.append(line)
    return "\n".join(selected), "\n".join(global_lines)

def _los_deep_knowledge_context(query: str, max_chunks: int = 20, owner_email: str | None = None) -> str:
    q = (query or "").strip()
    if not q:
        return ""
    chunks: list[dict[str, Any]] = retriever.retrieve(q, top_k=max_chunks, owner_email=owner_email) or []
    if not chunks:
        return ""
    lines: list[str] = []
    for i, c in enumerate(chunks, start=1):
        name = c.get("name", "")
        source_type = c.get("source_type", "")
        txt = (c.get("text", "") or "").replace("\n", " ").strip()
        if not txt:
            continue
        lines.append(f"[{i}] {source_type}:{name} -> {txt[:1200]}")
    return "\n".join(lines)


def _owner_slug(owner_email: str | None) -> str:
    import re as _re
    raw = (owner_email or "global").strip().lower()
    safe = _re.sub(r"[^a-z0-9._-]+", "_", raw)
    return safe or "global"


def _los_exact_asset_text_context(query: str, max_assets: int = 3, max_chars_per_asset: int = 12000, owner_email: str | None = None) -> str:
    """
    Force-include full extracted text for assets that match a filename hint in query.
    This prevents LOS from answering with metadata-only when detailed content exists.
    """
    q = (query or "").strip()
    if not q:
        return ""
    hints: list[str] = []
    import re as _re
    m = _re.findall(r'"([^"]{2,180})"', q)
    hints.extend(m or [])
    ext = _re.findall(r'([a-zA-Z0-9_. -]{2,180}\.(png|jpg|jpeg|webp|bmp|tiff|pdf|docx|pptx|xlsx|txt|md|csv|json))', q, flags=_re.IGNORECASE)
    hints.extend([x[0] for x in ext])
    # fallback broad hint for "image" queries
    if not hints and ("image" in q.lower() or "photo" in q.lower() or "picture" in q.lower()):
        hints.append("image")

    if not hints:
        return ""
    hint = hints[0].strip()
    if not hint:
        return ""

    # Match recent assets by name.
    items = store.list_assets(owner_email=owner_email)
    matched = []
    h = hint.lower()
    for item in items:
        name = str(item.get("name", ""))
        if h in name.lower():
            matched.append(item)
        if len(matched) >= max_assets:
            break
    # If user asked broadly about "image/photo/picture", include most recent image-like assets.
    if not matched and h in {"image", "photo", "picture"}:
        for item in items:
            mime = str(item.get("mime", "")).lower()
            name = str(item.get("name", "")).lower()
            if (
                mime.startswith("image/")
                or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"))
            ):
                matched.append(item)
            if len(matched) >= max_assets:
                break
    if not matched:
        return ""

    lines = []
    owner_slug = _owner_slug(owner_email)
    for i, item in enumerate(matched, start=1):
        aid = item.get("id", "")
        name = item.get("name", "")
        txt_path = settings.data_vault_root / "processed" / owner_slug / f"{aid}.txt"
        if not txt_path.exists():
            # Backward-compat fallback for older flat processed layout.
            txt_path = settings.data_vault_root / "processed" / f"{aid}.txt"
        if not txt_path.exists():
            continue
        try:
            txt = txt_path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            txt = ""
        if not txt:
            continue
        lines.append(f"[{i}] exact_asset:{name} -> {txt[:max_chars_per_asset]}")
    return "\n".join(lines)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/session/device-auto")
def session_device_auto():
    return _auto_pick_vb_device()


@app.get("/api/session/platform-check")
def session_platform_check():
    auto = _auto_pick_vb_device()
    root = chrome_user_data_root()
    root_txt = str(root) if root is not None else None
    root_exists = bool(root and root.exists())
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "chrome_user_data_root": root_txt,
        "chrome_user_data_root_exists": root_exists,
        "audio_devices_count": len(auto.get("devices", [])),
        "selected_device_id": auto.get("selected_device_id"),
        "selected_device_name": auto.get("selected_device_name"),
        "devices": auto.get("devices", []),
        "preferred_driver": auto.get("preferred_driver"),
        "setup_steps": auto.get("setup_steps", []),
    }


@app.get("/api/session/audio-validate")
def session_audio_validate(device_id: int | None = None):
    auto = _auto_pick_vb_device()
    selected_id = device_id if device_id is not None else auto.get("selected_device_id")
    if selected_id is None:
        raise HTTPException(status_code=400, detail="No input device available for validation")
    try:
        result = _validate_audio_flow(int(selected_id), seconds=2.0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio validation failed: {e}")
    return {
        "selected_device_id": int(selected_id),
        "selected_device_name": auto.get("selected_device_name"),
        **result,
    }


@app.get("/api/session/status")
def session_status():
    with _session_lock:
        running = _session_proc is not None and (_session_proc.poll() is None)
        code = None if _session_proc is None else _session_proc.poll()
        return {
            "running": running,
            "status": _session_meta.get("status", "idle"),
            "pid": _session_meta.get("pid"),
            "meeting_url": _session_meta.get("meeting_url"),
            "profile_email": _session_meta.get("profile_email"),
            "assistant_name": _session_meta.get("assistant_name"),
            "avatar_mode": _session_meta.get("avatar_mode"),
            "audio_device_id": _session_meta.get("audio_device_id"),
            "exit_code": code,
        }


@app.get("/api/session/logs")
def session_logs(limit: int = 200):
    n = max(20, min(int(limit), 2000))
    with _session_log_lock:
        items = list(_session_logs)[-n:]
    transcript_lines = [
        x for x in items
        if ("[Transcript]" in x or "[User]" in x or "[Aria]" in x or "[Assistant]" in x)
    ]
    return {"items": items, "transcript_items": transcript_lines}


@app.post("/api/session/stop")
def session_stop():
    global _session_proc
    with _session_lock:
        if _session_proc and (_session_proc.poll() is None):
            pid = _session_proc.pid
            try:
                if os.name != "nt":
                    _session_proc.send_signal(signal.SIGINT)
                else:
                    # Windows: avoid CTRL_BREAK_EVENT because it can affect the backend console group.
                    _session_proc.terminate()
            except Exception:
                try:
                    _session_proc.terminate()
                except Exception:
                    pass
            _session_meta["status"] = "stopping"
            _append_session_log("[Session] Stop requested.")

            # Wait briefly for graceful shutdown; then force stop.
            try:
                _session_proc.wait(timeout=8)
                _append_session_log(f"[Session] Stopped gracefully. exit_code={_session_proc.poll()}")
            except Exception:
                try:
                    _session_proc.terminate()
                    _session_proc.wait(timeout=3)
                    _append_session_log(f"[Session] Forced terminate issued. exit_code={_session_proc.poll()}")
                except Exception:
                    try:
                        _session_proc.kill()
                        _append_session_log(f"[Session] Forced kill issued. exit_code={_session_proc.poll()}")
                    except Exception:
                        pass
            # Extra Windows fallback: kill full child process tree if still alive.
            if os.name == "nt" and _session_proc and (_session_proc.poll() is None):
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=6,
                    )
                    _append_session_log("[Session] taskkill fallback executed.")
                except Exception:
                    pass

            _session_meta["status"] = "idle"
            _session_proc = None
            return {"ok": True, "status": "idle"}
        _session_meta["status"] = "idle"
        _session_proc = None
        return {"ok": True, "status": "idle"}


@app.post("/api/session/start")
def session_start(
    payload: SessionStartPayload,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    global _session_proc, _session_meta
    meeting_url = (payload.meeting_url or "").strip()
    locked_email = _owner_email(
        x_user_email=x_user_email,
        requester_email=(payload.profile_email or ""),
        authorization=authorization,
    )
    if locked_email == "global":
        raise HTTPException(status_code=403, detail="Authenticated email is required to start session")
    profile_email = locked_email
    assistant_name = (payload.assistant_name or "Aria").strip() or "Aria"
    avatar_mode = "female" if (payload.avatar_mode or "").strip().lower() == "female" else "3d"
    if not meeting_url:
        raise HTTPException(status_code=400, detail="meeting_url is required")

    auto = _auto_pick_vb_device()
    selected_id = payload.audio_device_id if payload.audio_device_id is not None else auto.get("selected_device_id")

    with _session_lock:
        if _session_proc and (_session_proc.poll() is None):
            raise HTTPException(status_code=409, detail="A meeting session is already running")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["ARIA_NON_INTERACTIVE"] = "1"
        env["ARIA_MEETING_URL"] = meeting_url
        env["ARIA_PROFILE_EMAIL"] = profile_email
        env["ARIA_ASSISTANT_NAME"] = assistant_name
        env["ARIA_AVATAR_MODE"] = avatar_mode
        if selected_id is not None:
            env["ARIA_AUDIO_DEVICE_ID"] = str(selected_id)
        _append_session_log(
            f"[Session] Launch env prepared profile={profile_email} avatar={avatar_mode} audio_device={selected_id if selected_id is not None else 'auto-in-main'}"
        )

        # Backend-triggered start: command is acknowledged by API first;
        # then main process handles browser shutdown and meeting join flow.
        cmd = [sys.executable, "-u", "main.py"]
        try:
            popen_kwargs = {}
            if os.name == "nt":
                # Needed so CTRL_BREAK_EVENT can be sent for graceful stop on Windows.
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            _session_proc = subprocess.Popen(
                cmd,
                cwd=str(Path(__file__).resolve().parents[1]),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                **popen_kwargs,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to start session: {e}")
        _spawn_session_log_reader(_session_proc)

        _session_meta = {
            "status": "running",
            "pid": _session_proc.pid,
            "meeting_url": meeting_url,
            "profile_email": profile_email,
            "assistant_name": assistant_name,
            "avatar_mode": avatar_mode,
            "audio_device_id": selected_id,
            "started_at": _utc_now_iso(),
        }
        _append_session_log(
            f"[Session] Started pid={_session_proc.pid} meeting={meeting_url} "
            f"profile={profile_email} assistant={assistant_name} avatar={avatar_mode} audio_device={selected_id}"
        )
        return {
            "ok": True,
            "status": "running",
            "pid": _session_proc.pid,
            "selected_device_id": selected_id,
            "selected_device_name": auto.get("selected_device_name"),
        }


@app.on_event("startup")
def start_automation_worker():
    def _loop():
        while True:
            try:
                process_due_automation_jobs(store, ingestor)
            except Exception:
                pass
            time.sleep(15)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


@app.get("/api/data/history")
def list_history(x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    return {"items": store.list_assets(owner_email=owner)}


@app.post("/api/data/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    results = []
    total = 0
    try:
        for f in files[:24]:
            filename = (f.filename or "file").strip() or "file"
            content = await f.read()
            size = len(content)
            if size > MAX_DATA_UPLOAD_FILE_BYTES:
                raise HTTPException(status_code=400, detail=f"File '{filename}' exceeds 25 MB limit")
            total += size
            if total > MAX_DATA_UPLOAD_TOTAL_BYTES:
                raise HTTPException(status_code=400, detail="Total upload exceeds 80 MB limit")
            item = ingestor.ingest_file(content, filename, source_type="file", owner_email=owner)
            results.append(item)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    return {"items": results}


@app.post("/api/data/link")
def upload_link(payload: LinkPayload, x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    if not payload.url.strip():
        raise HTTPException(status_code=400, detail="URL is required")
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    item = ingestor.ingest_link(payload.url.strip(), owner_email=owner)
    return {"item": item}


@app.post("/api/data/text")
def upload_text(payload: TextPayload, x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    title = (payload.title or "quick_note").strip() or "quick_note"
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    item = ingestor.ingest_text(text=text, title=title, owner_email=owner)
    return {"item": item}


@app.delete("/api/data/{asset_id}")
def delete_asset(asset_id: str, x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    ok = ingestor.delete_asset(asset_id, owner_email=owner)
    if not ok:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"ok": True}


@app.post("/api/data/reprocess/{asset_id}")
def reprocess_asset(asset_id: str, x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    try:
        item = ingestor.reprocess_asset(asset_id, owner_email=owner)
        if not item:
            raise HTTPException(status_code=404, detail="Asset not found or inaccessible")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reprocess failed: {e}")
    return {"item": item}


@app.post("/api/data/ingest-meeting-artifacts")
def ingest_meeting_artifacts():
    meetings_dir = Path(MEMORY_DIR)
    if not meetings_dir.exists():
        return {"ingested": 0}

    ingested = 0
    for folder in meetings_dir.iterdir():
        if not folder.is_dir():
            continue
        for filename in ["transcript.txt", "summary.md", "notes.json", "diarization.json", "segments.json"]:
            fp = folder / filename
            if not fp.exists():
                continue
            data = fp.read_bytes()
            ingestor.ingest_file(data, f"{folder.name}_{filename}", source_type="meeting")
            ingested += 1

    return {"ingested": ingested}


@app.get("/api/los/history")
def los_history(x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    return {"items": store.list_los_items(owner_email=owner)}


@app.post("/api/los/note")
def los_note(payload: LosNotePayload, x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    grouped = {"group": "General", "title": "Quick note", "item_type": "note", "summary": text}
    try:
        context = _los_related_context(owner_email=owner)
        existing_groups = sorted({(i.get("group_name") or "").strip() for i in store.list_los_items(owner_email=owner) if (i.get("group_name") or "").strip()})
        client = _los_client()
        response = client.chat.completions.create(
            model=LOS_GROQ_MODEL,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convert user input into structured LOS storage. "
                        "Return strict JSON keys: group, title, item_type, summary. "
                        "item_type must be either task or note. "
                        "Use stable semantic grouping names. "
                        "If the input matches an existing group semantically, reuse that same group name exactly."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Existing groups: {', '.join(existing_groups) if existing_groups else '[none]'}\n\n"
                        f"Recent user knowledge context:\n{context}\n\n"
                        f"Input:\n{text}"
                    ),
                },
            ],
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        grouped = {
            "group": str(parsed.get("group", "General"))[:80],
            "title": str(parsed.get("title", "Quick note"))[:140],
            "item_type": "task" if str(parsed.get("item_type", "")).lower() == "task" else "note",
            "summary": str(parsed.get("summary", text))[:4000],
        }
    except Exception:
        pass

    created_at = datetime.utcnow().isoformat()
    item = {
        "id": str(uuid.uuid4()),
        "owner_email": owner,
        "item_type": grouped["item_type"],
        "title": grouped["title"],
        "content": grouped["summary"],
        "group_name": grouped["group"] or "General",
        "source_mode": (payload.source_mode or "typed").strip() or "typed",
        "created_at": created_at,
    }
    store.add_los_item(item)

    # Also ingest to shared memory index so meeting brain can reference it later.
    ingestor.ingest_text(
        text=(
            f"LOS {item['item_type'].upper()} | group={item['group_name']} | "
            f"title={item['title']} | content={item['content']} | created_at={item['created_at']}"
        ),
        title=f"los_{item['item_type']}_{item['title']}",
        owner_email=owner,
    )
    reminder = _schedule_los_reminder_if_any(
        owner=owner,
        text=text,
        source_mode=(payload.source_mode or "typed").strip() or "typed",
    )
    return {"item": item, "automation_reminder": reminder}


@app.get("/api/los/subagents/{agent_name}/messages")
def los_agent_messages(agent_name: str, limit: int = 30, x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    if agent_name not in LOS_AGENT_PERSONAS:
        raise HTTPException(status_code=404, detail="Unknown sub-agent")
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    return {"items": store.list_los_agent_messages(agent_name, limit=limit, owner_email=owner)}


@app.post("/api/los/subagents/chat")
def los_subagent_chat(payload: LosAgentChatPayload, x_user_email: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    agent_name = (payload.agent_name or "").strip().lower()
    message = (payload.message or "").strip()
    autonomy_mode = (payload.autonomy_mode or "suggest_actions").strip().lower()
    if agent_name not in LOS_AGENT_PERSONAS:
        raise HTTPException(status_code=400, detail="Invalid agent_name")
    if autonomy_mode not in LOS_AUTONOMY_MODES:
        raise HTTPException(status_code=400, detail="Invalid autonomy_mode")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    pending_key = (owner, agent_name)
    pending = _LOS_PENDING_EXECUTIONS.get(pending_key)
    approved_now = _is_approval_text(message)
    execution_intent = _is_execution_intent(message)

    now = datetime.utcnow().isoformat()
    user_row = {
        "id": str(uuid.uuid4()),
        "owner_email": owner,
        "agent_name": agent_name,
        "role": "user",
        "message": message,
        "created_at": now,
    }
    store.add_los_agent_message(user_row)

    context = _los_related_context(owner_email=owner)
    los_notes_context = _los_recent_notes_context(limit=30, owner_email=owner)
    exact_asset_context = _los_exact_asset_text_context(message, max_assets=4, max_chars_per_asset=16000, owner_email=owner)
    deep_context = _los_deep_knowledge_context(
        query=message,
        max_chunks=28,
        owner_email=owner,
    )
    recent = store.list_los_agent_messages(agent_name, limit=14, owner_email=owner)
    prompt_messages = []
    for m in recent:
        role = m.get("role", "")
        if role not in {"user", "assistant"}:
            continue
        prompt_messages.append({"role": role, "content": m.get("message", "")})

    client = _los_client()
    completion = client.chat.completions.create(
        model=LOS_GROQ_MODEL,
        temperature=0.3,
        messages=[
            {"role": "system", "content": LOS_AGENT_PERSONAS[agent_name]},
            {"role": "system", "content": f"Autonomy mode: {autonomy_mode}. {LOS_AUTONOMY_MODES[autonomy_mode]}"},
            {
                "role": "system",
                "content": (
                    "Hard rules: stay only in your domain. "
                    "If user asks outside your domain (even subtly), briefly acknowledge then redirect to your domain. "
                    "If user asks inside your domain, answer concretely using known user context as if you are their dedicated advisor. "
                    "Do not answer out-of-domain details. "
                    "Mode policy: "
                    "suggest_actions => only suggest, never execute; "
                    "execute_with_approval => if execution is requested, ask for explicit APPROVE and do not execute yet; "
                    "autonomous_mode => execute allowed actions without approval and report what was executed."
                ),
            },
            {
                "role": "system",
                "content": (
                    "Use this context hierarchy for answers:\n"
                    "1) Deep retrieved knowledge chunks (highest fidelity)\n"
                    "2) LOS notes/tasks summary\n"
                    "3) Asset/history metadata\n"
                    "If chunk context is insufficient, say what is missing and ask a narrow follow-up."
                ),
            },
            {"role": "system", "content": f"Asset/history metadata:\n{context}"},
            {"role": "system", "content": f"LOS notes and tasks:\n{los_notes_context}"},
            {"role": "system", "content": f"Exact matched asset full text:\n{exact_asset_context}"},
            {"role": "system", "content": f"Deep knowledge chunks:\n{deep_context}"},
            *prompt_messages,
        ],
        max_tokens=500,
    )
    reply = (completion.choices[0].message.content or "").strip() or "Noted."

    assistant_row = {
        "id": str(uuid.uuid4()),
        "owner_email": owner,
        "agent_name": agent_name,
        "role": "assistant",
        "message": reply,
        "created_at": datetime.utcnow().isoformat(),
    }
    store.add_los_agent_message(assistant_row)

    ingestor.ingest_text(
        text=(
            f"LOS SUBAGENT CHAT | agent={agent_name} | user={message} | assistant={reply} "
            f"| source_mode={payload.source_mode} | at={assistant_row['created_at']}"
        ),
        title=f"los_chat_{agent_name}_{assistant_row['created_at']}",
        owner_email=owner,
    )
    reminder = None
    # Enforce deterministic mode behavior without changing existing app flow.
    effective_reminder = None
    if autonomy_mode == "suggest_actions":
        effective_reminder = None
        if execution_intent:
            reply = "Execution policy (suggest_actions): I did not execute anything. I can provide a step-by-step action plan."
    elif autonomy_mode == "execute_with_approval":
        if approved_now and pending:
            effective_reminder = _schedule_los_reminder_if_any(
                owner=owner,
                text=pending.get("text", ""),
                source_mode=(payload.source_mode or "typed").strip() or "typed",
            )
            _LOS_PENDING_EXECUTIONS.pop(pending_key, None)
            if effective_reminder and effective_reminder.get("error"):
                reply = f"Execution failed after approval: {effective_reminder.get('error')}"
            elif effective_reminder and int(effective_reminder.get("count", 0) or 0) > 0:
                first = (effective_reminder.get("jobs") or [{}])[0]
                reply = (
                    "Execution complete after approval. "
                    f"Scheduled/sent to {first.get('recipient', '')} at {first.get('schedule_at', '')}."
                )
            else:
                reply = "Execution received, but no executable automation job was produced from your request."
        elif execution_intent:
            _LOS_PENDING_EXECUTIONS[pending_key] = {
                "text": message,
                "created_at": datetime.utcnow().isoformat(),
            }
            reply = "Approval needed. Reply with 'approve' to execute this request."
        else:
            effective_reminder = None
    else:  # autonomous_mode
        if execution_intent:
            effective_reminder = _schedule_los_reminder_if_any(
                owner=owner,
                text=message,
                source_mode=(payload.source_mode or "typed").strip() or "typed",
            )
            if effective_reminder and effective_reminder.get("error"):
                reply = f"Autonomous execution failed: {effective_reminder.get('error')}"
            elif effective_reminder and int(effective_reminder.get("count", 0) or 0) > 0:
                first = (effective_reminder.get("jobs") or [{}])[0]
                reply = (
                    "Autonomous execution complete: scheduled/sent to "
                    f"{first.get('recipient', '')} at {first.get('schedule_at', '')}."
                )
            else:
                reply = "Autonomous mode active. No executable automation job was produced from your request."
        else:
            effective_reminder = None

    return {"reply": reply, "message": assistant_row, "automation_reminder": effective_reminder, "autonomy_mode": autonomy_mode, "available_agents": sorted(LOS_AGENT_PERSONAS.keys()), "available_autonomy_modes": sorted(LOS_AUTONOMY_MODES.keys())}


@app.get("/api/automation/history")
def automation_history(
    limit: int = 200,
    requester_email: str | None = None,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, requester_email=requester_email, authorization=authorization)
    rows = store.list_automation_jobs(limit=limit)
    items = []
    for r in rows:
        row = dict(r)
        if owner and (row.get("created_by_email") or "").strip().lower() != owner:
            continue
        try:
            row["recipients"] = json.loads(row.get("recipients_json") or "[]")
        except Exception:
            row["recipients"] = []
        try:
            row["attachments"] = json.loads(row.get("attachments_json") or "[]")
        except Exception:
            row["attachments"] = []
        items.append(row)
    return {"items": items}


@app.post("/api/automation/attachments")
async def automation_upload_attachments(
    files: list[UploadFile] = File(...),
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    max_file_bytes = 1024 * 1024 * 1024  # 1 GB per file
    max_total_bytes = 1024 * 1024 * 1024  # 1 GB per request
    total = 0
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    print(f"[AutomationAttach] request owner={owner} files={len(files)}")
    items = []
    try:
        owner_slug = _owner_slug(owner)
        attach_root = settings.data_vault_root / "raw" / owner_slug / "automation_attachments"
        attach_root.mkdir(parents=True, exist_ok=True)
        for f in files[:24]:
            fname = (f.filename or "file").strip() or "file"
            content = await f.read()
            size = len(content)
            print(f"[AutomationAttach] file name={fname} size={size}")
            if size > max_file_bytes:
                raise HTTPException(status_code=400, detail=f"Attachment '{fname}' exceeds 1 GB limit")
            total += size
            if total > max_total_bytes:
                raise HTTPException(status_code=400, detail="Total attachment upload exceeds 1 GB limit")
            safe_name = fname.replace("\\", "_").replace("/", "_")
            stored = attach_root / f"{uuid.uuid4()}__{safe_name}"
            stored.write_bytes(content)
            items.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": fname,
                    "path": str(stored),
                    "size": size,
                    "text_length": 0,
                    "chunk_count": 0,
                }
            )
            print(f"[AutomationAttach] stored path={stored}")
    except HTTPException:
        print("[AutomationAttach] rejected by validation")
        raise
    except ValueError as e:
        print(f"[AutomationAttach] value error: {e}")
        raise HTTPException(status_code=400, detail=f"Attachment rejected: {e}")
    except Exception as e:
        print(f"[AutomationAttach] internal error: {e}")
        raise HTTPException(status_code=500, detail=f"Attachment upload failed: {e}")
    return {"items": items}


@app.get("/api/connects")
def list_connects(
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    return {"items": store.list_contacts(owner)}


@app.post("/api/connects")
def upsert_connect(
    payload: ContactPayload,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    name = (payload.name or "").strip()
    email = (payload.email or "").strip().lower()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="name is required")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="valid email is required")
    now_iso = _utc_now_iso()
    row = {
        "id": str(uuid.uuid4()),
        "owner_email": owner,
        "name": name[:120],
        "email": email[:320],
        "updated_at": now_iso,
    }
    store.upsert_contact(row)
    ingestor.ingest_text(
        text=f"CONTACT SAVED | owner={owner} | name={row['name']} | email={row['email']} | updated_at={now_iso}",
        title=f"contact_{row['name']}",
        owner_email=owner,
    )
    return {"ok": True}


@app.delete("/api/connects/{contact_id}")
def delete_connect(
    contact_id: str,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    ok = store.delete_contact(owner, contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True}


@app.get("/api/automation/sender/{email}")
def automation_sender_get(email: str):
    row = store.get_automation_sender(email.strip().lower())
    if not row:
        return {"configured": False}
    return {
        "configured": True,
        "item": {
            "email": row["email"],
            "smtp_host": row["smtp_host"],
            "smtp_port": row["smtp_port"],
            "smtp_username": row["smtp_username"],
            "smtp_from_email": row["smtp_from_email"],
            "use_tls": row["use_tls"],
            "updated_at": row["updated_at"],
        },
    }


@app.get("/api/automation/sender-default")
def automation_sender_default(
    requester_email: str | None = None,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, requester_email=requester_email, authorization=authorization)
    if owner:
        row = store.get_automation_sender(owner)
        if not row:
            return {"configured": False}
        return {"configured": True, "item": row}
    rows = store.list_automation_senders(limit=1)
    if not rows:
        return {"configured": False}
    return {"configured": True, "item": rows[0]}


@app.post("/api/automation/sender/setup")
def automation_sender_setup(
    payload: AutomationSenderSetupPayload,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    email = (payload.email or "").strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    owner = _owner_email(x_user_email=x_user_email, requester_email=email, authorization=authorization)
    if email != owner:
        raise HTTPException(status_code=403, detail="sender email must match logged-in account")
    app_password = (payload.app_password or "").strip()
    if len(app_password) < 8:
        raise HTTPException(status_code=400, detail="App password looks too short")
    smtp_username = (payload.smtp_username or email).strip()
    smtp_from_email = (payload.smtp_from_email or email).strip()

    try:
        cipher, salt = encrypt_text(app_password)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sender encryption unavailable: {e}")
    now_iso = _utc_now_iso()
    store.upsert_automation_sender(
        {
            "email": email,
            "smtp_host": (payload.smtp_host or "smtp.gmail.com").strip(),
            "smtp_port": int(payload.smtp_port or 587),
            "smtp_username": smtp_username,
            "smtp_from_email": smtp_from_email,
            "use_tls": bool(payload.use_tls),
            "password_ciphertext": cipher,
            "password_salt": salt,
            "updated_at": now_iso,
        }
    )
    return {"ok": True}


@app.post("/api/automation/schedule")
def automation_schedule(
    payload: AutomationCreatePayload,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    requester = (payload.requester_email or "").strip().lower()
    if "@" not in requester:
        raise HTTPException(status_code=400, detail="Valid requester_email is required")
    owner = _owner_email(x_user_email=x_user_email, requester_email=requester, authorization=authorization)
    if requester != owner:
        raise HTTPException(status_code=403, detail="requester_email must match logged-in account")
    mode = (payload.mode or "ai_schedule").strip().lower()
    bulk_mode = (payload.bulk_mode or "same_for_all").strip().lower()
    instruction = (payload.instruction or "").strip()
    subject = (payload.subject or "").strip()
    message = (payload.message or "").strip()
    explicit_recipients = parse_recipients(payload.recipients or "")
    named_recipients: list[str] = []
    ai_recipients: list[str] = []

    if mode not in {"ai_schedule", "custom_schedule", "send_now"}:
        raise HTTPException(status_code=400, detail="mode must be ai_schedule, custom_schedule, or send_now")

    parsed = {
        "subject": subject or "Aria Reminder",
        "message": message or instruction or "Aria automated message",
        "recipients": [requester],
        "schedule_at_utc": _utc_now_iso(),
        "timezone": (payload.timezone or "UTC"),
    }
    if mode == "ai_schedule":
        if not instruction:
            raise HTTPException(status_code=400, detail="instruction is required for ai_schedule")
        parsed = _parse_automation_instruction(instruction, requester)
    elif mode == "custom_schedule":
        if (bulk_mode != "custom_per_email") and (not subject or not message):
            raise HTTPException(status_code=400, detail="subject and message are required for custom_schedule")
        if not (payload.schedule_at and payload.schedule_at.strip()):
            raise HTTPException(status_code=400, detail="schedule_at is required for custom_schedule")
        parsed["schedule_at_utc"] = _parse_iso_schedule(payload.schedule_at)
    elif mode == "send_now":
        if (not subject or not message) and instruction:
            parsed_now = _parse_automation_instruction(instruction, requester)
            subject = subject or parsed_now.get("subject", "")
            message = message or parsed_now.get("message", "")
            if not explicit_recipients and not (payload.recipients or "").strip():
                raw_ai = parsed_now.get("recipients") or []
                if isinstance(raw_ai, list):
                    ai_recipients = [str(x).strip().lower() for x in raw_ai if "@" in str(x)]
        if not subject or not message:
            raise HTTPException(status_code=400, detail="subject and message are required for send_now")
        parsed["subject"] = subject
        parsed["message"] = message
        parsed["schedule_at_utc"] = _utc_now_iso()

    if _explicit_self_target(instruction):
        recipients = [owner]
    else:
        if not explicit_recipients and instruction:
            named_recipients = _extract_named_recipients(instruction, owner)
        if not explicit_recipients and not named_recipients and instruction and _mentions_named_target_without_email(instruction):
            raise HTTPException(status_code=400, detail="Recipient name not found in Connects. Add contact or provide explicit email.")
        recipients = explicit_recipients or named_recipients or ai_recipients or parsed["recipients"]

    if len(recipients) > 12:
        raise HTTPException(status_code=400, detail="Maximum 12 recipients allowed")

    schedule_at = parsed["schedule_at_utc"]
    if mode == "ai_schedule" and payload.schedule_at and payload.schedule_at.strip():
        schedule_at = _parse_iso_schedule(payload.schedule_at)

    now_iso = _utc_now_iso()
    jobs = []
    shared_attachments = payload.shared_attachment_paths or []

    def _insert_job(recipient: str, subject_txt: str, message_txt: str, attachment_paths: list[str] | None = None):
        if _is_recent_duplicate_job(requester, recipient, subject_txt, message_txt, within_seconds=120):
            return
        job = {
            "id": str(uuid.uuid4()),
            "created_by_email": requester,
            "channel": "email",
            "recipients_json": json.dumps([recipient]),
            "subject": subject_txt[:300],
            "message": message_txt[:12000],
            "schedule_at": schedule_at,
            "timezone": (payload.timezone or parsed["timezone"] or "UTC"),
            "status": "scheduled",
            "source_prompt": instruction,
            "attachments_json": json.dumps(attachment_paths or []),
            "created_at": now_iso,
            "sent_at": None,
            "error_text": None,
        }
        store.add_automation_job(job)
        store.add_automation_event(
            {
                "id": str(uuid.uuid4()),
                "job_id": job["id"],
                "event_type": "scheduled",
                "details_json": json.dumps({"recipient": recipient, "schedule_at": schedule_at, "attachments": attachment_paths or []}),
                "created_at": now_iso,
            }
        )
        ingestor.ingest_text(
            text=(
                f"AUTOMATION SCHEDULED | job_id={job['id']} | by={requester} | channel=email | "
                f"to={recipient} | subject={job['subject']} | schedule_at={schedule_at} | "
                f"attachments={len(attachment_paths or [])} | prompt={instruction}"
            ),
            title=f"automation_scheduled_{job['id']}",
        )
        jobs.append({**job, "recipients": [recipient]})

    if bulk_mode == "custom_per_email":
        entries = payload.recipient_entries or []
        if not entries:
            raise HTTPException(status_code=400, detail="recipient_entries required for custom_per_email")
        if len(entries) > 12:
            raise HTTPException(status_code=400, detail="Maximum 12 recipient entries allowed")
        for e in entries:
            recipient = str(e.get("recipient", "")).strip().lower()
            sub = str(e.get("subject", "")).strip()
            msg = str(e.get("message", "")).strip()
            att = [x.strip() for x in str(e.get("attachment_paths", "")).split(",") if x.strip()]
            if "@" not in recipient or not sub or not msg:
                raise HTTPException(status_code=400, detail="Each recipient entry needs recipient, subject, message")
            _insert_job(recipient, sub, msg, att)
    elif bulk_mode == "ai_grouping":
        if not instruction:
            raise HTTPException(status_code=400, detail="instruction required for ai_grouping")
        entries = _ai_group_messages(instruction, recipients, payload.timezone or "UTC")
        if not entries:
            raise HTTPException(status_code=400, detail="AI grouping could not generate recipient messages")
        entries = entries[:12]
        for e in entries:
            _insert_job(e["recipient"], e["subject"], e["message"], shared_attachments)
    else:
        for r in recipients:
            _insert_job(r, parsed["subject"], parsed["message"], shared_attachments)

    if mode == "send_now":
        process_due_automation_jobs(store, ingestor)
    return {"items": jobs}


@app.get("/api/meetings")
def meetings_list(
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    items = [_meeting_payload_from_dir(d) for d in _meeting_dirs()]
    if owner and owner != "global":
        items = [m for m in items if (not m.get("owner_email")) or (m.get("owner_email") == owner)]
    return {"items": items, "count": len(items)}


@app.get("/api/system/self-check")
def system_self_check():
    auto = _auto_pick_vb_device()
    meetings = _meeting_dirs()
    with _session_lock:
        running = _session_proc is not None and (_session_proc.poll() is None)
        exit_code = None if _session_proc is None else _session_proc.poll()
    return {
        "ok": True,
        "session_running": running,
        "session_exit_code": exit_code,
        "audio_selected_device_id": auto.get("selected_device_id"),
        "audio_selected_device_name": auto.get("selected_device_name"),
        "meetings_count": len(meetings),
    }


@app.get("/api/meetings/{meeting_id}")
def meeting_detail(
    meeting_id: str,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    folder = Path(MEMORY_DIR) / meeting_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Meeting not found")
    out = _meeting_payload_from_dir(folder)
    if owner and owner != "global" and out.get("owner_email") and out.get("owner_email") != owner:
        raise HTTPException(status_code=403, detail="Meeting belongs to another account")
    for name, key in [("summary.md", "summary"), ("transcript.txt", "transcript"), ("diarization.json", "diarization"), ("speaker_transcript.txt", "speaker_transcript")]:
        fp = folder / name
        if fp.exists():
            try:
                txt = fp.read_text(encoding="utf-8", errors="ignore")
                out[key] = json.loads(txt) if key == "diarization" else txt
            except Exception:
                out[key] = [] if key == "diarization" else ""
    return out


@app.post("/api/meetings/{meeting_id}/chat")
def meeting_chat(
    meeting_id: str,
    payload: MeetingQueryPayload,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    folder = Path(MEMORY_DIR) / meeting_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Meeting not found")
    mp = _meeting_payload_from_dir(folder)
    if owner and owner != "global" and mp.get("owner_email") and mp.get("owner_email") != owner:
        raise HTTPException(status_code=403, detail="Meeting belongs to another account")
    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is required")

    context = _meeting_text(folder)
    if not context:
        return {"reply": "No meeting context found."}
    selected_semantic, global_semantic = _meeting_semantic_context(meeting_id, q, max_chunks=30)

    client = _los_client()
    completion = client.chat.completions.create(
        model=LOS_GROQ_MODEL,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a meeting analyst. Prioritize selected-meeting evidence first, then global backend memory. "
                    "If exact evidence is missing, say what is missing. Be concise and factual."
                ),
            },
            {"role": "system", "content": f"Meeting context:\n{context}"},
            {"role": "system", "content": f"Selected meeting semantic chunks:\n{selected_semantic}"},
            {"role": "system", "content": f"Global backend semantic chunks:\n{global_semantic}"},
            {"role": "user", "content": q},
        ],
        max_tokens=500,
    )
    reply = (completion.choices[0].message.content or "").strip() or "No answer."
    return {"reply": reply}


@app.post("/api/meetings/{meeting_id}/ingest")
def ingest_single_meeting(
    meeting_id: str,
    x_user_email: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    owner = _owner_email(x_user_email=x_user_email, authorization=authorization)
    folder = Path(MEMORY_DIR) / meeting_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail="Meeting not found")
    mp = _meeting_payload_from_dir(folder)
    if owner and owner != "global" and mp.get("owner_email") and mp.get("owner_email") != owner:
        raise HTTPException(status_code=403, detail="Meeting belongs to another account")
    ingested = 0
    for filename in ["transcript.txt", "summary.md", "notes.json", "diarization.json", "segments.json", "speaker_transcript.txt"]:
        fp = folder / filename
        if not fp.exists():
            continue
        ingestor.ingest_file(fp.read_bytes(), f"{folder.name}_{filename}", source_type="meeting", owner_email=owner)
        ingested += 1
    return {"ingested": ingested}
