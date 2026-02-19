#!/usr/bin/env python3
"""Telegram getUpdates helper to discover chat and thread IDs."""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

import requests

from .config import load_environment


def _resolve_token(flag_token: Optional[str]) -> str:
    token = flag_token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Error: TELEGRAM_BOT_TOKEN is not set (or pass --token).")
        sys.exit(1)
    return token


def _resolve_api_base_url(flag_base_url: Optional[str]) -> str:
    base_url = flag_base_url or os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
    base_url = base_url.strip()
    if not base_url:
        print("❌ Error: TELEGRAM_API_BASE_URL cannot be empty (or pass --api-base-url).")
        sys.exit(1)
    return base_url.rstrip("/")


def fetch_updates(token: str, api_base_url: str, limit: int, timeout: int) -> List[Dict]:
    url = f"{api_base_url}/bot{token}/getUpdates"
    params = {
        "limit": limit,
        "timeout": timeout,
    }
    response = requests.get(url, params=params, timeout=max(30, timeout + 10))

    try:
        data = response.json()
    except ValueError:
        print(f"❌ Telegram Error: {response.text}")
        sys.exit(1)

    if response.status_code != 200 or not data.get("ok"):
        print(f"❌ Telegram Error: {data}")
        sys.exit(1)

    result = data.get("result")
    if not isinstance(result, list):
        print("❌ Telegram Error: Unexpected getUpdates response format.")
        sys.exit(1)

    return result


def _chat_name(chat: Dict) -> str:
    title = chat.get("title")
    if title:
        return str(title)

    first_name = chat.get("first_name")
    username = chat.get("username")
    if first_name and username:
        return f"{first_name} (@{username})"
    if first_name:
        return str(first_name)
    if username:
        return f"@{username}"
    return "-"


def extract_targets(updates: List[Dict]) -> List[Tuple[int, str, str, Optional[int]]]:
    rows: List[Tuple[int, str, str, Optional[int]]] = []
    seen = set()

    for update in updates:
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            message = update.get(key)
            if not isinstance(message, dict):
                continue

            chat = message.get("chat")
            if not isinstance(chat, dict):
                continue

            chat_id = chat.get("id")
            if not isinstance(chat_id, int):
                continue

            chat_type = str(chat.get("type", "-"))
            name = _chat_name(chat)
            thread_id = message.get("message_thread_id")
            if not isinstance(thread_id, int):
                thread_id = None

            row = (chat_id, chat_type, name, thread_id)
            if row in seen:
                continue

            seen.add(row)
            rows.append(row)

    rows.sort(key=lambda item: (item[0], -1 if item[3] is None else item[3]))
    return rows


def _print_rows(rows: List[Tuple[int, str, str, Optional[int]]]) -> None:
    print("✅ Telegram targets discovered:\n")
    for chat_id, chat_type, name, thread_id in rows:
        print(f"• chat_id={chat_id} | type={chat_type} | name={name}")
        if thread_id is not None:
            print(f"  thread_id={thread_id}")


def _print_env_hint(rows: List[Tuple[int, str, str, Optional[int]]]) -> None:
    print("\nSuggested .env values (pick the target you want):\n")

    chat_to_threads: Dict[int, set] = {}
    for chat_id, _, _, thread_id in rows:
        chat_to_threads.setdefault(chat_id, set())
        if thread_id is not None:
            chat_to_threads[chat_id].add(thread_id)

    for chat_id in sorted(chat_to_threads):
        thread_ids = sorted(chat_to_threads[chat_id])
        print(f"# Chat-level (no topic/thread)")
        print(f"TELEGRAM_CHAT_ID={chat_id}")
        if not thread_ids:
            print("# TELEGRAM_THREAD_ID=<optional>")
            print()
            continue

        print("\n# Topic/thread-level")
        for thread_id in thread_ids:
            print(f"TELEGRAM_CHAT_ID={chat_id}")
            print(f"TELEGRAM_THREAD_ID={thread_id}")
            print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch Telegram getUpdates and print chat/thread IDs.",
    )
    parser.add_argument("--env-file", help="Path to .env file")
    parser.add_argument("--token", help="Telegram bot token (overrides TELEGRAM_BOT_TOKEN)")
    parser.add_argument(
        "--api-base-url",
        help="Telegram Bot API base URL (overrides TELEGRAM_API_BASE_URL)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum updates to fetch (default: 50)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="Long-poll timeout in seconds (default: 0)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw getUpdates JSON (for debugging)",
    )
    args = parser.parse_args(argv)

    if args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.timeout < 0:
        parser.error("--timeout must be >= 0")

    try:
        load_environment(args.env_file)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    token = _resolve_token(args.token)
    api_base_url = _resolve_api_base_url(args.api_base_url)

    print("📨 Fetching Telegram updates...")
    updates = fetch_updates(
        token=token,
        api_base_url=api_base_url,
        limit=args.limit,
        timeout=args.timeout,
    )
    print(f"ℹ️  Retrieved {len(updates)} update(s).")

    if args.raw:
        print(json.dumps(updates, indent=2, ensure_ascii=False))

    rows = extract_targets(updates)
    if not rows:
        print("⚠️  No chat/thread IDs found in recent updates.")
        print("   Send a message in the target chat/topic to your bot, then run this command again.")
        return

    _print_rows(rows)
    _print_env_hint(rows)


if __name__ == "__main__":
    main()
