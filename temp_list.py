import pyaudio

p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    # Only print input devices
    if info.get('maxInputChannels') > 0:  # type: ignore
        print(f"[{i}] {info.get('name')}")
p.terminate()
