import os
import sys
import re
import subprocess
import platform
import time
import requests
import argparse
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from env_check import find_android_sdk, find_java, find_gradlew, find_android_studio

# 1. Load Environment Variables
load_dotenv()


def _require_env(name):
    """Exit with a clear error if a required env var is missing."""
    value = os.getenv(name)
    if not value:
        print(f"❌ Error: Required environment variable '{name}' is not set.")
        sys.exit(1)
    return value


def _find_android_sdk():
    """Detects Android SDK from env vars or common install paths."""
    return find_android_sdk()


# Configuration from .env
ANDROID_ROOT = os.path.abspath(_require_env('ANDROID_PROJECT_PATH'))
MODULE_NAME = os.getenv('APP_MODULE_NAME', 'app')
BUILD_VARIANT = None  # Set via CLI argument
DRIVE_FOLDER_ID = _require_env('DRIVE_FOLDER_ID')
TELEGRAM_TOKEN = _require_env('TELEGRAM_BOT_TOKEN')
CHAT_ID = _require_env('TELEGRAM_CHAT_ID')
SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
OAUTH_CREDENTIALS_FILE = os.getenv('OAUTH_CREDENTIALS_FILE')
OAUTH_TOKEN_FILE = os.getenv('OAUTH_TOKEN_FILE', 'token.json')

IS_WINDOWS = platform.system() == 'Windows'

# Derived Paths
_gradlew_name = 'gradlew.bat' if IS_WINDOWS else 'gradlew'
GRADLEW_EXEC = os.path.join(ANDROID_ROOT, _gradlew_name)
VERSION_FILE = os.path.join(ANDROID_ROOT, MODULE_NAME, 'version.properties')
APK_OUTPUT_DIR = None  # Set after CLI args are parsed

# Detect Android Studio
_studio = find_android_studio()
if _studio:
    print(f"✅ Android Studio found at: {_studio}")
else:
    print("⚠️  Warning: Android Studio not found.")

# Detect Android SDK
_android_sdk = _find_android_sdk()
if _android_sdk:
    print(f"✅ Android SDK found at: {_android_sdk}")
    os.environ.setdefault('ANDROID_HOME', _android_sdk)
else:
    print("⚠️  Warning: Android SDK not found. Set ANDROID_HOME if the build fails.")

# Detect Java
_java_home = find_java()
if _java_home:
    print(f"✅ Java found at: {_java_home}")
    os.environ.setdefault('JAVA_HOME', _java_home)
else:
    print("⚠️  Warning: Java not found. Set JAVA_HOME if the build fails.")

# Check Android project directory exists
if not os.path.isdir(ANDROID_ROOT):
    print(f"❌ Error: Android project directory not found: {ANDROID_ROOT}")
    sys.exit(1)

# Check Gradle Wrapper exists and is executable
if not os.path.exists(GRADLEW_EXEC):
    print(f"❌ Error: Could not find gradlew at: {GRADLEW_EXEC}")
    print("   Check ANDROID_PROJECT_PATH in your .env file.")
    sys.exit(1)

if not os.access(GRADLEW_EXEC, os.X_OK) and not IS_WINDOWS:
    print("⚠️  gradlew is not executable, fixing permissions...")
    os.chmod(GRADLEW_EXEC, 0o755)

# Validate Drive auth config — need at least one method
if not SERVICE_ACCOUNT_FILE and not OAUTH_CREDENTIALS_FILE:
    print("❌ Error: Set GOOGLE_APPLICATION_CREDENTIALS (service account) or OAUTH_CREDENTIALS_FILE (OAuth) in .env")
    sys.exit(1)

if SERVICE_ACCOUNT_FILE and not os.path.isfile(SERVICE_ACCOUNT_FILE):
    print(f"❌ Error: Service account file not found: {SERVICE_ACCOUNT_FILE}")
    sys.exit(1)

if OAUTH_CREDENTIALS_FILE and not os.path.isfile(OAUTH_CREDENTIALS_FILE):
    print(f"❌ Error: OAuth credentials file not found: {OAUTH_CREDENTIALS_FILE}")
    sys.exit(1)

print(f"📁 Project: {ANDROID_ROOT}")
print(f"🔧 Gradle: {GRADLEW_EXEC}")


def bump_version(bump_type):
    """Reads version.properties from the Android project, bumps it, and saves it."""
    print(f"🔄 Bumping version ({bump_type})...")

    props = {}
    # Read existing
    try:
        with open(VERSION_FILE, 'r') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    props[key] = value
    except FileNotFoundError:
        print(f"❌ Error: version.properties not found at {VERSION_FILE}")
        sys.exit(1)

    # Logic
    version_code = int(props.get('VERSION_CODE', 1))
    version_name = props.get('VERSION_NAME', '1.0.0')

    raw_parts = version_name.split('.')
    if len(raw_parts) != 3:
        print(f"❌ Error: Invalid VERSION_NAME '{version_name}', expected X.Y.Z format")
        sys.exit(1)
    try:
        parts = list(map(int, raw_parts))
    except ValueError:
        print(f"❌ Error: VERSION_NAME '{version_name}' contains non-numeric parts")
        sys.exit(1)

    if bump_type == 'major':
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    elif bump_type == 'minor':
        parts[1] += 1
        parts[2] = 0
    elif bump_type == 'patch':
        parts[2] += 1

    new_version_name = ".".join(map(str, parts))
    new_version_code = version_code + 1

    # Write back atomically to avoid corruption on crash
    tmp_file = VERSION_FILE + '.tmp'
    with open(tmp_file, 'w') as f:
        f.write(f"VERSION_CODE={new_version_code}\n")
        f.write(f"VERSION_NAME={new_version_name}\n")
    os.replace(tmp_file, VERSION_FILE)

    print(f"✅ Version Updated: {version_name} -> {new_version_name}")
    return new_version_name


