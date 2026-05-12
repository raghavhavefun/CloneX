import os
import platform
import subprocess
from pathlib import Path


def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def is_macos() -> bool:
    return platform.system().lower() == "darwin"


def kill_browser_processes():
    """
    Best-effort browser shutdown used before launching automation profile.
    """
    if is_windows():
        for exe in ["chrome.exe", "msedge.exe"]:
            subprocess.run(["taskkill", "/F", "/IM", exe], capture_output=True, text=True)
        return

    # macOS/Linux style
    for proc_name in ["Google Chrome", "Microsoft Edge", "chrome", "msedge"]:
        subprocess.run(["pkill", "-f", proc_name], capture_output=True, text=True)


def chrome_user_data_root() -> Path | None:
    if is_windows():
        local_app_data = os.getenv("LOCALAPPDATA", "").strip()
        if not local_app_data:
            return None
        return Path(local_app_data) / "Google" / "Chrome" / "User Data"
    if is_macos():
        home = Path.home()
        return home / "Library" / "Application Support" / "Google" / "Chrome"
    # Linux fallback
    home = Path.home()
    return home / ".config" / "google-chrome"


def audio_device_priority(name: str) -> int:
    """
    Lower score = better.
    Cross-platform heuristic for loopback/virtual devices.
    """
    n = (name or "").lower()
    # Windows virtual cable / loopback common names
    if "vb-audio" in n or "cable output" in n:
        return 0
    if "stereo mix" in n:
        return 1
    # macOS virtual devices (BlackHole/Loopback/Soundflower)
    if "blackhole" in n or "loopback" in n or "soundflower" in n:
        return 0
    # Generic monitor/virtual terms
    if "monitor" in n or "virtual" in n:
        return 2
    return 10

