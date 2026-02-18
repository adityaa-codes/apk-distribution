"""Convenience alias commands for common apkdist workflows."""

import argparse
import os
import sys
from typing import List, Optional

from .cleanup import main as cleanup_main_cli
from .env_check import main as env_check_main_cli
from .pipeline import main as pipeline_main


def _resolve_variant(positional: Optional[str], flag_value: Optional[str], parser: argparse.ArgumentParser) -> str:
    if positional and flag_value and positional != flag_value:
        parser.error("Variant provided twice with different values. Use either positional or --variant.")
    return flag_value or positional or "release"


def _run_bump_alias(bump_type: str, argv=None):
    parser = argparse.ArgumentParser(
        prog=f"apk{bump_type}",
        description=f"Run apkdist {bump_type} with optional variant.",
    )
    parser.add_argument("variant", nargs="?", help="Build variant (default: release)")
    parser.add_argument("--variant", dest="variant_flag", help="Build variant (same as positional variant)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without side effects")
    parser.add_argument("--force", action="store_true", help="Force rebuild and re-upload")
    parser.add_argument("--env-file", help="Path to .env file")
    args = parser.parse_args(argv)

    variant = _resolve_variant(args.variant, args.variant_flag, parser)

    forwarded: List[str] = [bump_type, "--variant", variant]
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.force:
        forwarded.append("--force")
    if args.env_file:
        forwarded.extend(["--env-file", args.env_file])

    return pipeline_main(forwarded)


def bump_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="apkbump",
        description="Bump version with type and optional variant.",
    )
    parser.add_argument("type", choices=["major", "minor", "patch"], help="Bump type")
    parser.add_argument("variant", nargs="?", help="Build variant (default: release)")
    parser.add_argument("--variant", dest="variant_flag", help="Build variant (same as positional variant)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without side effects")
    parser.add_argument("--force", action="store_true", help="Force rebuild and re-upload")
    parser.add_argument("--env-file", help="Path to .env file")
    args = parser.parse_args(argv)

    variant = _resolve_variant(args.variant, args.variant_flag, parser)

    forwarded: List[str] = [args.type, "--variant", variant]
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.force:
        forwarded.append("--force")
    if args.env_file:
        forwarded.extend(["--env-file", args.env_file])

    return pipeline_main(forwarded)


def patch_main(argv=None):
    return _run_bump_alias("patch", argv)


def minor_main(argv=None):
    return _run_bump_alias("minor", argv)


def major_main(argv=None):
    return _run_bump_alias("major", argv)


def clean_main(argv=None):
    return cleanup_main_cli(argv)


def check_main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        project = os.getenv("ANDROID_PROJECT_PATH")
        if project:
            argv = ["--project", project]

    return env_check_main_cli(argv)
