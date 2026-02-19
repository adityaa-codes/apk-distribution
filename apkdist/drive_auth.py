from pathlib import Path
from typing import Optional
import os
import sys


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
        print("   Using OAuth (personal account)")
        return creds

    if not service_account_file:
        print("❌ Error: Drive credentials are not configured.")
        sys.exit(1)

    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(service_account_file, scopes=scopes)
    print("   Using service account (Shared Drive)")
    return creds
