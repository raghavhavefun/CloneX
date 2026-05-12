"""
Quick tester for assistant addressing behavior.

Usage:
  .\venv\Scripts\python.exe test_response_gate.py --name john --mode smart  # type: ignore
"""

import argparse

from modules.response_gate import ResponseGate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="aria")
    parser.add_argument("--wake", default="hey")
    parser.add_argument("--mode", default="smart", choices=["strict", "smart"])
    args = parser.parse_args()

    gate = ResponseGate(assistant_name=args.name, wake_prefix=args.wake, mode=args.mode)

    print(f"ResponseGate tester | name={args.name} wake={args.wake} mode={args.mode}")
    print("Type text and press Enter. Type 'exit' to quit.\n")
    while True:
        text = input("you> ").strip()
        if text.lower() in {"exit", "quit"}:
            break
        ok, reason, score = gate.should_respond(text)
        print(f"respond={ok} reason={reason} score={score:.2f}\n")


if __name__ == "__main__":
    main()
