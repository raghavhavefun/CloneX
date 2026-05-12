import platform
import subprocess


def check_obs() -> bool:
    try:
        if platform.system().lower().startswith("win"):
            out = subprocess.run(["where", "obs64.exe"], capture_output=True, text=True)
            return out.returncode == 0
        out = subprocess.run(["which", "obs"], capture_output=True, text=True)
        return out.returncode == 0
    except Exception:
        return False


def main():
    print("OBS installed:", "yes" if check_obs() else "no")


if __name__ == "__main__":
    main()
