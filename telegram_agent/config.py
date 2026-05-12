import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    def load_dotenv(*args, **kwargs):
        return False

def _load_env_fallback(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        s = line.strip()
        if not s or s.startswith('#') or '=' not in s:
            continue
        k, v = s.split('=', 1)
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key and (key not in os.environ or not str(os.environ.get(key, "")).strip()):
            os.environ[key] = val

_env_path = Path(__file__).resolve().parents[1] / '.env'
loaded = load_dotenv(_env_path, override=True)
if not loaded:
    _load_env_fallback(_env_path)


@dataclass
class TelegramAgentConfig:
    supabase_url: str
    supabase_anon_key: str
    data_backend_url: str
    telegram_groq_key: str



def load_config() -> TelegramAgentConfig:
    return TelegramAgentConfig(
        supabase_url=os.getenv('SUPABASE_URL', '').strip().rstrip('/'),
        supabase_anon_key=os.getenv('SUPABASE_ANON_KEY', '').strip(),
        data_backend_url=os.getenv('DATA_BACKEND_URL', 'http://127.0.0.1:8001').strip().rstrip('/'),
        telegram_groq_key=(
            os.getenv('TELEGRAM_GROQ_API_KEY', '').strip()
            or os.getenv('TELEGRAM_BOT_KEY', '').strip()
        ),
    )