def get_app_name(variant):
    """Parses appName from build.gradle.kts manifestPlaceholders for the given variant."""
    gradle_file = os.path.join(ANDROID_ROOT, MODULE_NAME, 'build.gradle.kts')
    if not os.path.isfile(gradle_file):
        gradle_file = os.path.join(ANDROID_ROOT, MODULE_NAME, 'build.gradle')
    if not os.path.isfile(gradle_file):
        return None

    try:
        content = open(gradle_file, 'r').read()
    except OSError:
        return None

    # Match variant block and its appName, e.g.: create("staging") { ... manifestPlaceholders["appName"] = "Suuz-Staging" ... }
    # For release/debug (no create()), match: release { ... manifestPlaceholders["appName"] = "Suuz" ... }
    variant_lower = variant.lower()

    # Try create("<variant>") { ... } blocks first, then bare <variant> { ... }
    for pattern in [
        rf'create\(\s*"{variant_lower}"\s*\)\s*\{{([^}}]*)\}}',
        rf'\b{variant_lower}\s*\{{([^}}]*)\}}',
    ]:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            block = match.group(1)
            name_match = re.search(r'manifestPlaceholders\s*\[\s*"appName"\s*\]\s*=\s*"([^"]+)"', block)
            if name_match:
                return name_match.group(1)

    # Fallback: check defaultConfig
    default_match = re.search(r'defaultConfig\s*\{([^}]*)\}', content, re.DOTALL)
    if default_match:
        name_match = re.search(r'manifestPlaceholders\s*\[\s*"appName"\s*\]\s*=\s*"([^"]+)"', default_match.group(1))
        if name_match:
            return name_match.group(1)

    return None


def build_apk():
    """Runs the Gradle build command inside the Android project directory."""
    print("🔨 Building APK with Gradle...")

    # We must run this command *inside* the Android project dir for Gradle to work happily
    variant_task = BUILD_VARIANT.capitalize()
    gradlew_cmd = 'gradlew.bat' if IS_WINDOWS else './gradlew'
    cmd = [gradlew_cmd, f":{MODULE_NAME}:assemble{variant_task}"]

    try:
        # cwd=ANDROID_ROOT is crucial here
        result = subprocess.run(cmd, cwd=ANDROID_ROOT, check=True, capture_output=False)
        print("✅ Build Successful!")
    except subprocess.CalledProcessError as e:
        print("❌ Build Failed!")
        sys.exit(1)


def find_apk_file():
    """Finds the generated APK file."""
    # Sometimes the APK name changes (e.g., app-release.apk or app-release-unsigned.apk)
    # This function looks for the most recently modified .apk file in the output dir
    if not os.path.exists(APK_OUTPUT_DIR):
        return None

    files = [os.path.join(APK_OUTPUT_DIR, f) for f in os.listdir(APK_OUTPUT_DIR) if f.endswith('.apk')]
    if not files:
        return None

    # Return the most recent file
    return max(files, key=os.path.getmtime)


def is_apk_fresh(apk_path, max_age_mins=30):
    """Returns True if the APK was modified within max_age_mins."""
    if not apk_path:
        return False
    age_secs = time.time() - os.path.getmtime(apk_path)
    return age_secs < (max_age_mins * 60)


