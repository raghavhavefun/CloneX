from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telegram_agent.config import load_config
import sqlite3
import json
from datetime import datetime, timezone
from telegram_agent.state_store import init_db, get_bot_token, get_session, upsert_session, clear_session, _conn as tg_conn, has_notified_job, mark_job_notified
from telegram_agent.auth_supabase import SupabaseOtpClient
from telegram_agent.aria_backend_client import AriaBackendClient
from telegram_agent.intent_parser import parse_join_command, parse_schedule_command, parse_email_command
from telegram_agent.scheduler import MeetingScheduler, ScheduledMeetingJob
from telegram_agent.heartbeat import heartbeat_status

CFG = load_config()
BACKEND = AriaBackendClient(CFG.data_backend_url)
OTP = SupabaseOtpClient(CFG)
SCHEDULER: MeetingScheduler | None = None
APP: Application | None = None  # type: ignore

LOS_AGENT_ALIASES = {
    "command agent": "command_agent",
    "identity agent": "identity_agent",
    "calendar agent": "calendar_agent",
    "email communication agent": "email_communication_agent",
    "email agent": "email_communication_agent",
    "communication agent": "email_communication_agent",
    "opportunity agent": "opportunity_agent",
    "finance agent": "finance_agent",
    "research agent": "research_agent",
    "negotiation agent": "negotiation_agent",
    "content agent": "content_agent",
    "business builder agent": "business_builder_agent",
    "network agent": "network_agent",
    "execution agent": "execution_agent",
    "social media agent": "social_media_agent",
    "cofounder agent": "cofounder_agent",
}


def _normalize_los_agent_name(raw: str) -> str:
    t = (raw or "").strip().strip('"').strip("'").lower()
    if not t:
        return ""
    t = t.replace("-", " ")
    if t.startswith("agent "):
        t = t[6:].strip()
    if t.endswith(" agent") and t not in LOS_AGENT_ALIASES:
        # keep "x agent" as-is for alias lookup first, then fallback below
        pass
    if t in LOS_AGENT_ALIASES:
        return LOS_AGENT_ALIASES[t]
    return "_".join(part for part in t.split() if part)


def _uid(update: Update) -> str:  # type: ignore
    return str(update.effective_user.id if update.effective_user else '')


