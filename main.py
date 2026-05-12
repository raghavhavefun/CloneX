"""
Project Aria — AI Meeting Executive Assistant
Phase 1: Audio capture + transcription + live Q&A + post-meeting summary

Usage:
    python main.py                          # Mic-only mode (no browser)
    python main.py <meeting_url>            # Auto-join Google Meet
    python main.py --list-devices           # Show available audio input devices
"""

import sys
import signal
import threading
import time
import asyncio
import os
import requests
import re
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.audio_capture import AudioCapture
from modules.transcriber import Transcriber
from modules.brain import Brain
from modules.notifier import Notifier
from modules.meeting_joiner import MeetingJoiner
from modules.voice import Voice
from modules.avatar import Avatar
from modules.bridge_3d import Bridge3D
from modules.response_gate import ResponseGate
from modules.meeting_intelligence import MeetingIntelligence, is_email_intent, parse_email_intent, is_go_ahead
from modules.action_agent import ActionAgent
from modules.platform_adapter import chrome_user_data_root, kill_browser_processes, audio_device_priority
from config import VOICE_ENABLED, AVATAR_ENABLED, RESPONSE_MODE, STT_MODEL_SIZE, GROQ_API_KEY


def _safe_profile_slug(email: str) -> str:
    cleaned = (email or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9@._-]+", "_", cleaned)
    cleaned = cleaned.replace("@", "_at_")
    return cleaned[:120] or "default_profile"

def _assistant_aliases(name: str) -> list[str]:
    raw = (name or "").strip().lower()
    if not raw:
        return ["assistant"]
    cleaned = re.sub(r"[^a-z0-9\s']", " ", raw)
    tokens = [t for t in cleaned.split() if t]
    aliases = {"assistant"}
    if tokens:
        aliases.add(tokens[0])
    for t in tokens:
        # Keep short alpha nickname-like tokens (e.g. "ra").
        if t.isalpha() and 2 <= len(t) <= 4:
            aliases.add(t)
    # also allow full phrase
    aliases.add(cleaned.strip())
    return sorted(a for a in aliases if a)


def _prompt_profile_email() -> str:
    while True:
        entered = input("\nEnter your Google email for signed-in Chrome profile: ").strip().lower()
        if "@" in entered and "." in entered.split("@")[-1]:
            return entered
        print("Please enter a valid email address.")