def find_on_drive(version_name):
    """Checks if an APK for this version already exists on Drive. Returns download link or None."""
    try:
        creds = _get_drive_credentials()
        service = build('drive', 'v3', credentials=creds)
        query = f"name = '{APP_NAME}-v{version_name}.apk' and '{DRIVE_FOLDER_ID}' in parents and trashed = false"
        results = service.files().list(
            q=query, fields='files(id)', supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = results.get('files', [])
        if files:
            file_id = files[0]['id']
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    except Exception as e:
        print(f"⚠️  Could not check Drive for existing APK: {e}")
    return None


def _get_drive_credentials():
    """Returns Drive API credentials using OAuth (personal) or service account (Shared Drive)."""
    scopes = ['https://www.googleapis.com/auth/drive']

    # Option 1: OAuth consent flow (personal accounts)
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
        print("   Using OAuth (personal account)")
        return creds

    # Option 2: Service account (Shared Drives / Workspace)
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    print("   Using service account (Shared Drive)")
    return creds


def upload_to_drive(file_path, version_name):
    """Uploads to Google Drive (supports Shared Drives and OAuth consent)."""
    print("☁️ Uploading to Google Drive...")

    try:
        creds = _get_drive_credentials()
        service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"❌ Google Drive auth failed: {e}")
        sys.exit(1)

    file_metadata = {
        'name': f'{APP_NAME}-v{version_name}.apk',
        'parents': [DRIVE_FOLDER_ID]
    }

    media = MediaFileUpload(file_path, mimetype='application/vnd.android.package-archive')

    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        file_id = file.get('id')

        # Permission: Anyone with link
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'},
            supportsAllDrives=True
        ).execute()
    except Exception as e:
        print(f"❌ Google Drive upload failed: {e}")
        sys.exit(1)

    print("✅ Uploaded to Google Drive!")
    # Direct Download Link (Works best for files <100MB)
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def send_telegram(version_name, direct_link, folder_id, variant):
    """Sends the formatted Telegram message."""
    print("🚀 Sending Telegram Notification...")

    folder_link = f"https://drive.google.com/drive/folders/{folder_id}"

    message = (
        f"<b>🚀 New Update Released!</b>\n\n"
        f"<b>Version:</b> {version_name}\n"
        f"<b>Branch:</b> {variant.capitalize()}\n\n"
        f"<i>Tap below to update directly.</i>"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "⬇️ Download APK", "url": direct_link}],
                [{"text": "📂 Open Drive Folder", "url": folder_link}]
            ]
        }
    }

    res = requests.post(url, json=payload)
    try:
        ok = res.status_code == 200 and res.json().get('ok')
    except ValueError:
        ok = False
    if not ok:
        print(f"❌ Telegram Error: {res.text}")
    else:
        print("✅ Notification Sent!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('type', choices=['major', 'minor', 'patch'], help='Bump type')
    parser.add_argument('--variant', default='release', help='Build variant (default: release)')
    parser.add_argument('--dry-run', action='store_true', help='Simulate the pipeline without building, uploading, or notifying')
    parser.add_argument('--force', action='store_true', help='Force rebuild and re-upload even if a fresh APK exists')
    args = parser.parse_args()

    DRY_RUN = args.dry_run
    BUILD_VARIANT = args.variant
    APK_OUTPUT_DIR = os.path.join(ANDROID_ROOT, MODULE_NAME, 'build', 'outputs', 'apk', BUILD_VARIANT)

    APP_NAME = get_app_name(BUILD_VARIANT) or MODULE_NAME.capitalize()
    print(f"📦 {APP_NAME} | Module: {MODULE_NAME} | Variant: {BUILD_VARIANT}")
    if DRY_RUN:
        print("🧪 Dry-run mode — no changes will be made\n")

    # 1. Bump
    if DRY_RUN:
        props = {}
        try:
            with open(VERSION_FILE, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        props[key] = value
            version_name = props.get('VERSION_NAME', '1.0.0')
            print(f"🔄 [DRY-RUN] Would bump version ({args.type}) from {version_name}")
        except FileNotFoundError:
            print(f"❌ version.properties not found at {VERSION_FILE}")
            sys.exit(1)
        new_ver = version_name
    else:
        new_ver = bump_version(args.type)

    # 2. Build (skip if fresh APK exists and --force not set)
    if DRY_RUN:
        variant_task = BUILD_VARIANT.capitalize()
        print(f"🔨 [DRY-RUN] Would run: ./gradlew :{MODULE_NAME}:assemble{variant_task}")
    else:
        existing_apk = find_apk_file()
        if not args.force and is_apk_fresh(existing_apk):
            age_mins = int((time.time() - os.path.getmtime(existing_apk)) / 60)
            print(f"⏩ Skipping build — fresh APK found ({age_mins}m old): {existing_apk}")
            print("   Use --force to rebuild anyway.")
        else:
            build_apk()

    # 3. Find & Upload (skip upload if already on Drive and --force not set)
    if DRY_RUN:
        apk_path = find_apk_file()
        if apk_path:
            print(f"📦 [DRY-RUN] Found APK: {apk_path}")
        else:
            print(f"📦 [DRY-RUN] No existing APK in {APK_OUTPUT_DIR} (expected after a real build)")
        print(f"☁️  [DRY-RUN] Would upload to Google Drive folder: {DRIVE_FOLDER_ID}")
        print(f"🚀 [DRY-RUN] Would send Telegram notification to chat: {CHAT_ID}")
        print("\n✅ Dry-run complete — everything looks good!")
    else:
        apk_path = find_apk_file()
        if not apk_path:
            print(f"❌ Could not find APK in {APK_OUTPUT_DIR}")
            sys.exit(1)

        link = None
        if not args.force:
            link = find_on_drive(new_ver)
            if link:
                print(f"⏩ Skipping upload — APK already on Drive for v{new_ver}")

        if not link:
            link = upload_to_drive(apk_path, new_ver)

        # 4. Notify
        send_telegram(new_ver, link, DRIVE_FOLDER_ID, BUILD_VARIANT)