import json
import re
from datetime import datetime, timezone
from pathlib import Path


class MeetingIntelligence:
    def __init__(self):
        self._last_speaker = "Speaker 1"
        self._speaker_names = {}

    def diarize_segments(self, segments: list[dict]) -> list[dict]:
        out = []
        speaker = self._last_speaker
        prev_end = None
        for seg in segments or []:
            txt = (seg.get("text") or "").strip()
            if not txt:
                continue
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
            if prev_end is not None and (start - prev_end) > 2.5:
                speaker = "Speaker 2" if speaker == "Speaker 1" else "Speaker 1"
            prev_end = end
            out.append({
                "speaker": speaker,
                "start": start,
                "end": end,
                "text": txt,
            })
        self._last_speaker = speaker
        return out

    def assign_names(self, diarized: list[dict]) -> list[dict]:
        """
        Best-effort name assignment from spoken cues.
        If no name cues are found, keeps generic Speaker labels.
        """
        name_patterns = [
            re.compile(r"\b(?:i am|i'm|this is|my name is)\s+([A-Z][a-z]{2,20})\b", re.IGNORECASE),
            re.compile(r"\b([A-Z][a-z]{2,20})\s+here\b", re.IGNORECASE),
        ]

        for seg in diarized or []:
            speaker = str(seg.get("speaker", "")).strip()
            txt = str(seg.get("text", "")).strip()
            if not speaker or not txt:
                continue
            if speaker in self._speaker_names:
                continue
            for pat in name_patterns:
                m = pat.search(txt)
                if m:
                    name = m.group(1).strip()
                    self._speaker_names[speaker] = name.capitalize()
                    break

        out = []
        for seg in diarized or []:
            speaker = str(seg.get("speaker", "")).strip() or "Speaker"
            display = self._speaker_names.get(speaker, speaker)
            row = dict(seg)
            row["speaker"] = display
            out.append(row)
        return out

    def speaker_transcript_text(self, diarized: list[dict]) -> str:
        lines = []
        for seg in diarized or []:
            speaker = str(seg.get("speaker", "Speaker")).strip() or "Speaker"
            txt = str(seg.get("text", "")).strip()
            if not txt:
                continue
            lines.append(f"{speaker}: {txt}")
        return "\n".join(lines)

    def merge_with_assistant(self, diarized: list[dict], assistant_events: list[dict]) -> list[dict]:
        merged = []
        for seg in diarized or []:
            txt = str(seg.get("text", "")).strip()
            if not txt:
                continue
            merged.append(
                {
                    "speaker": str(seg.get("speaker", "Speaker")).strip() or "Speaker",
                    "start": float(seg.get("start", 0.0) or 0.0),
                    "end": float(seg.get("end", 0.0) or 0.0),
                    "text": txt,
                }
            )
        for ev in assistant_events or []:
            txt = str(ev.get("text", "")).strip()
            if not txt:
                continue
            st = float(ev.get("start", 0.0) or 0.0)
            en = float(ev.get("end", st + 0.01) or (st + 0.01))
            merged.append(
                {
                    "speaker": str(ev.get("speaker", "Assistant")).strip() or "Assistant",
                    "start": st,
                    "end": en,
                    "text": txt,
                }
            )
        merged.sort(key=lambda x: (float(x.get("start", 0.0) or 0.0), str(x.get("speaker", ""))))
        return merged

    def write_artifacts(self, meeting_dir: str, segments: list[dict], diarized: list[dict]):
        p = Path(meeting_dir)
        p.mkdir(parents=True, exist_ok=True)
        (p / "segments.json").write_text(json.dumps(segments or [], indent=2), encoding="utf-8")
        (p / "diarization.json").write_text(json.dumps(diarized or [], indent=2), encoding="utf-8")


def is_email_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    patterns = [
        r"\b(send|mail|email)\b.*\b(now|today|tomorrow|am|pm|\d{1,2}:\d{2}|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(send)\s+(an?\s+)?(email|mail)\b",
        r"\b(send\s+email\s+to)\b",
        r"\b(email\s+to)\b",
        r"\b(schedule)\s+(an?\s+)?(email|mail)\b",
        r"\b(remind me|set a reminder|reminder)\b",
    ]
    return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)


def parse_email_intent(text: str) -> dict:
    t = (text or "").strip()
    lower = t.lower()
    explicit_send_now = any(k in lower for k in ["send now", "right now", "immediately", "asap", "now"])
    has_schedule_cue = any(k in lower for k in ["tomorrow", "today", " at ", " am", " pm", "schedule", "on monday", "on tuesday", "on wednesday", "on thursday", "on friday", "on saturday", "on sunday"])
    mode = "ai_schedule" if has_schedule_cue and not explicit_send_now else "send_now"
    recipients = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t)
    subject = "Aria Message"
    explicit_subject = False
    m = re.search(r"subject\s*(?:is|:)\s*(.+?)(?:\s+body\s*(?:is|:)|$)", t, flags=re.IGNORECASE)
    if m:
        subject = m.group(1).strip(" .")
        explicit_subject = True
    body = ""
    explicit_body = False
    bm = re.search(r"body\s*(?:is|:)\s*(.+)$", t, flags=re.IGNORECASE)
    if bm:
        body = bm.group(1).strip()
        explicit_body = bool(body)
    if not body:
        # Build polished body from intent when user does not provide explicit body.
        draft = re.sub(r"\bhey\s+\w+\b", "", t, flags=re.IGNORECASE).strip()
        draft = re.sub(
            r"\b(can you|could you|please|send( an?)?( email| mail)|schedule( an?)?( email| mail)|by sending( an?)?( email| mail))\b",
            " ",
            draft,
            flags=re.IGNORECASE,
        )
        # Remove recipient labels ("to maya", "to raj@gmail.com") from body text.
        draft = re.sub(r"\bto\s+[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", " ", draft, flags=re.IGNORECASE)
        draft = re.sub(r"\bto\s+[A-Za-z][A-Za-z ]{0,40}\b", " ", draft, flags=re.IGNORECASE)
        # Remove timing transport words; keep purpose.
        draft = re.sub(r"\b(right now|now|today|tomorrow|at\s+\d{1,2}(?::\d{2})?\s*(am|pm)?)\b", " ", draft, flags=re.IGNORECASE)
        draft = re.sub(r"\s+", " ", draft).strip(" .,:;-")

        if not draft:
            draft = "This is a quick reminder from Aria."
        if not draft.endswith((".", "!", "?")):
            draft = f"{draft}."
        draft = draft[0].upper() + draft[1:] if draft else draft

        body = (
            "Hi,\n\n"
            f"{draft}\n\n"
            "Regards,\n"
            "Aria"
        )
    if body.strip().lower() in {"hi?", "hi", "hello?", "hello"}:
        body = "Hi,\n\nThis is a quick reminder from Aria.\n\nRegards,\nAria"

    if subject == "Aria Message":
        if "join the meeting" in lower:
            subject = "Join the meeting now"
        elif "remind" in lower or "reminder" in lower:
            subject = "Reminder from Aria"
        elif "follow up" in lower:
            subject = "Follow-up"
        else:
            subject = "Quick update"
    return {
        "mode": mode,
        "recipients": recipients,
        "subject": subject,
        "body": body,
        "explicit_subject": explicit_subject,
        "explicit_body": explicit_body,
        "schedule_at": None,
        "instruction": t,
    }


def is_go_ahead(text: str) -> bool:
    t = (text or "").lower().strip()
    return "go ahead" in t or "go-ahead" in t