def _resolve_existing_chrome_profile(email: str) -> tuple[str | None, str | None]:
    root = chrome_user_data_root()
    if root is None:
        return None, None
    if not root.exists():
        return None, None
    candidates = [p for p in root.iterdir() if p.is_dir() and (p.name == "Default" or p.name.startswith("Profile"))]
    email_l = (email or "").strip().lower()

    # Prefer Local State profile cache mapping first.
    try:
        local_state = root / "Local State"
        if local_state.exists():
            data = json.loads(local_state.read_text(encoding="utf-8", errors="ignore"))
            info_cache = (((data or {}).get("profile") or {}).get("info_cache") or {})
            for profile_name, profile_meta in info_cache.items():
                user_name = str((profile_meta or {}).get("user_name", "")).strip().lower()
                if user_name == email_l:
                    prof_path = root / profile_name
                    if prof_path.exists():
                        return str(root), profile_name
    except Exception:
        pass

    for p in candidates:
        pref = p / "Preferences"
        if not pref.exists():
            continue
        try:
            data = json.loads(pref.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        account_info = data.get("account_info") or []
        for acc in account_info:
            if str(acc.get("email", "")).strip().lower() == email_l:
                return str(root), p.name
    return None, None


def _prepare_cloned_chrome_profile(email: str, source_user_data_dir: str, source_profile_dir: str) -> tuple[str, str]:
    """
    Clone the detected signed-in Chrome profile into a dedicated automation profile folder.
    This avoids lockups when Playwright opens the live Chrome User Data directory.
    """
    slug = _safe_profile_slug(email)
    runtime_root = Path("data_vault") / "chrome_profiles_runtime" / slug
    target_user_data_dir = runtime_root
    target_profile_dir = "Default"
    target_profile_path = target_user_data_dir / target_profile_dir

    src_root = Path(source_user_data_dir)
    src_profile = src_root / source_profile_dir
    target_user_data_dir.mkdir(parents=True, exist_ok=True)

    local_state_src = src_root / "Local State"
    local_state_dst = target_user_data_dir / "Local State"
    # Always refresh clone every run so sign-in state stays current.
    if target_profile_path.exists():
        shutil.rmtree(target_profile_path, ignore_errors=True)
    if local_state_dst.exists():
        try:
            local_state_dst.unlink()
        except Exception:
            pass
    if local_state_src.exists():
        shutil.copy2(local_state_src, local_state_dst)
    shutil.copytree(src_profile, target_profile_path, dirs_exist_ok=True)
    print("[System] Runtime profile refreshed from local Chrome profile.")

    return str(target_user_data_dir.resolve()), target_profile_dir


class Aria:
    def __init__(self, meeting_url=None, audio_device=None, assistant_name="Aria", audio=None, transcriber=None, initial_avatar="3d"):
        self.meeting_url = meeting_url
        self.audio = audio if audio else AudioCapture(device_index=audio_device)
        self.transcriber = transcriber if transcriber else Transcriber(model_size=STT_MODEL_SIZE)
        self.brain = Brain()
        self.brain.set_wake_word(f"hey {assistant_name.lower()}")
        self.response_gate = ResponseGate(
            assistant_name=assistant_name,
            wake_prefix="hey",
            mode=RESPONSE_MODE,
            aliases=_assistant_aliases(assistant_name),
        )
        self.voice = Voice()
        self.avatar = Avatar(initial_mode=initial_avatar) if AVATAR_ENABLED else None
        self.bridge_3d = Bridge3D()
        if self.avatar:
            self.bridge_3d.on_change_avatar = self._on_change_avatar  # type: ignore
            self._set_voice_for_avatar(initial_avatar)
            
        self.assistant_name = assistant_name
        self.notifier = Notifier()
        self.joiner = MeetingJoiner(close_chrome_before_launch=True, user_data_dir=os.getenv("ARIA_CHROME_USER_DATA_DIR", "").strip())
        self.action_agent = ActionAgent(api_key=GROQ_API_KEY)
        self.loop = None # Will be set by the main event loop
        self._running = False
        self._brain_thread = None
        self.meeting_intelligence = MeetingIntelligence()
        self.pending_email_command = None
        self._last_email_intent_sig = ""
        self._last_email_intent_at = 0.0
        self._last_email_exec_at = 0.0
        self.assistant_events = []
        self._session_mono_start = None

    def _set_voice_for_avatar(self, avatar_mode: str):
        # Female avatar gets female voice; others keep current default male voice.
        if avatar_mode == "female":
            self.voice.set_voice("en-US-JennyNeural")
        else:
            self.voice.set_voice("en-US-GuyNeural")

    def _on_change_avatar(self, avatar_mode: str):
        try:
            if self.avatar:
                self.avatar.change_image(avatar_mode)
            self._set_voice_for_avatar(avatar_mode)
        except Exception as e:
            print(f"[Aria] Avatar/voice switch error: {e}")

    def start(self):
        print(f"\n{'='*50}")
        print(f"  {self.assistant_name} is now active")
        print(f"  Wake word: '{self.brain.wake_word}'")
        print(f"  Press Ctrl+C to end the meeting")
        print(f"{'='*50}\n")

        self._running = True
        self._session_mono_start = time.monotonic()
        if not self.audio._running:
            self.audio.start()
        if not self.transcriber._running:
            self.transcriber.start(self.audio)
        if self.avatar:
            self.avatar.start()

        self._brain_thread = threading.Thread(target=self._brain_loop, daemon=True)
        self._brain_thread.start()

    def _try_queue_email_command(self, text: str) -> bool:
        if not is_email_intent(text):
            return False
        norm = re.sub(r"\s+", " ", (text or "").strip().lower())
        now_mono = time.monotonic()
        if self._last_email_intent_sig == norm and (now_mono - self._last_email_intent_at) < 45:
            print(f"[{self.assistant_name}] Duplicate email intent ignored (cooldown).")
            return True
        cmd = parse_email_intent(text)
        # Recipient may come from Connects (name->email) or fallback to sender's own email in backend.
        expires = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(minutes=2)
        self.pending_email_command = {**cmd, "expires_at": expires.isoformat()}
        self._last_email_intent_sig = norm
        self._last_email_intent_at = now_mono
        print(f"[{self.assistant_name}] Email intent detected. Scheduling now...")
        self._execute_pending_email_command()
        return True

    def _try_save_connect(self, text: str) -> bool:
        t = (text or "").strip().lower()
        if "save connect" not in t:
            return False
        import re
        m = re.search(r"save connect\s+([a-zA-Z\s]+)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", t, re.IGNORECASE)
        if not m:
            return False
        name = m.group(1).strip().title()
        email = m.group(2).strip().lower()
        sender = os.getenv("ARIA_PROFILE_EMAIL", "").strip().lower()
        if not sender:
            return False
        try:
            import requests
            r = requests.post(
                "http://127.0.0.1:8001/api/connects",
                json={"name": name, "email": email},
                headers={"X-User-Email": sender},
                timeout=12
            )
            if r.status_code < 400:
                msg = f"I have saved {name} to your connects."
                print(f"[{self.assistant_name}] {msg}")
                self.voice.speak(msg, avatar=self.avatar, bridge_3d=self.bridge_3d)
            else:
                self.voice.speak("I couldn't save the connect.", avatar=self.avatar, bridge_3d=self.bridge_3d)
        except Exception as e:
            print(f"[{self.assistant_name}] Failed to save connect: {e}")
        return True

    def _execute_pending_email_command(self) -> bool:
        cmd = self.pending_email_command
        if not cmd:
            print(f"[{self.assistant_name}] No pending email command.")
            return True
        if (time.monotonic() - self._last_email_exec_at) < 25:
            print(f"[{self.assistant_name}] Email action cooldown active. Skipping duplicate send.")
            self.pending_email_command = None
            return True
        try:
            if datetime.fromisoformat(cmd["expires_at"].replace("Z", "+00:00")) < datetime.utcnow().replace(tzinfo=timezone.utc):
                self.pending_email_command = None
                print(f"[{self.assistant_name}] Pending email command expired.")
                return True
        except Exception:
            pass

        sender = os.getenv("ARIA_PROFILE_EMAIL", "").strip().lower()
        if not sender or "@" not in sender:
            print(f"[{self.assistant_name}] ARIA_PROFILE_EMAIL is missing, cannot authorize send from signed-in profile.")
            return True

        # Always send instruction so backend Groq parser can resolve names,
        # draft subject/body, and parse schedule time.
        # Only override subject/message if user explicitly provided them.
        has_explicit_recipients = bool(cmd.get("recipients", []))
        payload = {
            "requester_email": sender,
            "recipients": ",".join(cmd.get("recipients", [])),
            "instruction": cmd.get("instruction", ""),
            "mode": "ai_schedule" if not has_explicit_recipients and not cmd.get("explicit_subject") else cmd.get("mode", "send_now"),
            "subject": cmd.get("subject", "") if cmd.get("explicit_subject") else "",
            "message": cmd.get("body", "") if cmd.get("explicit_body") else "",
            "bulk_mode": "same_for_all",
            "schedule_at": cmd.get("schedule_at"),
            "timezone": "UTC",
        }
        audit_mode = str(payload.get("mode", "send_now"))
        audit_recips = payload.get("recipients", "") or "(auto)"
        audit_subject = (payload.get("subject", "") or "(ai-draft)").strip()
        audit_msg = (payload.get("message", "") or "").strip()
        print(
            f"[EmailAudit] prepare mode={audit_mode} requester={sender} recipients={audit_recips} "
            f"subject={audit_subject!r} explicit_body={bool(audit_msg)}"
        )
        try:
            is_reminder = "remind me" in cmd.get("instruction", "").lower()
            if is_reminder:
                pre_line = "I have set that up for you. You will be notified at the specified time."
            else:
                pre_line = "Sending the message now." if payload["mode"] == "send_now" else "Scheduling that message now."
            try:
                self.voice.speak(pre_line, avatar=self.avatar, bridge_3d=self.bridge_3d)
            except Exception:
                pass
            r = requests.post("http://127.0.0.1:8001/api/automation/schedule", json=payload, timeout=12)
            if r.status_code >= 400:
                print(f"[{self.assistant_name}] Email scheduling failed: {r.text[:300]}")
                print(f"[EmailAudit] result status=failed http={r.status_code}")
                try:
                    detail = ""
                    try:
                        detail = (r.json() or {}).get("detail", "")
                    except Exception:
                        detail = ""
                    if "connects" in str(detail).lower():
                        self.voice.speak("I could not find that name in your contacts. Please add them in the dashboard.", avatar=self.avatar, bridge_3d=self.bridge_3d)
                    else:
                        self.voice.speak("I could not send that message. Please check sender setup.", avatar=self.avatar, bridge_3d=self.bridge_3d)
                except Exception:
                    pass
                self.pending_email_command = None
                return True
            confirm_line = "Email sent."
            try:
                data = r.json()
                items = data.get("items") or []
                if items:
                    to_addr = (items[0].get("recipients") or [""])[0]
                    when = items[0].get("schedule_at", "")
                    print(f"[EmailAudit] result status=accepted items={len(items)} first_to={to_addr} schedule_at={when}")
                    print(f"[{self.assistant_name}] Scheduled email -> to={to_addr} at={when}")
                    if cmd.get("mode") == "send_now":
                        confirm_line = f"I sent the message to {to_addr}."
                    else:
                        confirm_line = f"I scheduled the message to {to_addr}."
            except Exception:
                pass
            print(f"[{self.assistant_name}] {confirm_line}")
            try:
                self.voice.speak(confirm_line, avatar=self.avatar, bridge_3d=self.bridge_3d)
            except Exception:
                pass
            print(f"[{self.assistant_name}] Email automation accepted and logged.")
            self._last_email_exec_at = time.monotonic()
            self.pending_email_command = None
        except Exception as e:
            print(f"[{self.assistant_name}] Email automation backend unavailable: {e}")
        return True

    def _brain_loop(self):
        while self._running:
            try:
                text = self.transcriber.get_latest(timeout=0.5)
                if not text:
                    continue

                self.brain.add_segment(text)

                if self._try_save_connect(text):
                    continue
                if self._try_queue_email_command(text):
                    continue
                if self.pending_email_command and is_go_ahead(text):
                    self._execute_pending_email_command()
                    continue

                should_respond, reason, score = self.response_gate.should_respond(text)
                if should_respond:
                    if reason == "smart_score":
                        print(f"[{self.assistant_name}] Direct-address detected (score={score:.2f})")
                    else:
                        print(f"[{self.assistant_name}] Wake phrase detected.")

                    # Agentic browser/meeting execution layer (additive).
                    if self.loop and self.joiner and self.joiner.page:
                        plan = self.action_agent.plan(
                            user_text=text,
                            platform=getattr(self.joiner, "current_platform", "unknown"),
                            current_url=getattr(self.joiner.page, "url", ""),
                        )
                        if plan and plan.get("steps"):
                            print(f"[{self.assistant_name}] Agentic action plan: {plan.get('summary', 'Executing actions')}")
                            try:
                                fut = asyncio.run_coroutine_threadsafe(
                                    self.joiner.execute_agentic_steps(plan["steps"]),
                                    self.loop
                                )
                                # Non-blocking execution to keep transcription/reply loop responsive.
                                print(f"[{self.assistant_name}] Action execution completed.")
                                continue
                            except Exception as e:
                                print(f"[{self.assistant_name}] Action execution fallback to normal response: {e}")

                    print(f"\n[{self.assistant_name}] Responding...")
                    answer = self.brain.answer_question(text)
                    
                    # Check for actions like [ACTION: search: query]
                    import re
                    action_match = re.search(r'\[ACTION: (.*?): (.*?)\]', answer)
                    clean_answer = re.sub(r'\[ACTION: .*?\]', '', answer).strip()
                    
                    print(f"[{self.assistant_name}] {clean_answer}\n")
                    try:
                        now_off = (time.monotonic() - self._session_mono_start) if self._session_mono_start else 0.0
                    except Exception:
                        now_off = 0.0
                    self.assistant_events.append(
                        {
                            "speaker": self.assistant_name,
                            "start": float(now_off),
                            "end": float(now_off) + 0.01,
                            "text": clean_answer,
                        }
                    )
                    if VOICE_ENABLED:
                        self.voice.speak(clean_answer, avatar=self.avatar, bridge_3d=self.bridge_3d)

                    if action_match:
                        action_type = action_match.group(1).strip()
                        query = action_match.group(2).strip()
                        try:
                            # Schedule the async web action on the main event loop
                            if self.loop:
                                asyncio.run_coroutine_threadsafe(
                                    self.joiner.perform_web_action(action_type, query),
                                    self.loop
                                )
                            else:
                                print("[Aria] Event loop not ready for web action.")
                        except Exception as e:
                            print(f"[Aria] Could not perform web action: {e}")
            except Exception as e:
                print(f"[Aria] Brain loop error (skipped): {e}")

    def stop(self):
        print(f"\n[{self.assistant_name}] Meeting ended. Wrapping up...")
        self._running = False
        if self.avatar:
            self.avatar.stop()

        self.transcriber.stop()
        self.audio.stop()

        transcript = self.transcriber.get_full_transcript()
        if not transcript.strip():
            print(f"[{self.assistant_name}] No transcript captured. Nothing to save.")
            return

        print(f"[{self.assistant_name}] Generating meeting summary (this takes ~10s)...")
        summary = self.brain.generate_summary(transcript)
        self.notifier.print_summary(summary)

        segments = []
        diarized = []
        speaker_transcript = ""
        try:
            segments = self.transcriber.get_segments()
            diarized = self.meeting_intelligence.diarize_segments(segments)
            diarized = self.meeting_intelligence.assign_names(diarized)
            dialogue_rows = self.meeting_intelligence.merge_with_assistant(diarized, self.assistant_events)
            speaker_transcript = self.meeting_intelligence.speaker_transcript_text(dialogue_rows)
        except Exception as e:
            print(f"[{self.assistant_name}] Meeting intelligence error (non-fatal): {e}")

        saved = self.notifier.save_meeting(
            transcript=transcript,
            summary=summary,
            notes=self.brain.notes,
            meeting_url=self.meeting_url or "",
            segments=segments,
            diarization=diarized,
            speaker_transcript=speaker_transcript,
        )
        print(f"[{self.assistant_name}] Files saved → {saved}")


def list_audio_devices():
    capture = AudioCapture()
    devices = capture.list_devices()
    capture.pa.terminate()
    print("\nAvailable audio input devices:")
    for idx, name in devices:
        print(f"  [{idx}] {name}")
    print()


def run_mic_only(aria: Aria):
    aria.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        aria.stop()


async def run_with_meeting(aria: Aria):
    # Store the main loop so background threads can use it
    aria.loop = asyncio.get_running_loop()  # type: ignore
    
    print(f"[System] Meeting URL input: {aria.meeting_url}")
    try:
        # 1. Join the meeting FIRST while the CPU is quiet
        # This makes the browser launch much faster
        await aria.joiner.join_meeting(aria.meeting_url, assistant_name=aria.assistant_name)
    except Exception as e:
        print(f"[System] Meeting join failed: {e}")
        print("[System] Continuing in mic-only mode.")
    
    # 2. NOW start the heavy AI lifting (Ears, Brain, Face)
    aria.start()
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await aria.joiner.leave_meeting()
        aria.stop()


def main():
    args = sys.argv[1:]

    if "--list-devices" in args:
        list_audio_devices()
        return
    # Non-interactive values (used by backend/dashboard orchestration).
    non_interactive = os.getenv("ARIA_NON_INTERACTIVE", "").strip().lower() in {"1", "true", "yes"}
    env_meeting_url = os.getenv("ARIA_MEETING_URL", "").strip()
    env_profile_email = os.getenv("ARIA_PROFILE_EMAIL", "").strip().lower()
    env_audio_device = os.getenv("ARIA_AUDIO_DEVICE_ID", "").strip()
    env_assistant_name = os.getenv("ARIA_ASSISTANT_NAME", "").strip()
    env_avatar = os.getenv("ARIA_AVATAR_MODE", "").strip().lower()

    meeting_url = env_meeting_url or (args[0] if args else None)
    
    print(f"\n{'='*50}")
    print("  Welcome to Project Aria")
    print(f"{'='*50}\n")

    if non_interactive:
        if not env_profile_email or "@" not in env_profile_email:
            print("[System] ARIA_PROFILE_EMAIL is required in non-interactive mode.")
            return
        profile_email = env_profile_email
    else:
        profile_email = _prompt_profile_email()
    # Ensure profile copy reads fully flushed browser state.
    print("[System] Preparing Chrome profile and forcing Chrome shutdown...")
    kill_browser_processes()
    existing_root, existing_profile = _resolve_existing_chrome_profile(profile_email)
    print(f"[System] Chrome profile detect root={existing_root} profile={existing_profile}")
    if existing_root and existing_profile:
        try:
            cloned_root, cloned_profile = _prepare_cloned_chrome_profile(profile_email, existing_root, existing_profile)
            os.environ["ARIA_CHROME_USER_DATA_DIR"] = cloned_root
            os.environ["ARIA_CHROME_PROFILE_DIR"] = cloned_profile
            print(f"[System] Found existing Chrome signed profile: {existing_profile}")
            print("[System] Using cloned runtime profile for automation stability.")
        except Exception as e:
            print(f"[System] Clone profile failed: {e}")
            print("[System] Aborting session start to avoid launching an empty/autonomous browser profile.")
            print("[System] Fix: close all Chrome windows, sign in once in normal Chrome, then retry.")
            return
    else:
        print("[System] No signed-in local Chrome profile found for that email.")
        print("[System] Please sign in to that Google account in normal Chrome first, close Chrome, then run main.py again.")
        return
    os.environ["ARIA_PROFILE_EMAIL"] = profile_email
    print(f"[System] Using signed-in Chrome profile: {profile_email}")
    print(f"[System] User data dir: {os.environ.get('ARIA_CHROME_USER_DATA_DIR', '')}")

    # 1. Collect Audio Device FIRST
    skip_audio_enum = os.getenv("ARIA_SKIP_AUDIO_ENUM", "false").strip().lower() in {"1", "true", "yes"}
    devices = []
    valid_ids = []
    if not (non_interactive and skip_audio_enum):
        capture = AudioCapture()
        devices = capture.list_devices()
        valid_ids = [d[0] for d in devices]
        capture.pa.terminate()

        print("\nAvailable audio input devices:")
        for idx, name in devices:
            print(f"  [{idx}] {name}")
        print()
    
    def _auto_pick_vb_device():
        # Prefer VB-CABLE style loopback inputs for meeting audio capture.
        ranked = sorted(devices, key=lambda x: (audio_device_priority(x[1]), x[0]))
        return ranked[0][0] if ranked else None

    audio_device = None
    if non_interactive:
        if env_audio_device and valid_ids:
            try:
                candidate = int(env_audio_device)
                if candidate in valid_ids:
                    audio_device = candidate
            except ValueError:
                pass
        if audio_device is None:
            audio_device = _auto_pick_vb_device()
        if audio_device is None and skip_audio_enum:
            print("[System] Skipping audio enumeration in non-interactive mode; using default input device.")
        elif audio_device is None:
            print("[System] Could not auto-select an audio input device.")
            return
        else:
            print(f"[System] Auto-selected audio device ID: {audio_device}")
    else:
        while audio_device is None:
            raw_input = input("Select the audio device ID you want to use (e.g. 1): ").strip()
            if raw_input:
                try:
                    candidate = int(raw_input)
                    if candidate in valid_ids:
                        audio_device = candidate
                    else:
                        print(f"ID {candidate} is not in the available list. Please select a valid input device.")
                except ValueError:
                    print("Please enter a valid number.")

    # 2. Collect Assistant Name SECOND
    if non_interactive:
        assistant_name = env_assistant_name or "Evan"
        initial_avatar = "female" if env_avatar == "female" else "3d"
        print(f"[System] Assistant name: {assistant_name}")
        print(f"[System] Avatar mode: {initial_avatar}")
    else:
        print("\nHow would you like to set the assistant's name?")
        print("1. Type it\n2. Speak it")
        choice = input("Select (1 or 2): ")
        
        assistant_name = "Evan"
        if choice == "2":
            print("\n[System] Listening for name...")
            # (Simplified for now to keep it fast)
            assistant_name = "Evan"
        else:
            assistant_name = input("\nPlease type the assistant's name: ").strip()
            if not assistant_name: assistant_name = "Evan"

        print("\nWhich avatar would you like to start with?")
        print("1. 3D Generated Avatar (Default)")
        print("2. Female Avatar")
        avatar_choice = input("Select (1 or 2): ").strip()
        if avatar_choice == "2":
            initial_avatar = "female"
        else:
            initial_avatar = "3d"

    print(f"\n[System] Setup complete. Powering up {assistant_name}...")
    print("-" * 30)

    # 3. NOW start the heavy lifting
    audio = AudioCapture(device_index=audio_device)
    transcriber = Transcriber(model_size=STT_MODEL_SIZE)
    aria = Aria(meeting_url=meeting_url, audio_device=audio_device, assistant_name=assistant_name, audio=audio, transcriber=transcriber, initial_avatar=initial_avatar)

    def handle_signal(sig, frame):
        aria.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if meeting_url:
        asyncio.run(run_with_meeting(aria))
    else:
        run_mic_only(aria)

if __name__ == "__main__":
    main()
