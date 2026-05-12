import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "agent_user_config.json"


def prompt(label: str, default: str = "") -> str:
    raw = input(f"{label} [{default}]: ").strip()
    return raw or default


def main():
    print("\n=== Aria Agent First-Run Setup ===")
    print("This wizard stores local setup needed before runtime starts.\n")

    profile_email = prompt("Profile email")
    meeting_platform = prompt("Default platform (zoom/google_meet/teams)", "google_meet")
    virtual_audio_driver = prompt("Virtual audio driver (vb-cable/blackhole)", "vb-cable")

    # TODO: Add real pairing flow with backend token exchange.
    pairing_token = prompt("Pairing token (temporary placeholder)")

    cfg = {
        "profile_email": profile_email,
        "meeting_platform": meeting_platform,
        "virtual_audio_driver": virtual_audio_driver,
        "pairing_token": pairing_token,
    }
    CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    print("\nSaved setup to agent_user_config.json")
    print("Next: run dashboard Validate Audio Flow and Join Meeting.\n")


if __name__ == "__main__":
    main()
