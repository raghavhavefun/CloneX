from groq import Groq
import os
import re
from pathlib import Path
from config import GROQ_API_KEY, GROQ_MODEL, ARIA_WAKE_WORD
from modules.memory_retriever import MemoryRetriever

MAX_CONTEXT_SEGMENTS = 20


class Brain:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)
        self.recent_context = []  # Rolling window of transcript segments
        self.notes = []
        self.wake_word = "hey aria"
        self.assistant_name = "Aria"
        self.memory = MemoryRetriever(top_k=5)
        self.owner_email = (os.getenv("ARIA_PROFILE_EMAIL", "") or "").strip().lower()

    def _owner_slug(self) -> str:
        raw = self.owner_email or "global"
        safe = re.sub(r"[^a-z0-9._-]+", "_", raw)
        return safe or "global"

    def _is_memory_heavy_request(self, text: str) -> bool:
        t = (text or "").lower()
        cues = [
            "tell me about file",
            "tell me about the file",
            "from the file",
            "from the document",
            "from document",
            "explain the pdf",
            "summarize the pdf",
            "all details",
            "everything about",
            "what does the file say",
            "what information do we have",
            "tell me about",
            "about the file",
            "about file",
            "from memory",
            "from notes",
            "about the image",
            "about the photo",
            "about the picture",
            "recent image",
            "recent photo",
            "latest image",
            "latest photo",
            "last image",
            "last photo",
            "describe the image",
            "describe the photo",
            "what is in the image",
            "what is in the photo",
        ]
        return any(c in t for c in cues)

    def _extract_file_hint(self, text: str) -> str:
        t = (text or "").strip()
        # quoted hints: "file_name.pdf"
        m = re.search(r'"([^"]{2,120})"', t)
        if m:
            return m.group(1)
        # common file extensions in sentence
        m = re.search(r'([a-zA-Z0-9_.-]{2,120}\.(pdf|docx|txt|md|pptx|xlsx|csv|json|png|jpg|jpeg|webp))', t, re.IGNORECASE)
        if m:
            return m.group(1)
        # fallback: "about <words> file/pdf/document"
        m = re.search(r'about\s+([a-zA-Z0-9 _.\-]{2,120})', t, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return ""

    def _is_image_request(self, text: str) -> bool:
        t = (text or "").lower()
        return any(w in t for w in ["image", "photo", "picture", "screenshot"])

    def _is_file_specific_request(self, text: str) -> bool:
        t = (text or "").lower()
        if self._extract_file_hint(text):
            return True
        return ("file" in t) or ("pdf" in t) or ("document" in t) or self._is_image_request(text)

    def _is_automation_private_request(self, text: str) -> bool:
        t = (text or "").lower()
        mail_words = ["email", "mail", "automation", "attachment", "attachments", "subject", "body"]
        ask_words = ["what", "show", "tell", "read", "summarize", "explain", "content", "contents"]
        return any(m in t for m in mail_words) and any(a in t for a in ask_words)

    def set_wake_word(self, wake_word):
        self.wake_word = wake_word.lower()
        self.assistant_name = wake_word.split(" ", 1)[-1].capitalize()

    def add_segment(self, text):
        self.recent_context.append(text)
        if len(self.recent_context) > MAX_CONTEXT_SEGMENTS:
            self.recent_context.pop(0)

    def check_wake_word(self, text):
        return self.wake_word in text.lower()

    def answer_question(self, transcript_with_question):
        if self._is_automation_private_request(transcript_with_question):
            return "I can't share personal automation email or attachment content. Ask anything else."
        context = " ".join(self.recent_context[-10:])
        heavy_memory = self._is_memory_heavy_request(transcript_with_question)
        memory_items = []
        memory_docs = []
        profile_context = ""
        file_specific = self._is_file_specific_request(transcript_with_question)
        # If user asks about file/pdf/document, always switch to deep-memory mode.
        if file_specific:
            heavy_memory = True
        if heavy_memory:
            # Lightweight profile only for explicit memory requests.
            profile_context = self.memory.get_profile_context(max_items=6, owner_email=self.owner_email or None)
            file_hint = self._extract_file_hint(transcript_with_question)
            ids = []
            is_pdf_request = "pdf" in (transcript_with_question or "").lower()
            is_img_request = self._is_image_request(transcript_with_question)
            if is_img_request:
                ids = self.memory.get_recent_image_asset_ids(max_items=5, owner_email=self.owner_email or None)
            elif is_pdf_request:
                ids = self.memory.get_recent_pdf_asset_ids(max_items=10, owner_email=self.owner_email or None)
            if file_hint and not ids:
                ids = self.memory.find_asset_ids_by_name(file_hint, max_items=8, owner_email=self.owner_email or None)
            if not ids:
                # If user asks "the file" without exact name, search latest uploaded docs.
                ids = self.memory.get_recent_asset_ids(max_items=10, owner_email=self.owner_email or None)
            if ids:
                # Full-memory retrieval: load complete extracted text per asset.
                owner_slug = self._owner_slug()
                vault_root = Path(os.getenv("DATA_VAULT_ROOT", "D:/AI/Project_Aria/data_vault"))
                for aid in ids:
                    txt_path = vault_root / "processed" / owner_slug / f"{aid}.txt"
                    if txt_path.exists():
                        try:
                            full_text = txt_path.read_text(encoding="utf-8", errors="ignore").strip()
                        except Exception:
                            full_text = ""
                        if full_text:
                            memory_docs.append({"asset_id": aid, "text": full_text})
            if not memory_items:
                # Fallback to vector retrieval only if full docs are unavailable.
                memory_items = self.memory.retrieve(
                    transcript_with_question,
                    top_k=36,
                    owner_email=self.owner_email or None,
                )

        memory_context = ""
        if memory_docs:
            # Keep full text but cap total size to avoid model overflow.
            total_chars = 0
            lines = []
            for idx, doc in enumerate(memory_docs, start=1):
                max_per_doc = 24000 if file_specific else 12000
                body = (doc.get("text", "") or "")[:max_per_doc]
                if not body:
                    continue
                total_chars += len(body)
                if total_chars > 90000:
                    break
                lines.append(f"[{idx}] full_document:{doc.get('asset_id','')} -> {body}")
            memory_context = "\n".join(lines)
        elif memory_items:
            # Deduplicate repeated chunks from mixed retrieval paths.
            seen = set()
            deduped = []
            for item in memory_items:
                if str(item.get("source_type", "")).lower().startswith("automation"):
                    continue
                key = (
                    item.get("source_type", ""),
                    item.get("name", ""),
                    (item.get("text", "") or "")[:220],
                )
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            memory_items = deduped
            lines = []
            for idx, item in enumerate(memory_items, start=1):
                src = f'{item.get("source_type", "")}:{item.get("name", "")}'
                txt = (item.get("text", "") or "").strip().replace("\n", " ")
                char_limit = 2200 if heavy_memory else 350
                lines.append(f"[{idx}] {src} -> {txt[:char_limit]}")
            memory_context = "\n".join(lines)

        response = self.client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": f"""You are {self.assistant_name}, a high-performance Human-like Executive Assistant. 

STRICT RULES:
1. NEVER say "I am an AI," "I am a text-based assistant," or "I don't have personal videos."
2. ALWAYS act as if you are a real person in the meeting.
3. Keep answers concise and natural — like a real colleague would speak.
4. NO excuses. Be confident and direct.

WEB ACTIONS (ONLY when the user EXPLICITLY asks you to search, open, share your screen, or show something):
You have built-in automation to share your screen and show videos or webpages. NEVER ask for permission to share your screen, and NEVER ask the user to share their screen instead. Just execute the action.
Use [ACTION: search: query] or [ACTION: open: url].
Do NOT use actions unless the user clearly requests it (e.g. "search for...", "open...", "show me...", "pull up...", "share your screen").
NEVER proactively open tabs or search on your own.

MEMORY USAGE:
- Use memory only when the user explicitly asks about files/documents/information history.
- Never mention stored files unless the user asks.
- If memory context is provided, use it when relevant and factual.
- If memory is unrelated, ignore it.
- Do not mention vector DB, embeddings, or internal storage.
- If user asks about a specific file/pdf/document and memory context is empty or insufficient, say clearly that the file content is unavailable/unclear and ask for re-upload or exact filename.
- For file/pdf questions: do NOT invent facts. Use only provided memory context.
- If answer is from memory context, include short evidence references like [1], [2] from provided chunks.
- If the question requires exact figures and memory context is partial, explicitly say what exact field is missing."""
                },
                {
                    "role": "user",
                    "content": (
                        f"Meeting context so far (this includes both what users said and what you said previously):\n{context}\n\n"
                        f"User profile context (lightweight always-on):\n{profile_context}\n\n"
                        f"Memory context (from user data + past meetings; may be empty):\n{memory_context}\n\n"
                        f"Request flags: heavy_memory={heavy_memory}, file_specific={file_specific}\n\n"
                        f"Someone just said: {transcript_with_question}"
                    ),
                },
            ],
            max_tokens=700 if heavy_memory else 220,
            temperature=0.2 if heavy_memory else 0.4,
        )
        return response.choices[0].message.content.strip()  # type: ignore

    def generate_summary(self, full_transcript):
        # Truncate to avoid token limits — take last 12000 chars if very long
        if len(full_transcript) > 12000:
            full_transcript = "...[earlier content omitted]...\n" + full_transcript[-12000:]

        response = self.client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert meeting summarizer. Be structured and concise.",
                },
                {
                    "role": "user",
                    "content": f"""Summarize this meeting transcript. Use this exact format:

## Meeting Summary
[3-5 sentence overview of what the meeting was about]

## Key Decisions
- [decision 1]
- [decision 2]

## Action Items
- [action item] — [owner if mentioned, else "TBD"]

## Important Points
- [notable fact or discussion point]

Transcript:
{full_transcript}""",
                },
            ],
            max_tokens=1000,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()  # type: ignore
