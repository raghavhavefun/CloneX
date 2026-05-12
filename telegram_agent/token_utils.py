import requests


def validate_telegram_bot_token(bot_token: str) -> tuple[bool, str]:
    token = (bot_token or '').strip()
    if not token:
        return False, 'Token is empty'
    try:
        r = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=12)
        if r.status_code >= 400:
            return False, f'Telegram API rejected token ({r.status_code})'
        data = r.json()
        if not data.get('ok'):
            return False, f"Telegram rejected token: {data.get('description', 'unknown error')}"
        username = (data.get('result') or {}).get('username', 'bot')
        return True, f'Valid bot token for @{username}'
    except Exception as e:
        return False, f'Token validation failed: {e}'
