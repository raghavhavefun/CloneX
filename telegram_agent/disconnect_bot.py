import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telegram_agent.state_store import delete_bot_token, init_db, list_bot_accounts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--account', required=True, help='Account email to disconnect')
    args = parser.parse_args()

    init_db()
    n = delete_bot_token(args.account)
    if n:
        print(f'Disconnected bot for account: {args.account.strip().lower()}')
    else:
        print('No mapped bot token found for that account.')

    accounts = list_bot_accounts()
    if accounts:
        print('Remaining configured accounts:')
        for a in accounts:
            print(f' - {a}')
    else:
        print('No accounts mapped now.')


if __name__ == '__main__':
    main()
