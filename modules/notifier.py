import os
import json
from datetime import datetime
from config import MEMORY_DIR


class Notifier:
    def __init__(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)

    def save_meeting(self, transcript, summary, notes, meeting_url="", segments=None, diarization=None, speaker_transcript=None):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        meeting_dir = os.path.join(MEMORY_DIR, f"meeting_{timestamp}")
        os.makedirs(meeting_dir, exist_ok=True)
        owner_email = (os.getenv("ARIA_PROFILE_EMAIL", "") or "").strip().lower()

        with open(os.path.join(meeting_dir, "transcript.txt"), "w", encoding="utf-8") as f:
            f.write(transcript)

        with open(os.path.join(meeting_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write(f"# Meeting Summary\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            if meeting_url:
                f.write(f"**URL:** {meeting_url}\n")
            f.write("\n")
            f.write(summary)

        with open(os.path.join(meeting_dir, "notes.json"), "w", encoding="utf-8") as f:
            json.dump(
                {"timestamp": timestamp, "url": meeting_url, "notes": notes, "owner_email": owner_email},
                f,
                indent=2,
            )

        if segments is not None:
            with open(os.path.join(meeting_dir, "segments.json"), "w", encoding="utf-8") as f:
                json.dump(segments, f, indent=2)

        if diarization is not None:
            with open(os.path.join(meeting_dir, "diarization.json"), "w", encoding="utf-8") as f:
                json.dump(diarization, f, indent=2)
        if speaker_transcript is not None:
            with open(os.path.join(meeting_dir, "speaker_transcript.txt"), "w", encoding="utf-8") as f:
                f.write(speaker_transcript)

        return meeting_dir

    def print_summary(self, summary):
        print("\n" + "=" * 60)
        print("ARIA — MEETING SUMMARY")
        print("=" * 60)
        print(summary)
        print("=" * 60 + "\n")
