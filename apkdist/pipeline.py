#!/usr/bin/env python3
"""APK build/distribution pipeline CLI."""

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from typing import Optional

from .config import PipelineConfig, load_environment, load_pipeline_config, user_config_dir
from .drive_auth import get_drive_credentials
from .env_check import find_android_sdk, find_android_studio, find_java
from .telegram import is_cloud_telegram_api, send_release_notification


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

    props = {}
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
        creds = get_drive_credentials(
            oauth_credentials_file=oauth_credentials_file,
            oauth_token_file=oauth_token_file,
            service_account_file=service_account_file,
        )
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


def validate_environment(config: PipelineConfig) -> None:
    """Validate local machine state and required inputs before execution."""
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

    if not os.path.isdir(config.android_root):
        print(f"❌ Error: Android project directory not found: {config.android_root}")
        sys.exit(1)

    is_windows = platform.system() == "Windows"
    gradlew_exec = os.path.join(config.android_root, "gradlew.bat" if is_windows else "gradlew")
    if not os.path.exists(gradlew_exec):
        print(f"❌ Error: Could not find gradlew at: {gradlew_exec}")
        print("   Check ANDROID_PROJECT_PATH in your .env file.")
        sys.exit(1)

    if platform.system() != "Windows" and not os.access(gradlew_exec, os.X_OK):
        print("⚠️  gradlew is not executable, fixing permissions...")
        os.chmod(gradlew_exec, 0o755)

    if not config.service_account_file and not config.oauth_credentials_file:
        print("❌ Error: Set GOOGLE_APPLICATION_CREDENTIALS or OAUTH_CREDENTIALS_FILE in .env")
        sys.exit(1)

    if config.service_account_file and not os.path.isfile(config.service_account_file):
        print(f"❌ Error: Service account file not found: {config.service_account_file}")
        sys.exit(1)

    if config.oauth_credentials_file and not os.path.isfile(config.oauth_credentials_file):
        print(f"❌ Error: OAuth credentials file not found: {config.oauth_credentials_file}")
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

    try:
        config = load_pipeline_config(args.variant)
    except ValueError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)

    is_windows = platform.system() == "Windows"
    gradlew_exec = os.path.join(config.android_root, "gradlew.bat" if is_windows else "gradlew")
    version_file = os.path.join(config.android_root, config.module_name, "version.properties")
    apk_output_dir = os.path.join(
        config.android_root,
        config.module_name,
        "build",
        "outputs",
        "apk",
        config.build_variant,
    )

    if loaded_env:
        print(f"📄 Loaded config: {loaded_env}")
    elif not args.env_file:
        print(f"ℹ️  No .env found in current directory; tried global config at {user_config_dir()}")

    print(f"📁 Project: {config.android_root}")
    print(f"🔧 Gradle: {gradlew_exec}")
    if not is_cloud_telegram_api(config.telegram_api_base_url):
        print("ℹ️  Local Telegram Bot API mode detected — sendDocument is sent as a single message.")

    validate_environment(config)

    app_name = get_app_name(config.android_root, config.module_name, config.build_variant) or config.module_name.capitalize()
    print(f"📦 {app_name} | Module: {config.module_name} | Variant: {config.build_variant}")

    if args.dry_run:
        print("🧪 Dry-run mode — no changes will be made\n")
        current_version = read_version_name(version_file)
        print(f"🔄 [DRY-RUN] Would bump version ({args.type}) from {current_version}")

        variant_task = config.build_variant.capitalize()
        gradle_cmd = "gradlew.bat" if is_windows else "./gradlew"
        print(f"🔨 [DRY-RUN] Would run: {gradle_cmd} :{config.module_name}:assemble{variant_task}")

        apk_path = find_apk_file(apk_output_dir)
        if apk_path:
            print(f"📦 [DRY-RUN] Found APK: {apk_path}")
        else:
            print(f"📦 [DRY-RUN] No existing APK in {apk_output_dir} (expected after a real build)")

        print(f"☁️  [DRY-RUN] Would upload to Google Drive folder: {config.drive_folder_id}")
        if config.thread_id is None:
            print(f"🚀 [DRY-RUN] Would send Telegram notification to chat: {config.chat_id}")
        else:
            print(
                f"🚀 [DRY-RUN] Would send Telegram notification to chat: {config.chat_id} "
                f"(thread: {config.thread_id})"
            )
        print(f"🌐 [DRY-RUN] Telegram API base URL: {config.telegram_api_base_url}")
        if config.send_document:
            if is_cloud_telegram_api(config.telegram_api_base_url):
                print(
                    "📎 [DRY-RUN] Would upload APK via sendDocument when APK size <= "
                    f"{config.cloud_document_limit_mb} MB (cloud Bot API limit)"
                )
                print("📎 [DRY-RUN] If APK exceeds limit, would keep Drive-link only")
            else:
                print("📎 [DRY-RUN] Would upload APK to Telegram using sendDocument")
        else:
            print("📎 [DRY-RUN] Telegram sendDocument is disabled")
        print("\n✅ Dry-run complete — everything looks good!")
        return

    new_version = bump_version(version_file, args.type)

    existing_apk = find_apk_file(apk_output_dir)
    if not args.force and is_apk_fresh(existing_apk):
        age_mins = int((time.time() - os.path.getmtime(existing_apk)) / 60)
        print(f"⏩ Skipping build — fresh APK found ({age_mins}m old): {existing_apk}")
        print("   Use --force to rebuild anyway.")
    else:
        build_apk(config.android_root, config.module_name, config.build_variant)

    apk_path = find_apk_file(apk_output_dir)
    if not apk_path:
        print(f"❌ Could not find APK in {apk_output_dir}")
        sys.exit(1)

    link = upload_to_drive(
        file_path=apk_path,
        version_name=new_version,
        app_name=app_name,
        drive_folder_id=config.drive_folder_id,
        oauth_credentials_file=config.oauth_credentials_file,
        oauth_token_file=config.oauth_token_file,
        service_account_file=config.service_account_file,
    )

    send_release_notification(
        version_name=new_version,
        direct_link=link,
        drive_folder_id=config.drive_folder_id,
        variant=config.build_variant,
        telegram_token=config.telegram_token,
        chat_id=config.chat_id,
        thread_id=config.thread_id,
        telegram_api_base_url=config.telegram_api_base_url,
        apk_path=apk_path,
        send_document=config.send_document,
        cloud_document_limit_mb=config.cloud_document_limit_mb,
    )


if __name__ == "__main__":
    main()
