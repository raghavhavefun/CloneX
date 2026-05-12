from typing import Any
import requests


class AriaBackendClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    def _headers(self, email: str = '', bearer: str = '') -> dict[str, str]:
        h: dict[str, str] = {}
        if email:
            h['X-User-Email'] = email.strip().lower()
        if bearer:
            h['Authorization'] = f'Bearer {bearer}'
        return h

    def health(self) -> tuple[bool, str]:
        try:
            r = requests.get(f'{self.base_url}/health', timeout=8)
            if r.status_code >= 400:
                return False, f'health failed ({r.status_code})'
            return True, 'ok'
        except Exception as e:
            return False, str(e)

    def session_status(self, email: str, bearer: str) -> tuple[bool, dict[str, Any] | str]:
        try:
            r = requests.get(
                f'{self.base_url}/api/session/status',
                headers=self._headers(email=email, bearer=bearer),
                timeout=12,
            )
            if r.status_code >= 400:
                return False, f'status failed ({r.status_code}): {r.text}'
            return True, r.json() if r.content else {}
        except Exception as e:
            return False, str(e)

    def session_start(
        self,
        *,
        meeting_url: str,
        email: str,
        bearer: str,
        assistant_name: str = 'Aria',
        avatar_mode: str = '3d',
    ) -> tuple[bool, dict[str, Any] | str]:
        payload = {
            'meeting_url': meeting_url.strip(),
            'profile_email': email.strip().lower(),
            'assistant_name': assistant_name.strip() or 'Aria',
            'avatar_mode': 'female' if avatar_mode.strip().lower() == 'female' else '3d',
        }
        try:
            r = requests.post(
                f'{self.base_url}/api/session/start',
                headers={**self._headers(email=email, bearer=bearer), 'Content-Type': 'application/json'},
                json=payload,
                timeout=20,
            )
            if r.status_code >= 400:
                return False, f'start failed ({r.status_code}): {r.text}'
            return True, r.json() if r.content else {}
        except Exception as e:
            return False, str(e)

    def session_stop(self, email: str, bearer: str) -> tuple[bool, dict[str, Any] | str]:
        try:
            r = requests.post(
                f'{self.base_url}/api/session/stop',
                headers=self._headers(email=email, bearer=bearer),
                timeout=15,
            )
            if r.status_code >= 400:
                return False, f'stop failed ({r.status_code}): {r.text}'
            return True, r.json() if r.content else {}
        except Exception as e:
            return False, str(e)

    def data_upload(self, email: str, bearer: str, file_bytes: bytes, filename: str) -> tuple[bool, dict[str, Any] | str]:
        try:
            r = requests.post(
                f'{self.base_url}/api/data/upload',
                headers=self._headers(email=email, bearer=bearer),
                files=[('files', (filename, file_bytes, 'application/octet-stream'))],
                timeout=300,
            )
            if r.status_code >= 400:
                return False, f'upload failed ({r.status_code}): {r.text}'
            return True, r.json() if r.content else {}
        except Exception as e:
            return False, str(e)

    def los_list_agents(self, email: str, bearer: str) -> tuple[bool, dict[str, Any] | str]:  # type: ignore
        try:
            # We don't have a direct list agents endpoint in the document, but usually it's hardcoded to 6 domain-locked.
            # We can also just chat directly if we know the name, or we can use a dummy/hardcoded list in the bot if needed.
            # Actually, the doc says "6 domain-locked sub-agents". Let's assume the bot knows them or we use the chat endpoint.
            pass
        except Exception as e:
            return False, str(e)

    def los_chat(
        self,
        email: str,
        bearer: str,
        agent_name: str,
        message: str,
        autonomy_mode: str = "suggest_actions",
    ) -> tuple[bool, dict[str, Any] | str]:
        try:
            payload = {
                'agent_name': agent_name.strip(),
                'message': message.strip(),
                'autonomy_mode': autonomy_mode.strip() or "suggest_actions",
            }
            r = requests.post(
                f'{self.base_url}/api/los/subagents/chat',
                headers={**self._headers(email=email, bearer=bearer), 'Content-Type': 'application/json'},
                json=payload,
                timeout=30,
            )
            if r.status_code >= 400:
                return False, f'LOS chat failed ({r.status_code}): {r.text}'
            return True, r.json() if r.content else {}
        except Exception as e:
            return False, str(e)

    def automation_schedule(self, email: str, bearer: str, parsed: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
        try:
            mode = "send_now" if parsed.get("schedule_type") == "send_now" else "custom_schedule"
            
            recipient = str(parsed.get("recipient") or "").strip()
            if recipient.lower() in ["myself", "me"]:
                recipient = email
                
            payload = {
                "requester_email": email,
                "recipients": recipient,
                "instruction": parsed.get("raw_command", ""),
                "mode": mode,
                "subject": "Aria Reminder from Telegram",
                "message": parsed.get("body", ""),
            }
            if parsed.get("schedule_time_local"):
                payload["schedule_at"] = parsed.get("schedule_time_local")

            r = requests.post(
                f'{self.base_url}/api/automation/schedule',
                headers={**self._headers(email=email, bearer=bearer), 'Content-Type': 'application/json'},
                json=payload,
                timeout=20,
            )
            if r.status_code >= 400:
                return False, f'Schedule failed ({r.status_code}): {r.text}'
            return True, r.json() if r.content else {}
        except Exception as e:
            return False, str(e)

    def automation_history(self, email: str, bearer: str, limit: int = 5) -> tuple[bool, dict[str, Any] | str]:
        try:
            r = requests.get(
                f'{self.base_url}/api/automation/history?limit={limit}',
                headers=self._headers(email=email, bearer=bearer),
                timeout=10,
            )
            if r.status_code >= 400:
                return False, f'History failed ({r.status_code}): {r.text}'
            return True, r.json() if r.content else {}
        except Exception as e:
            return False, str(e)

    def save_connect(self, email: str, bearer: str, name: str, contact_email: str) -> tuple[bool, str]:
        try:
            payload = {'name': name, 'email': contact_email}
            r = requests.post(
                f'{self.base_url}/api/connects',
                headers={**self._headers(email=email, bearer=bearer), 'Content-Type': 'application/json'},
                json=payload,
                timeout=15,
            )
            if r.status_code >= 400:
                return False, f'save connect failed ({r.status_code}): {r.text}'
            return True, 'Connect saved successfully!'
        except Exception as e:
            return False, str(e)
