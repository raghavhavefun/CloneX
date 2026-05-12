import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


@dataclass
class ScheduledMeetingJob:
    telegram_user_id: str
    meeting_url: str
    assistant_name: str
    avatar_mode: str
    start_at_utc_iso: str


class MeetingScheduler:
    def __init__(self, on_run: Callable[[ScheduledMeetingJob], None]):
        self._on_run = on_run
        self._jobs: list[ScheduledMeetingJob] = []
        self._lock = threading.Lock()
        self._stop = False
        self._t = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._t.start()

    def shutdown(self) -> None:
        self._stop = True

    def add_job(self, job: ScheduledMeetingJob) -> None:
        with self._lock:
            self._jobs.append(job)

    def _loop(self) -> None:
        while not self._stop:
            due: list[ScheduledMeetingJob] = []
            now = datetime.now(timezone.utc)
            with self._lock:
                keep: list[ScheduledMeetingJob] = []
                for j in self._jobs:
                    try:
                        t = datetime.fromisoformat(j.start_at_utc_iso)
                        if t <= now:
                            due.append(j)
                        else:
                            keep.append(j)
                    except Exception:
                        continue
                self._jobs = keep
            for j in due:
                try:
                    self._on_run(j)
                except Exception:
                    pass
            time.sleep(4)
