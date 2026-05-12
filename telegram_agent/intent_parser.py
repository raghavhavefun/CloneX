from datetime import datetime, timedelta, timezone
from typing import Any
import re
import json

try:
    from groq import Groq
except ImportError:
    Groq = None


def parse_join_command(text: str) -> dict[str, Any] | None:
    raw = (text or '').strip()
    if not raw:
        return None
    lowered = raw.lower()
    if not (lowered.startswith('join now ') or lowered.startswith('/joinnow ')):
        return None

    m = re.search(r'(https?://\S+)', raw)
    if not m:
        return {'error': 'Missing meeting link. Example: join now https://meet.google.com/abc-defg-hij name Rag avatar 3d'}
    link = m.group(1).strip()

    name = 'Aria'
    avatar = '3d'

    m_name = re.search(r'\bname\s+([^\n]+?)(?:\s+avatar\b|$)', raw, flags=re.IGNORECASE)
    if m_name:
        name = m_name.group(1).strip()

    m_avatar = re.search(r'\bavatar\s+(female|3d)\b', raw, flags=re.IGNORECASE)
    if m_avatar:
        avatar = m_avatar.group(1).lower()

    return {'meeting_url': link, 'assistant_name': name, 'avatar_mode': avatar}


def parse_schedule_command(text: str) -> dict[str, Any] | None:
    raw = (text or '').strip()
    if not raw.lower().startswith('schedule '):
        return None

    m_link = re.search(r'(https?://\S+)', raw)
    if not m_link:
        return {'error': 'Missing meeting link. Example: schedule https://meet.google.com/abc-defg-hij at 2026-05-06 19:30'}
    link = m_link.group(1).strip()

    m_at = re.search(r'\bat\s+(.+)$', raw, flags=re.IGNORECASE)
    if not m_at:
        return {'error': 'Missing schedule time. Use: at YYYY-MM-DD HH:MM (24h)'}

    at_raw = m_at.group(1).strip()
    try:
        dt = datetime.strptime(at_raw, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
    except Exception:
        return {'error': 'Invalid time format. Use exactly: YYYY-MM-DD HH:MM (24h, UTC)'}

    run_at = dt - timedelta(minutes=5)
    return {
        'meeting_url': link,
        'assistant_name': 'Aria',
        'avatar_mode': '3d',
        'schedule_at_utc': dt.isoformat(),
        'start_at_utc': run_at.isoformat(),
    }


def parse_email_command(text: str, groq_key: str = '') -> dict[str, Any] | None:
    raw = (text or '').strip()
    lower_raw = raw.lower()
    if not any(lower_raw.startswith(w) for w in ['email ', 'remind ', 'remind me ', 'note ', 'schedule ', 'send ']):
        return None
    
    if not Groq or not groq_key:
        return {'error': 'Groq library or API key missing for intent parsing.'}

    client = Groq(api_key=groq_key)
    now_local = datetime.now().astimezone()
    prompt = f"""
    You are an intent parser. The user wants to send an email, create a reminder, or take a note.
    Command: "{raw}"
    Current Time (Local): {now_local.isoformat()}
    Extract the following into a JSON object strictly:
    - "recipient": the name or email address. If it's a reminder or note for themselves, output "myself".
    - "body": the content of the message or reminder.
    - "schedule_type": either "send_now" or "custom_schedule". If they specify a time/delay, set to custom_schedule, else send_now.
    - "schedule_time_local": If custom_schedule, calculate the exact requested time based on Current Time and output it strictly as an ISO8601 format string with timezone offset (e.g. "2026-05-06T15:00:00+05:30"). If now, null.
    
    Return ONLY valid JSON.
    """
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content
        if not content:
            return {'error': 'Failed to parse intent.'}
        parsed = json.loads(content)
        parsed['raw_command'] = raw
        return parsed
    except Exception as e:
        return {'error': f'Groq error: {str(e)}'}
