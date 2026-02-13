#!/usr/bin/env python3
"""
Cleanup script — deletes APK files older than 7 days from Google Drive.

Usage:
    python cleanup.py                          # dry-run (default, just lists old files)
    python cleanup.py --delete                 # actually delete old files from Drive
    python cleanup.py --days 14 --delete       # delete files older than 14 days
"""

import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

DRIVE_FOLDER_ID = os.getenv('DRIVE_FOLDER_ID')
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
OAUTH_CREDENTIALS_FILE = os.getenv('OAUTH_CREDENTIALS_FILE')
OAUTH_TOKEN_FILE = os.getenv('OAUTH_TOKEN_FILE', 'token.json')


def get_drive_credentials():
    """Returns Drive API credentials using OAuth or service account."""
    scopes = ['https://www.googleapis.com/auth/drive']

    if OAUTH_CREDENTIALS_FILE:
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials

        creds = None
        if os.path.isfile(OAUTH_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(OAUTH_TOKEN_FILE, scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CREDENTIALS_FILE, scopes)
                creds = flow.run_local_server(port=0)
            with open(OAUTH_TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
        return creds

    if SERVICE_ACCOUNT_FILE:
        return service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)

    print("❌ Set GOOGLE_APPLICATION_CREDENTIALS or OAUTH_CREDENTIALS_FILE in .env")
    sys.exit(1)


def cleanup_drive(folder_id, max_age_days=7, delete=False):
    """Lists and optionally deletes APK files older than max_age_days from Google Drive."""
    try:
        creds = get_drive_credentials()
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"❌ Google Drive auth failed: {e}")
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    cutoff_str = cutoff.strftime('%Y-%m-%dT%H:%M:%S')

    query = (
        f"'{folder_id}' in parents"
        f" and name contains '.apk'"
        f" and createdTime < '{cutoff_str}'"
        f" and trashed = false"
    )

    try:
        results = service.files().list(
            q=query,
            fields='files(id, name, createdTime, size)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            orderBy='createdTime'
        ).execute()
    except Exception as e:
        print(f"❌ Failed to list files: {e}")
        sys.exit(1)

    files = results.get('files', [])

    if not files:
        print(f"✅ No APK files older than {max_age_days} days found on Drive")
        return

    print(f"📦 Found {len(files)} APK(s) older than {max_age_days} days:\n")

    for f in files:
        size_mb = int(f.get('size', 0)) / (1024 * 1024)
        created = f.get('createdTime', 'unknown')[:10]
        print(f"  📄 {f['name']} ({size_mb:.1f} MB, uploaded {created})")

    print()
    if not delete:
        print(f"ℹ️  Run with --delete to remove these files")
        return

    confirm = input(f"⚠️  Delete {len(files)} file(s) from Drive? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Aborted — no files were deleted")
        return

    deleted = 0
    for f in files:
        try:
            service.files().delete(fileId=f['id'], supportsAllDrives=True).execute()
            deleted += 1
        except Exception as e:
            print(f"  ❌ Failed to delete {f['name']}: {e}")

    print(f"\n✅ Deleted {deleted}/{len(files)} file(s) from Drive")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Clean up old APK files from Google Drive')
    parser.add_argument('--days', type=int, default=7, help='Delete files older than this many days (default: 7)')
    parser.add_argument('--delete', action='store_true', help='Actually delete files (default: dry-run)')
    args = parser.parse_args()

    if not DRIVE_FOLDER_ID:
        print("❌ Set DRIVE_FOLDER_ID in .env")
        sys.exit(1)

    if not args.delete:
        print("🧹 Cleanup dry-run (no files will be deleted)\n")

    cleanup_drive(DRIVE_FOLDER_ID, max_age_days=args.days, delete=args.delete)

