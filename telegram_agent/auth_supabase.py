import requests
from typing import Any

from telegram_agent.config import TelegramAgentConfig


class SupabaseOtpClient:
    def __init__(self, cfg: TelegramAgentConfig):
        self.cfg = cfg

    def _headers(self) -> dict[str, str]:
        return {
            'apikey': self.cfg.supabase_anon_key,
            'Content-Type': 'application/json',
        }

    def send_otp(self, email: str) -> tuple[bool, str]:
        if not self.cfg.supabase_url or not self.cfg.supabase_anon_key:
            return False, 'Supabase env is missing (SUPABASE_URL / SUPABASE_ANON_KEY).'
        payload = {
            'email': email.strip().lower(),
            'create_user': False,
        }
        try:
            r = requests.post(
                f"{self.cfg.supabase_url}/auth/v1/otp",
                headers=self._headers(),
                json=payload,
                timeout=20,
            )
            if r.status_code >= 400:
                detail = ''
                try:
                    detail = (r.json() or {}).get('msg') or (r.json() or {}).get('error_description') or str(r.text)
                except Exception:
                    detail = str(r.text)
                return False, f'OTP send failed: {detail}'
            return True, 'OTP sent. Check your email and send: otp 123456'
        except Exception as e:
            return False, f'OTP send failed: {e}'

    def verify_otp(self, email: str, otp: str) -> tuple[bool, str, dict[str, Any]]:
        payload = {
            'type': 'email',
            'email': email.strip().lower(),
            'token': otp.strip(),
        }
        try:
            r = requests.post(
                f"{self.cfg.supabase_url}/auth/v1/verify",
                headers=self._headers(),
                json=payload,
                timeout=20,
            )
            data = r.json() if r.content else {}
            if r.status_code >= 400:
                msg = (data or {}).get('msg') or (data or {}).get('error_description') or str(data)
                return False, f'OTP verify failed: {msg}', {}
            user = (data or {}).get('user') or {}
            session = (data or {}).get('session') or {}
            access_token = session.get('access_token') or data.get('access_token') or ''
            refresh_token = session.get('refresh_token') or data.get('refresh_token') or ''
            verified_email = str(user.get('email', '')).strip().lower()
            if '@' not in verified_email or not access_token:
                return False, 'OTP verified but session token missing.', {}
            return True, 'Verified.', {
                'email': verified_email,
                'access_token': access_token,
                'refresh_token': refresh_token,
            }
        except Exception as e:
            return False, f'OTP verify failed: {e}', {}
