"""Unified apkdist CLI with subcommands."""

import argparse
from typing import List

from .cleanup import main as cleanup_main
from .env_check import main as env_check_main
from .pipeline import main as pipeline_main
from .telegram_updates import main as telegram_updates_main


def _run_make(args: argparse.Namespace) -> int:
    variant = args.variant_flag or args.variant or "release"
    forwarded: List[str] = [args.type, "--variant", variant]
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.force:
        forwarded.append("--force")
    if args.env_file:
        forwarded.extend(["--env-file", args.env_file])
    pipeline_main(forwarded)
    return 0


def _run_env_check(args: argparse.Namespace) -> int:
    forwarded: List[str] = []
    if args.project:
        forwarded.extend(["--project", args.project])
    env_check_main(forwarded)
    return 0


def _run_cleanup(args: argparse.Namespace) -> int:
    forwarded: List[str] = ["--days", str(args.days)]
    if args.delete:
        forwarded.append("--delete")
    if args.env_file:
        forwarded.extend(["--env-file", args.env_file])
    cleanup_main(forwarded)
    return 0


def _run_telegram_updates(args: argparse.Namespace) -> int:
    forwarded: List[str] = ["--limit", str(args.limit), "--timeout", str(args.timeout)]
    if args.env_file:
        forwarded.extend(["--env-file", args.env_file])
    if args.token:
        forwarded.extend(["--token", args.token])
    if args.api_base_url:
        forwarded.extend(["--api-base-url", args.api_base_url])
    if args.raw:
        forwarded.append("--raw")
    telegram_updates_main(forwarded)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="apkdist",
        description="APK distribution toolkit",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    make_parser = subparsers.add_parser("make", help="Build, upload, and notify a release")
    make_parser.add_argument("type", choices=["major", "minor", "patch"], help="Version bump type")
    make_parser.add_argument("variant", nargs="?", help="Build variant (default: release)")
    make_parser.add_argument("--variant", dest="variant_flag", help="Build variant (same as positional)")
    make_parser.add_argument("--dry-run", action="store_true", help="Simulate without side effects")
    make_parser.add_argument("--force", action="store_true", help="Force rebuild and re-upload")
    make_parser.add_argument("--env-file", help="Path to .env file")
    make_parser.set_defaults(handler=_run_make)

    check_parser = subparsers.add_parser("env-check", help="Validate local Android build environment")
    check_parser.add_argument("--project", help="Path to Android project root (where gradlew lives)")
    check_parser.set_defaults(handler=_run_env_check)

    cleanup_parser = subparsers.add_parser("cleanup", help="Clean old APK files from Google Drive")
    cleanup_parser.add_argument("--days", type=int, default=7, help="Delete files older than this many days")
    cleanup_parser.add_argument("--delete", action="store_true", help="Actually delete files (default dry-run)")
    cleanup_parser.add_argument("--env-file", help="Path to .env file")
    cleanup_parser.set_defaults(handler=_run_cleanup)

    updates_parser = subparsers.add_parser("telegram-updates", help="Discover Telegram chat/thread IDs")
    updates_parser.add_argument("--env-file", help="Path to .env file")
    updates_parser.add_argument("--token", help="Telegram bot token")
    updates_parser.add_argument("--api-base-url", help="Telegram Bot API base URL")
    updates_parser.add_argument("--limit", type=int, default=50, help="Maximum updates to fetch")
    updates_parser.add_argument("--timeout", type=int, default=0, help="Long-poll timeout in seconds")
    updates_parser.add_argument("--raw", action="store_true", help="Print raw getUpdates JSON")
    updates_parser.set_defaults(handler=_run_telegram_updates)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
