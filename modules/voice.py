import os
import asyncio
import edge_tts
from pydub import AudioSegment
import pyaudio
import wave

class Voice:
    def __init__(self, voice_name="en-US-GuyNeural"):
        # We are using the official "Guy" neural voice from Edge TTS!
        self.voice_name = voice_name

    def set_voice(self, voice_name):
        if voice_name and isinstance(voice_name, str):
            self.voice_name = voice_name
            print(f"[Voice] Switched voice to: {self.voice_name}")
        
    async def _generate_audio(self, text, output_file):
        communicate = edge_tts.Communicate(text, self.voice_name)
        await communicate.save(output_file)

    def speak(self, text, avatar=None, bridge_3d=None):
        print(f"[Voice] Generating speech for Aria...")
        mp3_file = "temp_voice.mp3"
        wav_file = "temp_voice.wav"
        if avatar:
            avatar.set_speech_text(text)
        
        # 1. Generate highly realistic MP3 using Edge TTS
        asyncio.run(self._generate_audio(text, mp3_file))
        
        # 2. Convert to WAV because PyAudio needs raw waveform data
        audio = AudioSegment.from_mp3(mp3_file)
        audio.export(wav_file, format="wav")
        
        # 3. Play the audio directly to the Default Playback Device (CABLE Input)
        print(f"[Voice] Speaking aloud...")
        wf = wave.open(wav_file, 'rb')
        pa = pyaudio.PyAudio()
        
        stream = pa.open(format=pa.get_format_from_width(wf.getsampwidth()),
                         channels=wf.getnchannels(),
                         rate=wf.getframerate(),
                         output=True)
        
        chunk_size = 1024
        data = wf.readframes(chunk_size)
        while len(data) > 0:
            stream.write(data)
            
            # Calculate volume for avatar lip-sync
            if avatar or bridge_3d:
                import numpy as np
                audio_data = np.frombuffer(data, dtype=np.int16)
                if len(audio_data) > 0:
                    volume = float(np.abs(audio_data).mean() / 5000.0)  # Normalize
                    vol = min(volume, 1.0)
                    if avatar:
                        avatar.set_volume(vol)
                    if bridge_3d:
                        bridge_3d.set_volume(vol)
            
            data = wf.readframes(chunk_size)
            
        if avatar:
            avatar.set_volume(0)
            avatar.set_speech_text("")
        if bridge_3d:
            bridge_3d.set_volume(0)
            
        stream.stop_stream()
        stream.close()
        pa.terminate()
        wf.close()
        
        # 4. Clean up temporary files
        try:
            os.remove(mp3_file)
            os.remove(wav_file)
        except Exception:
            pass
