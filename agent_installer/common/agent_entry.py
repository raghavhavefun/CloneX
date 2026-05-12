import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], cwd: Path | None = None):
    print(f"[Agent] Running: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(cwd or ROOT), check=False)


def _start_data_backend():
    backend = ROOT / "run_data_backend.py"
    return subprocess.Popen([sys.executable, str(backend)], cwd=str(ROOT))


def _start_main():
    main_py = ROOT / "main.py"
    env = os.environ.copy()
    env.setdefault("ARIA_NON_INTERACTIVE", "1")
    return subprocess.Popen([sys.executable, str(main_py)], cwd=str(ROOT), env=env)


def main():
    print("[Agent] Aria Agent starting...")
    print(f"[Agent] Platform: {platform.system()} {platform.release()}")

    # First launch wizard placeholder.
    wizard = ROOT / "agent_installer" / "common" / "first_run_wizard.py"
    if wizard.exists():
        _run([sys.executable, str(wizard)])

    # Start backend and main runtime.
    backend_proc = _start_data_backend()
    main_proc = _start_main()

    state = {
        "backend_pid": backend_proc.pid,
        "main_pid": main_proc.pid,
    }
    (ROOT / "agent_runtime_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"[Agent] backend pid={backend_proc.pid} main pid={main_proc.pid}")

    # Keep parent alive while children run.
    try:
        backend_proc.wait()
        main_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in [backend_proc, main_proc]:
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
