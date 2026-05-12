import numpy as np
import threading
import queue
import whisper
from datetime import datetime, timezone

SAMPLE_RATE = 16000
SEGMENT_SECONDS = 5  # Buffer 5s of audio before transcribing


class Transcriber:
    def __init__(self, model_size="large-v3"):
        self.model = None
        self.model_size = model_size
        self.text_queue = queue.Queue()
        self.full_transcript = []
        self._running = False
        self._thread = None
        self.segment_events = []
        self._audio_seconds_processed = 0.0

    def start(self, audio_capture):
        self._audio = audio_capture
        if self.model is None:
            print(f"[Transcriber] Loading Whisper {self.model_size} (this takes ~30s first time)...")
            self.model = whisper.load_model(self.model_size)
            print(f"[Transcriber] Whisper {self.model_size} ready.")
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def _loop(self):
        buffer = []
        silence_chunks = 0

        while self._running:
            chunk = self._audio.get_chunk(timeout=1.0)
            if chunk is None:
                continue

            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
            buffer.extend(samples)

            # Measure volume to detect silence
            energy = np.sqrt(np.mean(samples**2))
            if energy < 0.01:
                silence_chunks += 1
            else:
                silence_chunks = 0

            # 47 chunks is ~3 seconds. Transcribe if 3s silence reached, OR buffer hits 30 seconds max.
            # Only transcribe if we have at least 1 second of audio in buffer to avoid spam.
            if (silence_chunks >= 47 and len(buffer) > 16000) or len(buffer) > 16000 * 30:
                segment = np.array(buffer)
                buffer = []
                silence_chunks = 0

                chunk_seconds = len(segment) / SAMPLE_RATE
                base_offset = self._audio_seconds_processed
                self._audio_seconds_processed += chunk_seconds

                result = self.model.transcribe(  # type: ignore
                    segment,
                    language="en",
                    fp16=True,   # GPU acceleration
                    temperature=0,
                )
                text = result["text"].strip()  # type: ignore

                clean_text = text.lower().strip('.!')
                if clean_text in ["thank you", "thanks", "thank you for watching", "thanks for watching", "you"]:
                    text = ""

                if text:
                    self.full_transcript.append(text)
                    self.text_queue.put(text)
                    print(f"[Transcript] {text}")

                for seg in (result.get("segments") or []):
                    seg_text = str(seg.get("text", "")).strip()  # type: ignore
                    if not seg_text:
                        continue
                    self.segment_events.append(
                        {
                            "text": seg_text,
                            "start": float(seg.get("start", 0.0)) + base_offset,  # type: ignore
                            "end": float(seg.get("end", 0.0)) + base_offset,  # type: ignore
                            "created_at": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
                        }
                    )

    def get_latest(self, timeout=0.5):
        try:
            return self.text_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_full_transcript(self):
        return " ".join(self.full_transcript)

    def get_segments(self):
        return list(self.segment_events)
