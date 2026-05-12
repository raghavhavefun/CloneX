import json
import os
from typing import Any

from groq import Groq


ALLOWED_OPS = [
    "stop_share",
    "stop_video",
    "open_url",
    "search_youtube",
    "switch_tab",
    "scroll",
    "play",
    "pause",
    "close_tab",
]


class ActionAgent:
    """
    Agentic planner: maps natural command text into an ordered action plan.
    Execution is handled by MeetingJoiner so this remains pure planning.
    """

    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key) if api_key else None
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    def plan(self, user_text: str, platform: str, current_url: str) -> dict[str, Any] | None:
        if not self.client:
            return None
        text = (user_text or "").strip()
        if not text:
            return None
        lower = text.lower()

        # Deterministic fast-path for core meeting controls to avoid LLM drift.
        deterministic_steps = []
        if ("stop sharing" in lower) or ("stop share" in lower) or ("turn share off" in lower):
            deterministic_steps.append({"op": "stop_share", "args": {}})
        if ("stop video" in lower) or ("turn off video" in lower) or ("camera off" in lower):
            deterministic_steps.append({"op": "stop_video", "args": {}})
        if ("pause video" in lower) or ("stop the video" in lower):
            deterministic_steps.append({"op": "pause", "args": {}})
        if deterministic_steps:
            return {"summary": "Executing deterministic meeting controls", "steps": deterministic_steps}

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a UI action planner. Return strict JSON with keys: "
                            "should_execute (bool), summary (string), steps (array). "
                            "Each step object keys: op, args. "
                            f"Allowed ops only: {', '.join(ALLOWED_OPS)}. "
                            "Use ordered steps when user asks multiple actions in sequence. "
                            "Do not use open_url/search_youtube unless user explicitly says open/search/go to/play on youtube. "
                            "If user asks normal Q&A and not control action, should_execute=false."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Platform: {platform}\n"
                            f"Current URL: {current_url}\n"
                            f"Command: {text}\n"
                            "Return JSON only."
                        ),
                    },
                ],
                max_tokens=700,
            )
            raw = json.loads(completion.choices[0].message.content or "{}")
            if not bool(raw.get("should_execute")):
                return None
            steps = raw.get("steps") or []
            filtered = []
            for s in steps:
                op = str(s.get("op", "")).strip()
                if op not in ALLOWED_OPS:
                    continue
                args = s.get("args", {})
                if not isinstance(args, dict):
                    args = {}
                filtered.append({"op": op, "args": args})
            if not filtered:
                return None
            return {
                "summary": str(raw.get("summary", "Executing requested actions")).strip(),
                "steps": filtered,
            }
        except Exception:
            return None
