import pyaudio
import threading
import queue

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  # Whisper expects 16kHz


class AudioCapture:
    def __init__(self, device_index=None):
        self.device_index = device_index
        self.audio_queue = queue.Queue()
        self._running = False
        self._thread = None
        self.pa = pyaudio.PyAudio()

    def list_devices(self):
        devices = []
        for i in range(self.pa.get_device_count()):
            try:
                info = self.pa.get_device_info_by_index(i)
            except Exception:
                # Some Windows drivers report stale/invalid indices; skip them.
                continue
            if info.get("maxInputChannels", 0) > 0:  # type: ignore
                devices.append((i, info.get("name", f"Input Device {i}")))
        return devices

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        self.pa.terminate()

    def _capture_loop(self):
        # Dynamically detect supported channels for the device
        try:
            device_info = self.pa.get_device_info_by_index(self.device_index) if self.device_index is not None else self.pa.get_default_input_device_info()
            supported_channels = int(device_info['maxInputChannels'])
            actual_channels = min(supported_channels, 2) # Use 1 or 2
        except Exception:
            actual_channels = 1

        print(f"[AudioCapture] Starting stream with {actual_channels} channel(s) on device {self.device_index}")
        
        stream = self.pa.open(
            format=FORMAT,
            channels=actual_channels,
            rate=RATE,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=CHUNK,
        )
        
        while self._running:
            data = stream.read(CHUNK, exception_on_overflow=False)
            
            # If we are in Stereo, convert to Mono by taking every other 16-bit sample
            if actual_channels == 2:
                import numpy as np
                audio_np = np.frombuffer(data, dtype=np.int16)
                mono_data = audio_np[::2].tobytes() # Take left channel only
                self.audio_queue.put(mono_data)
            else:
                self.audio_queue.put(data)
                
        stream.stop_stream()
        stream.close()

    def get_chunk(self, timeout=1.0):
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
