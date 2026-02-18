#!/usr/bin/env python3
"""APK build/distribution pipeline CLI."""

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

from .config import default_token_path, load_environment, user_config_dir
from .env_check import find_android_sdk, find_android_studio, find_java


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"❌ Error: Required environment variable '{name}' is not set.")
        sys.exit(1)
    return value


def read_version_name(version_file: str) -> str:
    props = {}
    try:
        with open(version_file, "r", encoding="utf-8") as handle:
            for line in handle:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    props[key] = value
    except FileNotFoundError:
        print(f"❌ version.properties not found at {version_file}")
        sys.exit(1)
    return props.get("VERSION_NAME", "1.0.0")


def bump_version(version_file: str, bump_type: str) -> str:
    """Read version.properties from Android project, bump it, and save it."""
    print(f"🔄 Bumping version ({bump_type})...")

    props: Dict[str, str] = {}
    try:
        with open(version_file, "r", encoding="utf-8") as handle:
            for line in handle:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    props[key] = value
    except FileNotFoundError:
        print(f"❌ Error: version.properties not found at {version_file}")
        sys.exit(1)

    version_code = int(props.get("VERSION_CODE", 1))
    version_name = props.get("VERSION_NAME", "1.0.0")

    raw_parts = version_name.split(".")
    if len(raw_parts) != 3:
        print(f"❌ Error: Invalid VERSION_NAME '{version_name}', expected X.Y.Z format")
        sys.exit(1)

    try:
        parts = list(map(int, raw_parts))
    except ValueError:
        print(f"❌ Error: VERSION_NAME '{version_name}' contains non-numeric parts")
        sys.exit(1)

    if bump_type == "major":
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    elif bump_type == "minor":
        parts[1] += 1
        parts[2] = 0
    elif bump_type == "patch":
        parts[2] += 1

    new_version_name = ".".join(map(str, parts))
    new_version_code = version_code + 1

    tmp_file = f"{version_file}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as handle:
        handle.write(f"VERSION_CODE={new_version_code}\n")
        handle.write(f"VERSION_NAME={new_version_name}\n")
    os.replace(tmp_file, version_file)

    print(f"✅ Version Updated: {version_name} -> {new_version_name}")
    return new_version_name


