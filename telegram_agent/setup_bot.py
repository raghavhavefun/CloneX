import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telegram_agent.state_store import init_db, list_bot_accounts, set_bot_token
from telegram_agent.token_utils import validate_telegram_bot_token


def main() -> None:
    init_db()
    print('=== Connect Telegram Bot to Account ===')
    email = input('Account email: ').strip().lower()
    if '@' not in email:
        print('Invalid email.')
        return
    token = input('Telegram bot token: ').strip()
    ok, msg = validate_telegram_bot_token(token)
    print(msg)
    if not ok:
        return
    set_bot_token(email, token)
    print(f'Connected bot token to account: {email}')
    print('Configured accounts:')
    for a in list_bot_accounts():
        print(f' - {a}')


if __name__ == '__main__':
    main()
