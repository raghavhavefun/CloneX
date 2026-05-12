import re


class ResponseGate:
    """
    Decides if a transcript segment is actually addressed to the assistant.
    Modes:
    - strict: require exact wake phrase ("hey <name>")
    - smart: score direct-address signals; can still honor strict wake phrase
    """

    def __init__(self, assistant_name: str, wake_prefix: str = "hey", mode: str = "strict", aliases: list[str] | None = None):
        self.assistant_name = (assistant_name or "aria").strip().lower()
        self.wake_prefix = (wake_prefix or "hey").strip().lower()
        self.mode = (mode or "strict").strip().lower()
        self.aliases = [a.strip().lower() for a in (aliases or []) if (a or "").strip()]
        self._compile_patterns()

    def _compile_patterns(self):
        all_names = [self.assistant_name] + self.aliases
        unique_names = []
        seen = set()
        for n in all_names:
            if n and n not in seen:
                seen.add(n)
                unique_names.append(n)
        names_alt = "|".join(re.escape(n) for n in unique_names) or re.escape(self.assistant_name)
        wake = re.escape(self.wake_prefix)
        self.strict_pattern = re.compile(rf"\b(?:{wake}\s+)+(?:{names_alt})\b")
        self.name_pattern = re.compile(rf"\b(?:{names_alt})\b")
        self.direct_call_pattern = re.compile(rf"^(okay|ok|yo|hello|hi|hey)\s+(?:{names_alt})\b")
        self.question_pattern = re.compile(
            r"\b(can you|could you|would you|please|tell me|show me|find|search|open|summarize|what|why|how|when|where)\b"
        )
        self.you_pattern = re.compile(r"\b(you|your|yours)\b")
        self.other_name_pattern = re.compile(r"\b(he|she|they|him|her|them)\b")

    def update_identity(self, assistant_name: str, wake_prefix: str = None, aliases: list[str] | None = None):  # type: ignore
        self.assistant_name = (assistant_name or self.assistant_name).strip().lower()
        if wake_prefix is not None:
            self.wake_prefix = (wake_prefix or self.wake_prefix).strip().lower()
        if aliases is not None:
            self.aliases = [a.strip().lower() for a in aliases if (a or "").strip()]
        self._compile_patterns()

    def should_respond(self, text: str):
        """
        Returns: (bool, reason, score)
        """
        msg = (text or "").strip().lower()
        if not msg:
            return False, "empty", 0.0

        # Always allow strict wake phrase in any mode.
        if self.strict_pattern.search(msg):
            return True, "strict_wake", 1.0

        if self.mode == "strict":
            return False, "strict_mode_no_wake", 0.0

        score = 0.0

        # Name presence is the strongest signal.
        if self.name_pattern.search(msg):
            score += 0.45
        if self.direct_call_pattern.search(msg):
            score += 0.30

        # Intent/question signals.
        if self.question_pattern.search(msg):
            score += 0.25
        if msg.endswith("?"):
            score += 0.10
        if self.you_pattern.search(msg):
            score += 0.15

        # Penalties for likely side-conversation references.
        if self.other_name_pattern.search(msg) and not self.question_pattern.search(msg):
            score -= 0.20
        if self.name_pattern.search(msg) and "talking to" in msg and not self.question_pattern.search(msg):
            score -= 0.25

        score = max(0.0, min(1.0, score))
        should = score >= 0.60
        return should, "smart_score", score
