# APK Distribution Pipeline

A single-command pipeline that bumps your Android app version, builds the APK via Gradle, uploads it to Google Drive, and sends a download link to Telegram.

## Why?

Not every team needs (or wants) Google Play for internal distribution. Maybe you don't have a Play Console account, maybe you're distributing to a small group of testers, or maybe you just want something simpler. This tool gives you a one-command workflow: bump version → build → upload → notify — all without touching a store.

## How It Works

```
bump version → build APK → upload to Google Drive → notify via Telegram
```

1. **Version Bump** — Reads `version.properties` from your Android module, increments the version (`major` / `minor` / `patch`), and writes it back atomically.
2. **Gradle Build** — Runs `./gradlew :<module>:assemble<Variant>` inside your Android project.
3. **Drive Upload** — Uploads the generated APK to a Google Drive folder using a service account, sets it to "anyone with link can view", and generates a direct download URL.
4. **Telegram Notification** — Sends a formatted message to a Telegram chat with inline buttons for downloading the APK and opening the Drive folder.

## Prerequisites

- **Python 3.8+**
- **Android SDK** installed (auto-detected from `ANDROID_HOME`, `ANDROID_SDK_ROOT`, or common paths)
- **Gradle Wrapper** (`gradlew` / `gradlew.bat`) present in your Android project root
- A **Google Cloud** project with Drive API enabled (service account or OAuth credentials)
- A **Telegram Bot** token (create one via [@BotFather](https://t.me/BotFather))

### Supported Platforms

| Platform | Android Studio | SDK | Java | gradlew |
|---|---|---|---|---|
| **Linux** | `~/android-studio`, `/opt/android-studio`, `/usr/local/android-studio` | `~/Android/Sdk` | `/usr/lib/jvm/java-*`, bundled JBR | `gradlew` |
| **macOS** | `/Applications/Android Studio.app` | `~/Library/Android/sdk` | `/Library/Java/JavaVirtualMachines`, bundled JBR | `gradlew` |
| **Windows** | `%PROGRAMFILES%\Android\Android Studio`, `%LOCALAPPDATA%\Android\Android Studio` | `%LOCALAPPDATA%\Android\Sdk` | bundled JBR | `gradlew.bat` |

## Environment Check

Run the helper script to verify your build environment before using the pipeline:

```bash
python env_check.py --project /path/to/your/android/project
```

Example output:

```
🔍 Scanning build environment...

  ✅ Android Studio : /opt/android-studio
  ✅ Android SDK     : /home/user/Android/Sdk
  ✅ Java            : /usr/lib/jvm/java-17-openjdk-amd64
                       openjdk version "17.0.8" 2023-07-18
  ✅ gradlew         : /home/user/projects/my-app/gradlew

✅ Environment looks good!

💡 Suggested exports for your shell:
   export ANDROID_HOME=/home/user/Android/Sdk
   export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a `.env` File

Create a `.env` file in the same directory as `main.py`:

```env
# Required
ANDROID_PROJECT_PATH=/path/to/your/android/project
DRIVE_FOLDER_ID=your_google_drive_folder_id
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Drive auth — set ONE of these (see Google Drive Setup below)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
# OAUTH_CREDENTIALS_FILE=/path/to/credentials.json
# OAUTH_TOKEN_FILE=token.json

# Optional (defaults shown)
APP_MODULE_NAME=app
```

> ⚡ = at least one of `GOOGLE_APPLICATION_CREDENTIALS` or `OAUTH_CREDENTIALS_FILE` is required.

| Variable | Required | Description |
|---|---|---|
| `ANDROID_PROJECT_PATH` | ✅ | Absolute path to Android project root (where `gradlew` lives) |
| `DRIVE_FOLDER_ID` | ✅ | Google Drive folder ID to upload APKs into |
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | Telegram chat/group/channel ID to send notifications to |
| `GOOGLE_APPLICATION_CREDENTIALS` | ⚡ | Path to service account JSON key (for Shared Drives) |
| `OAUTH_CREDENTIALS_FILE` | ⚡ | Path to OAuth client credentials JSON (for personal accounts) |
| `OAUTH_TOKEN_FILE` | ❌ | Path to save OAuth token (default: `token.json`) |
| `APP_MODULE_NAME` | ❌ | Android module name (default: `app`) |
| `GOOGLE_DELEGATE_EMAIL` | ❌ | Email to impersonate via OAuth delegation (for Google Workspace users) |
| `BUILD_VARIANT` | ❌ | Gradle build variant, passed via `--variant` CLI flag (default: `release`) |

### 3. Android Project Setup

Your Android module must have a `version.properties` file at `<project>/<module>/version.properties`:

```properties
VERSION_CODE=1
VERSION_NAME=1.0.0
```

Your `build.gradle` should read from this file to set `versionCode` and `versionName`.

### 4. Google Drive Setup

Service accounts created after April 15, 2025 no longer have storage quota ([details](https://forum.rclone.org/t/google-drive-service-account-changes-and-rclone/50136)). Choose the option that matches your account type:

---

#### Option A: Personal Google Account (OAuth consent)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project (or use an existing one).
2. **Enable the Google Drive API:**
   - Navigate to **APIs & Services → Library**
   - Search for "Google Drive API" and click **Enable**
3. **Set up OAuth consent screen:**
   - Go to **APIs & Services → OAuth consent screen**
   - User type: **External** → click Create
   - Fill in the app name and your email
   - Under **Scopes**, add `https://www.googleapis.com/auth/drive`
   - Under **Test users**, add your Google email
   - Save
4. **Create OAuth credentials:**
   - Go to **APIs & Services → Credentials**
   - Click **Create Credentials → OAuth Client ID**
   - Application type: **Desktop app**
   - Click Create, then **Download JSON**
   - Save the file as `credentials.json` in your project folder
5. **Get your Drive folder ID:**
   - Open the target folder in Google Drive
   - The folder ID is the last part of the URL: `https://drive.google.com/drive/folders/<THIS_IS_THE_FOLDER_ID>`
6. **Set in `.env`:**
   ```env
   OAUTH_CREDENTIALS_FILE=credentials.json
   DRIVE_FOLDER_ID=<your_folder_id>
   ```
7. On the **first run**, a browser window will open asking you to sign in and authorize the app. After that, a `token.json` file is saved locally and reused for future runs.

---

#### Option B: Google Workspace Account (Shared Drive + Service Account)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project (or use an existing one).
2. **Enable the Google Drive API:**
   - Navigate to **APIs & Services → Library**
   - Search for "Google Drive API" and click **Enable**
3. **Create a Service Account:**
   - Go to **IAM & Admin → Service Accounts**
   - Click **Create Service Account**, give it a name, and click Done
   - Click the service account → **Keys → Add Key → Create new key → JSON**
   - Download the JSON key file and save it as `service-account.json`
   - Note the service account email (looks like `name@project.iam.gserviceaccount.com`)
4. **Set up a Shared Drive:**
   - In Google Drive, click **Shared drives** (left sidebar) → **New shared drive**
   - Create a folder inside the Shared Drive for your APK uploads
   - Click **Manage members** on the Shared Drive and add the service account email as a **Contributor**
5. **Get the folder ID:**
   - Open the target folder in the Shared Drive
   - The folder ID is the last part of the URL: `https://drive.google.com/drive/folders/<THIS_IS_THE_FOLDER_ID>`
6. **Set in `.env`:**
   ```env
   GOOGLE_APPLICATION_CREDENTIALS=service-account.json
   DRIVE_FOLDER_ID=<folder_id_inside_shared_drive>
   ```

---

> If both `GOOGLE_APPLICATION_CREDENTIALS` and `OAUTH_CREDENTIALS_FILE` are set, OAuth takes priority.

## Usage

```bash
python main.py <bump_type> [--variant <build_variant>] [--force] [--dry-run]
```

Where `<bump_type>` is one of: `major`, `minor`, or `patch`, and `--variant` is the Gradle build variant (default: `release`).

| Flag | Description |
|---|---|
| `--variant` | Build variant (default: `release`) |
| `--force` | Force rebuild and re-upload even if a fresh APK exists |
| `--dry-run` | Simulate the pipeline without making any changes |

> **Smart caching:** If an APK was built in the last 30 minutes, the build step is skipped. If the APK already exists on Google Drive for that version, the upload step is skipped. The Telegram notification is always sent. Use `--force` to bypass both checks.

### Examples

**Patch release** (1.2.3 → 1.2.4):
```bash
python main.py patch
```

**Minor release** (1.2.4 → 1.3.0):
```bash
python main.py minor
```

**Major release** (1.3.0 → 2.0.0):
```bash
python main.py major
```

**Staging variant build**:
```bash
python main.py patch --variant staging
```

**Force rebuild and re-upload**:
```bash
python main.py patch --force
```

**Dry run** (validates config and paths without building, uploading, or notifying):
```bash
python main.py patch --dry-run
```

### Example Output

```
✅ Android SDK found at: /home/user/Android/Sdk
📁 Project: /home/user/projects/my-app
📦 Module: app | Variant: release
🔧 Gradle: /home/user/projects/my-app/gradlew
🔄 Bumping version (patch)...
✅ Version Updated: 1.2.3 -> 1.2.4
🔨 Building APK with Gradle...
✅ Build Successful!
☁️ Uploading to Google Drive...
✅ Uploaded to Google Drive!
🚀 Sending Telegram Notification...
✅ Notification Sent!
```

## Startup Checks

The script validates the following before running any pipeline step:

- All required environment variables are set
- Android SDK is detected (warns if not found)
- Android project directory exists
- `gradlew` exists and is executable (auto-fixes permissions if needed)
- Service account JSON file exists

## Troubleshooting

| Error | Fix |
|---|---|
| `Required environment variable 'X' is not set` | Add the missing variable to your `.env` file |
| `Android SDK not found` | Install Android SDK and set `ANDROID_HOME` in your shell or `.env` |
| `Could not find gradlew` | Verify `ANDROID_PROJECT_PATH` points to the correct project root |
| `Service account file not found` | Check `GOOGLE_APPLICATION_CREDENTIALS` path |
| `Could not find APK in ...` | Verify `BUILD_VARIANT` matches your Gradle config (check `build/outputs/apk/` for the actual variant folder name) |
| `Google Drive auth failed` | Ensure the service account JSON is valid and Drive API is enabled |
| `Telegram Error` | Verify your bot token and chat ID; make sure the bot is added to the chat |

## Cleanup

Old APK files pile up on Google Drive. Use the cleanup script to remove them:

```bash
python cleanup.py                        # dry-run — lists old APKs without deleting
python cleanup.py --delete               # lists APKs older than 7 days, asks for confirmation, then deletes
python cleanup.py --days 14 --delete     # same but for APKs older than 14 days
```

The `--delete` flag always shows the file list first and asks for a `y/N` confirmation before removing anything.

## License

This project is licensed under the [MIT License](LICENSE.md).
