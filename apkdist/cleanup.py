#!/usr/bin/env python3
"""
Cleanup script — deletes APK files older than N days from Google Drive.

Usage:
    apkdist-cleanup                  # dry-run (default)
    apkdist-cleanup --delete         # actually delete old files from Drive
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .config import default_token_path, load_environment, user_config_dir


def get_drive_credentials(
    oauth_credentials_file: Optional[str],
    oauth_token_file: str,
    service_account_file: Optional[str],
):
    """Return Drive API credentials using OAuth or service account."""
    scopes = ["https://www.googleapis.com/auth/drive"]

    if oauth_credentials_file:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = None
        if os.path.isfile(oauth_token_file):
            creds = Credentials.from_authorized_user_file(oauth_token_file, scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(oauth_credentials_file, scopes)
                creds = flow.run_local_server(port=0)
            Path(oauth_token_file).parent.mkdir(parents=True, exist_ok=True)
            with open(oauth_token_file, "w", encoding="utf-8") as handle:
                handle.write(creds.to_json())
        return creds

    if service_account_file:
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(service_account_file, scopes=scopes)

    print("❌ Set GOOGLE_APPLICATION_CREDENTIALS or OAUTH_CREDENTIALS_FILE in .env")
    sys.exit(1)


def cleanup_drive(
    folder_id: str,
    max_age_days: int,
    delete: bool,
    oauth_credentials_file: Optional[str],
    oauth_token_file: str,
    service_account_file: Optional[str],
):
    """List and optionally delete APK files older than max_age_days from Google Drive."""
    from googleapiclient.discovery import build

    try:
        creds = get_drive_credentials(oauth_credentials_file, oauth_token_file, service_account_file)
        service = build("drive", "v3", credentials=creds)
    except Exception as exc:
        print(f"❌ Google Drive auth failed: {exc}")
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    query = (
        f"'{folder_id}' in parents"
        f" and name contains '.apk'"
        f" and createdTime < '{cutoff_str}'"
        f" and trashed = false"
    )

    try:
        results = service.files().list(
            q=query,
            fields="files(id, name, createdTime, size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            orderBy="createdTime",
        ).execute()
    except Exception as exc:
        print(f"❌ Failed to list files: {exc}")
        sys.exit(1)

    files = results.get("files", [])
    if not files:
        print(f"✅ No APK files older than {max_age_days} days found on Drive")
        return

    print(f"📦 Found {len(files)} APK(s) older than {max_age_days} days:\n")
    for item in files:
        size_mb = int(item.get("size", 0)) / (1024 * 1024)
        created = item.get("createdTime", "unknown")[:10]
        print(f"  📄 {item['name']} ({size_mb:.1f} MB, uploaded {created})")

    print()
    if not delete:
        print("ℹ️  Run with --delete to remove these files")
        return

    confirm = input(f"⚠️  Delete {len(files)} file(s) from Drive? (y/N): ").strip().lower()
    if confirm != "y":
        print("❌ Aborted — no files were deleted")
        return

    deleted = 0
    for item in files:
        try:
            service.files().delete(fileId=item["id"], supportsAllDrives=True).execute()
            deleted += 1
        except Exception as exc:
            print(f"  ❌ Failed to delete {item['name']}: {exc}")

    print(f"\n✅ Deleted {deleted}/{len(files)} file(s) from Drive")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Clean up old APK files from Google Drive")
    parser.add_argument("--days", type=int, default=7, help="Delete files older than this many days (default: 7)")
    parser.add_argument("--delete", action="store_true", help="Actually delete files (default: dry-run)")
    parser.add_argument("--env-file", help="Path to .env file")
    args = parser.parse_args(argv)

    try:
        loaded_env = load_environment(args.env_file)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    folder_id = os.getenv("DRIVE_FOLDER_ID")
    service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    oauth_credentials_file = os.getenv("OAUTH_CREDENTIALS_FILE")
    oauth_token_file = os.getenv("OAUTH_TOKEN_FILE") or str(default_token_path())

    if loaded_env:
        print(f"📄 Loaded config: {loaded_env}")
    elif not args.env_file:
        print(f"ℹ️  No .env found in current directory; tried global config at {user_config_dir()}")

    if not folder_id:
        print("❌ Set DRIVE_FOLDER_ID in your .env")
        sys.exit(1)

    if not args.delete:
        print("🧹 Cleanup dry-run (no files will be deleted)\n")

    cleanup_drive(
        folder_id=folder_id,
        max_age_days=args.days,
        delete=args.delete,
        oauth_credentials_file=oauth_credentials_file,
        oauth_token_file=oauth_token_file,
        service_account_file=service_account_file,
    )


if __name__ == "__main__":
    main()