def get_app_name(android_root: str, module_name: str, variant: str) -> Optional[str]:
    """Parse appName from build.gradle(.kts) manifestPlaceholders for variant."""
    gradle_file = os.path.join(android_root, module_name, "build.gradle.kts")
    if not os.path.isfile(gradle_file):
        gradle_file = os.path.join(android_root, module_name, "build.gradle")
    if not os.path.isfile(gradle_file):
        return None

    try:
        with open(gradle_file, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return None

    variant_lower = variant.lower()
    patterns = [
        rf'create\(\s*"{variant_lower}"\s*\)\s*\{{([^}}]*)\}}',
        rf"\b{variant_lower}\s*\{{([^}}]*)\}}",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            block = match.group(1)
            name_match = re.search(r'manifestPlaceholders\s*\[\s*"appName"\s*\]\s*=\s*"([^"]+)"', block)
            if name_match:
                return name_match.group(1)

    default_match = re.search(r"defaultConfig\s*\{([^}]*)\}", content, re.DOTALL)
    if default_match:
        name_match = re.search(
            r'manifestPlaceholders\s*\[\s*"appName"\s*\]\s*=\s*"([^"]+)"',
            default_match.group(1),
        )
        if name_match:
            return name_match.group(1)

    return None


def build_apk(android_root: str, module_name: str, build_variant: str) -> None:
    """Run the Gradle build command inside the Android project directory."""
    print("🔨 Building APK with Gradle...")

    variant_task = build_variant.capitalize()
    is_windows = platform.system() == "Windows"
    gradlew_cmd = "gradlew.bat" if is_windows else "./gradlew"
    cmd = [gradlew_cmd, f":{module_name}:assemble{variant_task}"]

    try:
        subprocess.run(cmd, cwd=android_root, check=True)
        print("✅ Build Successful!")
    except subprocess.CalledProcessError:
        print("❌ Build Failed!")
        sys.exit(1)


def find_apk_file(apk_output_dir: str) -> Optional[str]:
    """Find the most recently modified APK file in output dir."""
    if not os.path.exists(apk_output_dir):
        return None

    files = [
        os.path.join(apk_output_dir, name)
        for name in os.listdir(apk_output_dir)
        if name.endswith(".apk")
    ]
    if not files:
        return None

    return max(files, key=os.path.getmtime)


def is_apk_fresh(apk_path: Optional[str], max_age_mins: int = 30) -> bool:
    """Return True if APK was modified within max_age_mins."""
    if not apk_path:
        return False
    age_secs = time.time() - os.path.getmtime(apk_path)
    return age_secs < (max_age_mins * 60)


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


def find_on_drive(
    drive_folder_id: str,
    version_name: str,
    app_name: str,
    oauth_credentials_file: Optional[str],
    oauth_token_file: str,
    service_account_file: Optional[str],
) -> Optional[str]:
    """Check if APK for this version already exists on Drive."""
    from googleapiclient.discovery import build

    try:
        creds = get_drive_credentials(oauth_credentials_file, oauth_token_file, service_account_file)
        service = build("drive", "v3", credentials=creds)
        query = f"name = '{app_name}-v{version_name}.apk' and '{drive_folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = results.get("files", [])
        if files:
            file_id = files[0]["id"]
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    except Exception as exc:
        print(f"⚠️  Could not check Drive for existing APK: {exc}")

    return None


def upload_to_drive(
    file_path: str,
    version_name: str,
    app_name: str,
    drive_folder_id: str,
    oauth_credentials_file: Optional[str],
    oauth_token_file: str,
    service_account_file: Optional[str],
) -> str:
    """Upload APK to Google Drive and return direct download link."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    print("☁️ Uploading to Google Drive...")

    try:
        creds = get_drive_credentials(oauth_credentials_file, oauth_token_file, service_account_file)
        service = build("drive", "v3", credentials=creds)
    except Exception as exc:
        print(f"❌ Google Drive auth failed: {exc}")
        sys.exit(1)

    file_metadata = {
        "name": f"{app_name}-v{version_name}.apk",
        "parents": [drive_folder_id],
    }
    media = MediaFileUpload(file_path, mimetype="application/vnd.android.package-archive")

    try:
        created = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
            supportsAllDrives=True,
        ).execute()

        file_id = created.get("id")
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
    except Exception as exc:
        print(f"❌ Google Drive upload failed: {exc}")
        sys.exit(1)

    print("✅ Uploaded to Google Drive!")
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def send_telegram(
    version_name: str,
    direct_link: str,
    drive_folder_id: str,
    variant: str,
    telegram_token: str,
    chat_id: str,
) -> None:
    """Send the formatted Telegram message."""
    import requests

    print("🚀 Sending Telegram Notification...")

    folder_link = f"https://drive.google.com/drive/folders/{drive_folder_id}"
    message = (
        "<b>🚀 New Update Released!</b>\n\n"
        f"<b>Version:</b> {version_name}\n"
        f"<b>Branch:</b> {variant.capitalize()}\n\n"
        "<i>Tap below to update directly.</i>"
    )

    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "⬇️ Download APK", "url": direct_link}],
                [{"text": "📂 Open Drive Folder", "url": folder_link}],
            ]
        },
    }

    response = requests.post(url, json=payload, timeout=30)
    try:
        ok = response.status_code == 200 and response.json().get("ok")
    except ValueError:
        ok = False

    if not ok:
        print(f"❌ Telegram Error: {response.text}")
    else:
        print("✅ Notification Sent!")


def validate_environment(config: Dict[str, str]) -> None:
    """Validate local machine state and required inputs before execution."""
    android_root = config["android_root"]
    gradlew_exec = config["gradlew_exec"]
    service_account_file = config.get("service_account_file")
    oauth_credentials_file = config.get("oauth_credentials_file")

    studio = find_android_studio()
    if studio:
        print(f"✅ Android Studio found at: {studio}")
    else:
        print("⚠️  Warning: Android Studio not found.")

    android_sdk = find_android_sdk()
    if android_sdk:
        print(f"✅ Android SDK found at: {android_sdk}")
        os.environ.setdefault("ANDROID_HOME", android_sdk)
    else:
        print("⚠️  Warning: Android SDK not found. Set ANDROID_HOME if the build fails.")

    java_home = find_java()
    if java_home:
        print(f"✅ Java found at: {java_home}")
        os.environ.setdefault("JAVA_HOME", java_home)
    else:
        print("⚠️  Warning: Java not found. Set JAVA_HOME if the build fails.")

    if not os.path.isdir(android_root):
        print(f"❌ Error: Android project directory not found: {android_root}")
        sys.exit(1)

    if not os.path.exists(gradlew_exec):
        print(f"❌ Error: Could not find gradlew at: {gradlew_exec}")
        print("   Check ANDROID_PROJECT_PATH in your .env file.")
        sys.exit(1)

    if platform.system() != "Windows" and not os.access(gradlew_exec, os.X_OK):
        print("⚠️  gradlew is not executable, fixing permissions...")
        os.chmod(gradlew_exec, 0o755)

    if not service_account_file and not oauth_credentials_file:
        print("❌ Error: Set GOOGLE_APPLICATION_CREDENTIALS or OAUTH_CREDENTIALS_FILE in .env")
        sys.exit(1)

    if service_account_file and not os.path.isfile(service_account_file):
        print(f"❌ Error: Service account file not found: {service_account_file}")
        sys.exit(1)

    if oauth_credentials_file and not os.path.isfile(oauth_credentials_file):
        print(f"❌ Error: OAuth credentials file not found: {oauth_credentials_file}")
        sys.exit(1)


def main(argv=None):
    parser = argparse.ArgumentParser(description="APK distribution pipeline")
    parser.add_argument("type", choices=["major", "minor", "patch"], help="Bump type")
    parser.add_argument("--variant", default="release", help="Build variant (default: release)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the pipeline without building, uploading, or notifying",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild and re-upload even if a fresh APK exists",
    )
    parser.add_argument("--env-file", help="Path to .env file")
    args = parser.parse_args(argv)

    try:
        loaded_env = load_environment(args.env_file)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    android_root = os.path.abspath(_require_env("ANDROID_PROJECT_PATH"))
    module_name = os.getenv("APP_MODULE_NAME", "app")
    build_variant = args.variant
    drive_folder_id = _require_env("DRIVE_FOLDER_ID")
    telegram_token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")
    service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    oauth_credentials_file = os.getenv("OAUTH_CREDENTIALS_FILE")
    oauth_token_file = os.getenv("OAUTH_TOKEN_FILE") or str(default_token_path())

    is_windows = platform.system() == "Windows"
    gradlew_exec = os.path.join(android_root, "gradlew.bat" if is_windows else "gradlew")
    version_file = os.path.join(android_root, module_name, "version.properties")
    apk_output_dir = os.path.join(android_root, module_name, "build", "outputs", "apk", build_variant)

    if loaded_env:
        print(f"📄 Loaded config: {loaded_env}")
    elif not args.env_file:
        print(f"ℹ️  No .env found in current directory; tried global config at {user_config_dir()}")

    print(f"📁 Project: {android_root}")
    print(f"🔧 Gradle: {gradlew_exec}")

    validate_environment(
        {
            "android_root": android_root,
            "gradlew_exec": gradlew_exec,
            "service_account_file": service_account_file or "",
            "oauth_credentials_file": oauth_credentials_file or "",
        }
    )

    app_name = get_app_name(android_root, module_name, build_variant) or module_name.capitalize()
    print(f"📦 {app_name} | Module: {module_name} | Variant: {build_variant}")

    if args.dry_run:
        print("🧪 Dry-run mode — no changes will be made\n")
        current_version = read_version_name(version_file)
        print(f"🔄 [DRY-RUN] Would bump version ({args.type}) from {current_version}")

        variant_task = build_variant.capitalize()
        gradle_cmd = "gradlew.bat" if is_windows else "./gradlew"
        print(f"🔨 [DRY-RUN] Would run: {gradle_cmd} :{module_name}:assemble{variant_task}")

        apk_path = find_apk_file(apk_output_dir)
        if apk_path:
            print(f"📦 [DRY-RUN] Found APK: {apk_path}")
        else:
            print(f"📦 [DRY-RUN] No existing APK in {apk_output_dir} (expected after a real build)")

        print(f"☁️  [DRY-RUN] Would upload to Google Drive folder: {drive_folder_id}")
        print(f"🚀 [DRY-RUN] Would send Telegram notification to chat: {chat_id}")
        print("\n✅ Dry-run complete — everything looks good!")
        return

    new_version = bump_version(version_file, args.type)

    existing_apk = find_apk_file(apk_output_dir)
    if not args.force and is_apk_fresh(existing_apk):
        age_mins = int((time.time() - os.path.getmtime(existing_apk)) / 60)
        print(f"⏩ Skipping build — fresh APK found ({age_mins}m old): {existing_apk}")
        print("   Use --force to rebuild anyway.")
    else:
        build_apk(android_root, module_name, build_variant)

    apk_path = find_apk_file(apk_output_dir)
    if not apk_path:
        print(f"❌ Could not find APK in {apk_output_dir}")
        sys.exit(1)

    link = None
    if not args.force:
        link = find_on_drive(
            drive_folder_id=drive_folder_id,
            version_name=new_version,
            app_name=app_name,
            oauth_credentials_file=oauth_credentials_file,
            oauth_token_file=oauth_token_file,
            service_account_file=service_account_file,
        )
        if link:
            print(f"⏩ Skipping upload — APK already on Drive for v{new_version}")

    if not link:
        link = upload_to_drive(
            file_path=apk_path,
            version_name=new_version,
            app_name=app_name,
            drive_folder_id=drive_folder_id,
            oauth_credentials_file=oauth_credentials_file,
            oauth_token_file=oauth_token_file,
            service_account_file=service_account_file,
        )

    send_telegram(
        version_name=new_version,
        direct_link=link,
        drive_folder_id=drive_folder_id,
        variant=build_variant,
        telegram_token=telegram_token,
        chat_id=chat_id,
    )


if __name__ == "__main__":
    main()
