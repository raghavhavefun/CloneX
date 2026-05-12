from typing import Tuple

from telegram_agent.aria_backend_client import AriaBackendClient


def heartbeat_status(client: AriaBackendClient, email: str, bearer: str) -> Tuple[bool, str]:
    ok, msg = client.health()
    if not ok:
        return False, f'Backend health failed: {msg}'
    ok2, status = client.session_status(email=email, bearer=bearer)
    if not ok2:
        return False, f'Backend session status failed: {status}'
    st = (status or {}).get('status', 'unknown') if isinstance(status, dict) else 'unknown'
    return True, f'Backend online. Session status: {st}'