def _get_auth(update: Update) -> tuple[str, str, str]:  # type: ignore
    sess = get_session(_uid(update))
    return (
        str(sess.get('account_email', '') or ''),
        str(sess.get('supabase_access_token', '') or ''),
        str(sess.get('auth_state', 'unauthenticated') or 'unauthenticated'),
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore
    await update.message.reply_text(
        'Aria Telegram Agent is running.\n'
        '1) auth your@email.com\n'
        '2) otp 123456\n\n'
        'Commands:\n'
        '- join now <meeting_link> name <assistant> avatar <3d|female>\n'
        '- schedule <meeting_link> at YYYY-MM-DD HH:MM (UTC)\n'
        '- status\n'
        '- stop\n'
        '- los mode <suggest_actions|execute_with_approval|autonomous_mode>\n'
        '- /command\n'
        '- logout'
    )


async def cmd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore
    await update.message.reply_text(
        "Aria Telegram Command Center\n\n"
        "Auth\n"
        "- auth <email>\n"
        "- otp <code>\n"
        "- logout\n\n"
        "Session / Meetings\n"
        "- join now <meeting_link> name <assistant> avatar <3d|female>\n"
        "- schedule <meeting_link> at YYYY-MM-DD HH:MM\n"
        "- status\n"
        "- stop\n\n"
        "LOS (Life Operating System)\n"
        "- talk to los agent \"<agent name>\"\n"
        "- los mode <suggest_actions|execute_with_approval|autonomous_mode>\n"
        "- exit  (leave current LOS agent chat)\n\n"
        "LOS Agent Names\n"
        "- command agent\n"
        "- identity agent\n"
        "- calendar agent\n"
        "- email communication agent\n"
        "- opportunity agent\n"
        "- finance agent\n"
        "- research agent\n"
        "- negotiation agent\n"
        "- content agent\n"
        "- business builder agent\n"
        "- network agent\n"
        "- execution agent\n"
        "- social media agent\n"
        "- cofounder agent\n\n"
        "Automation / Contacts\n"
        "- email <instruction>\n"
        "- remind <instruction>\n"
        "- send <instruction>\n"
        "- history\n"
        "- save connect <Name> <Email>\n\n"
        "Data Vault Uploads\n"
        "- Send a document/photo directly in chat to upload it.\n\n"
        "Examples\n"
        "- talk to los agent \"social media agent\"\n"
        "- los mode execute_with_approval\n"
        "- send reminder to raj@example.com tomorrow 10 am"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore
    email, bearer, state = _get_auth(update)
    if state != 'verified' or not email or not bearer:
        await update.message.reply_text('Not authenticated. Run: auth your@email.com')
        return
    ok, msg = heartbeat_status(BACKEND, email=email, bearer=bearer)
    await update.message.reply_text(msg if ok else f'ERROR: {msg}')


async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore
    clear_session(_uid(update))
    await update.message.reply_text('Logged out from Telegram agent session.')


async def _run_scheduled_start(job: ScheduledMeetingJob) -> None:
    if APP is None:
        return
    sess = get_session(job.telegram_user_id)
    email = str(sess.get('account_email', '') or '')
    bearer = str(sess.get('supabase_access_token', '') or '')
    if not email or not bearer:
        return
    ok, out = BACKEND.session_start(
        meeting_url=job.meeting_url,
        email=email,
        bearer=bearer,
        assistant_name=job.assistant_name,
        avatar_mode=job.avatar_mode,
    )
    txt = 'Scheduled meeting start triggered. '
    txt += 'Success.' if ok else f'Failed: {out}'
    try:
        await APP.bot.send_message(chat_id=int(job.telegram_user_id), text=txt)
    except Exception:
        pass


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore
    msg = (update.message.text or '').strip()
    uid = _uid(update)

    if msg.lower().startswith('auth '):
        email = msg[5:].strip().lower()
        if '@' not in email:
            await update.message.reply_text('Invalid email. Use: auth your@email.com')
            return
        ok, text = OTP.send_otp(email)
        if ok:
            upsert_session(uid, {'pending_email': email, 'auth_state': 'otp_sent'})
        await update.message.reply_text(text)
        return

    if msg.lower().startswith('otp '):
        code = msg[4:].strip()
        sess = get_session(uid)
        pending = str(sess.get('pending_email', '') or '')
        if not pending:
            await update.message.reply_text('No pending email. Start with: auth your@email.com')
            return
        ok, text, payload = OTP.verify_otp(pending, code)
        if not ok:
            await update.message.reply_text(text)
            return
        upsert_session(
            uid,
            {
                'account_email': payload['email'],
                'supabase_access_token': payload['access_token'],
                'supabase_refresh_token': payload.get('refresh_token', ''),
                'auth_state': 'verified',
                'pending_email': '',
            },
        )
        await update.message.reply_text('Authentication successful. You can now run join/schedule/status/stop.')
        return

    email, bearer, state = _get_auth(update)
    if state != 'verified' or not email or not bearer:
        await update.message.reply_text('Authenticate first. Run: auth your@email.com')
        return

    sess = get_session(uid)
    los_agent = str(sess.get('los_agent', '') or '')

    if msg.lower() == 'exit' and los_agent:
        upsert_session(uid, {'los_agent': ''})
        await update.message.reply_text(f'Exited LOS mode with {los_agent}. Back to normal commands.')
        return

    los_mode = str(sess.get('los_mode', 'suggest_actions') or 'suggest_actions').strip().lower()

    if msg.lower().startswith('los mode '):
        requested = msg[9:].strip().lower()
        allowed = {"suggest_actions", "execute_with_approval", "autonomous_mode"}
        if requested not in allowed:
            await update.message.reply_text("Invalid mode. Use: suggest_actions | execute_with_approval | autonomous_mode")
            return
        upsert_session(uid, {'los_mode': requested})
        await update.message.reply_text(f'LOS mode set to {requested}')
        return

    if los_agent:
        ok, out = BACKEND.los_chat(email, bearer, los_agent, msg, autonomy_mode=los_mode)
        if ok and isinstance(out, dict):
            reply = out.get('reply', '') or str(out)
            await update.message.reply_text(reply)
        else:
            await update.message.reply_text(f'LOS Error: {out}')
        return

    if msg.lower().startswith('talk to los '):
        agent = msg[12:].strip()
        if agent.lower().startswith('agent '):
            agent = agent[6:].strip()
        agent = _normalize_los_agent_name(agent)
        if not agent:
            await update.message.reply_text('Specify an agent name. Example: talk to los agent "social media agent"')
            return
        upsert_session(uid, {'los_agent': agent})
        await update.message.reply_text(f'Entered LOS mode with {agent}. Type "exit" to leave.')
        return

    lower_msg = msg.lower()
    if lower_msg.startswith('save connect '):
        parts = msg[13:].strip().rsplit(' ', 1)
        if len(parts) != 2 or '@' not in parts[1]:
            await update.message.reply_text('Invalid format. Use: save connect <Name> <Email>')
            return
        name = parts[0].strip()
        contact_email = parts[1].strip()
        ok, out = BACKEND.save_connect(email, bearer, name, contact_email)
        await update.message.reply_text(out if ok else f'Save connect failed: {out}')
        return

    if any(lower_msg.startswith(w) for w in ['email ', 'remind ', 'remind me ', 'note ', 'schedule ', 'send ']):
        await update.message.reply_text('Parsing intent with Groq...')
        parsed = parse_email_command(msg, groq_key=CFG.telegram_groq_key)
        if not parsed:
            await update.message.reply_text('Failed to parse email intent.')
            return
        if 'error' in parsed:
            await update.message.reply_text(str(parsed['error']))
            return
        
        ok, out = BACKEND.automation_schedule(email, bearer, parsed)
        if ok:
            await update.message.reply_text(f'Success: {out}')
        else:
            await update.message.reply_text(f'Email Schedule Error: {out}')
        return

    if msg.lower() == 'history':
        ok, out = BACKEND.automation_history(email, bearer, limit=5)
        if ok and isinstance(out, dict):
            items = out.get('history', [])
            if not items:
                await update.message.reply_text('No recent automation history.')
            else:
                lines = [f"- {i.get('job_type')} to {i.get('recipient_email')}: {i.get('status')}" for i in items]
                await update.message.reply_text('\n'.join(lines))
        else:
            await update.message.reply_text(f'History Error: {out}')
        return

    if msg.lower() == 'stop':
        ok, out = BACKEND.session_stop(email=email, bearer=bearer)
        await update.message.reply_text('Stopped.' if ok else f'Stop failed: {out}')
        return

    if msg.lower() == 'status':
        ok, out = BACKEND.session_status(email=email, bearer=bearer)
        if ok and isinstance(out, dict):
            await update.message.reply_text(f"Session status: {out.get('status', 'unknown')} | pid: {out.get('pid')}")
        else:
            await update.message.reply_text(f'Status failed: {out}')
        return

    parsed_join = parse_join_command(msg)
    if parsed_join is not None:
        if parsed_join.get('error'):
            await update.message.reply_text(str(parsed_join['error']))
            return
        ok, out = BACKEND.session_start(
            meeting_url=str(parsed_join['meeting_url']),
            email=email,
            bearer=bearer,
            assistant_name=str(parsed_join.get('assistant_name', 'Aria')),
            avatar_mode=str(parsed_join.get('avatar_mode', '3d')),
        )
        await update.message.reply_text('Meeting start requested.' if ok else f'Start failed: {out}')
        return

    parsed_sched = parse_schedule_command(msg)
    if parsed_sched is not None:
        if parsed_sched.get('error'):
            await update.message.reply_text(str(parsed_sched['error']))
            return
        job = ScheduledMeetingJob(
            telegram_user_id=uid,
            meeting_url=str(parsed_sched['meeting_url']),
            assistant_name=str(parsed_sched['assistant_name']),
            avatar_mode=str(parsed_sched['avatar_mode']),
            start_at_utc_iso=str(parsed_sched['start_at_utc']),
        )
        if SCHEDULER:
            SCHEDULER.add_job(job)
        await update.message.reply_text(
            f"Scheduled. Meeting time (UTC): {parsed_sched['schedule_at_utc']} | start trigger (UTC): {parsed_sched['start_at_utc']}"
        )
        return

    await update.message.reply_text(
        'Unknown command. Use:\n'
        '- join now <meeting_link> name <assistant> avatar <3d|female>\n'
        '- schedule <meeting_link> at YYYY-MM-DD HH:MM\n'
        '- status\n- stop\n- talk to los <agent>\n- los mode <suggest_actions|execute_with_approval|autonomous_mode>\n- email <message>\n- history\n- logout'
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # type: ignore
    email, bearer, state = _get_auth(update)
    if state != 'verified' or not email or not bearer:
        await update.message.reply_text('Authenticate first. Run: auth your@email.com')
        return

    file_obj = None
    filename = 'upload.bin'
    
    if update.message.document:
        file_obj = await update.message.document.get_file()
        filename = update.message.document.file_name or 'document.bin'
    elif update.message.photo:
        file_obj = await update.message.photo[-1].get_file()
        filename = 'photo.jpg'
        
    if not file_obj:
        return
        
    await update.message.reply_text('Downloading file...')
    file_bytes = await file_obj.download_as_bytearray()
    
    await update.message.reply_text('Uploading to Aria Data Vault...')
    ok, out = BACKEND.data_upload(email, bearer, bytes(file_bytes), filename)
    if ok:
        await update.message.reply_text(f'Upload success: {out}')
    else:
        await update.message.reply_text(f'Upload failed: {out}')


async def poll_automation_jobs_loop(app) -> None:
    backend_db_path = Path("data_vault/sqlite/aria_memory.db")
    while True:
        try:
            if not backend_db_path.exists():
                await asyncio.sleep(10)
                continue

            email_to_uids = {}
            with tg_conn() as c:
                c.row_factory = sqlite3.Row
                rows = c.execute("SELECT telegram_user_id, account_email FROM telegram_sessions WHERE auth_state='verified'").fetchall()
                for r in rows:
                    e = str(r["account_email"]).lower().strip()
                    if e not in email_to_uids:
                        email_to_uids[e] = []
                    email_to_uids[e].append(str(r["telegram_user_id"]))

            if not email_to_uids:
                await asyncio.sleep(10)
                continue

            now_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
            with sqlite3.connect(backend_db_path) as bc:
                bc.row_factory = sqlite3.Row
                jobs = bc.execute("SELECT * FROM automation_jobs WHERE status IN ('scheduled', 'sent')").fetchall()

            for job in jobs:
                job_id = str(job["id"])
                if has_notified_job(job_id):
                    continue

                schedule_at = str(job["schedule_at"] or "")
                status = str(job["status"] or "")
                created_by = str(job["created_by_email"] or "").lower().strip()

                is_due = (status == "sent")
                if not is_due and schedule_at:
                    try:
                        s_dt = datetime.fromisoformat(schedule_at.replace("Z", "+00:00"))
                        if s_dt.tzinfo is None:
                            s_dt = s_dt.replace(tzinfo=timezone.utc)
                        is_due = s_dt <= now_dt
                    except Exception:
                        pass
                        
                if not is_due:
                    continue

                target_uids = []
                try:
                    recs_str = job["recipients_json"]
                    if recs_str:
                        recs = json.loads(recs_str)
                        for r in recs:
                            re = str(r).lower().strip()
                            if re in email_to_uids:
                                target_uids.extend(email_to_uids[re])
                except Exception:
                    pass

                if not target_uids and created_by in email_to_uids:
                    target_uids.extend(email_to_uids[created_by])

                target_uids = list(set(target_uids))

                if target_uids:
                    subj = str(job["subject"] or "")
                    msg = str(job["message"] or "")
                    text = f"🔔 *Aria Reminder*\n\n*{subj}*\n\n{msg}"
                    for uid in target_uids:
                        try:
                            print(f"[Telegram Poller] Sending notification for job {job_id} to {uid}")
                            await app.bot.send_message(chat_id=int(uid), text=text, parse_mode="Markdown")
                        except Exception as e:
                            print(f"[Telegram Poller] Failed to send telegram notification: {e}")

                mark_job_notified(job_id)

        except Exception as e:
            print(f"Error in polling loop: {e}")

        await asyncio.sleep(10)

async def post_init(app) -> None:
    asyncio.create_task(poll_automation_jobs_loop(app))

def main() -> None:
    global SCHEDULER, APP
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

    globals()["Update"] = Update
    globals()["ContextTypes"] = ContextTypes

    parser = argparse.ArgumentParser()
    parser.add_argument('--account', required=True, help='Account email mapped in setup_bot.py')
    args = parser.parse_args()

    init_db()
    account = args.account.strip().lower()
    token = get_bot_token(account)
    if not token:
        raise SystemExit(f'No bot token mapped for {account}. Run: python telegram_agent/setup_bot.py')

    app = Application.builder().token(token).post_init(post_init).build()
    APP = app

    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('command', cmd_command))
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('logout', cmd_logout))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_document))

    SCHEDULER = MeetingScheduler(lambda job: asyncio.run(_run_scheduled_start(job)))
    SCHEDULER.start()

    print(f'Telegram agent running for account mapping: {account}')
    print('Use Ctrl+C to stop.')
    app.run_polling(close_loop=False)


if __name__ == '__main__':
    main()
