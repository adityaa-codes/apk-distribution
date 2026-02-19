# APK Distribution Pipeline

`apkdist` builds an Android APK, uploads it to Google Drive, and sends a Telegram release message.

## Quickstart

1. Install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

2. Create `.env` from `.env.example` and set required values.

3. Validate toolchain:

```bash
apkdist env-check --project /absolute/path/to/android-project
```

4. Run a dry run:

```bash
apkdist make patch --dry-run
```

5. Run a real release:

```bash
apkdist make patch release
```

## What It Does

```text
bump version -> build APK -> upload to Drive -> notify in Telegram
```

- Bumps `<module>/version.properties`.
- Runs `:module:assemble<Variant>` with Gradle Wrapper.
- Uploads APK to Drive and generates a direct download link.
- Sends Telegram notification and optionally `sendDocument`.

## Commands

```bash
apkdist make <major|minor|patch> [variant] [--force] [--dry-run] [--env-file PATH]
apkdist env-check [--project PATH]
apkdist cleanup [--days 7] [--delete] [--env-file PATH]
apkdist telegram-updates [--timeout 10] [--env-file PATH]
```

## Required Environment

Minimum `.env`:

```env
ANDROID_PROJECT_PATH=/absolute/path/to/android-project
DRIVE_FOLDER_ID=google_drive_folder_id
TELEGRAM_BOT_TOKEN=bot_token
TELEGRAM_CHAT_ID=-1001234567890

# Set one Drive auth mode:
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
# OAUTH_CREDENTIALS_FILE=/absolute/path/to/credentials.json
```

### Environment Variables

| Variable | Required | Notes |
|---|---|---|
| `ANDROID_PROJECT_PATH` | Yes | Android project root where `gradlew` exists |
| `APP_MODULE_NAME` | No | Default `app` |
| `DRIVE_FOLDER_ID` | Yes | Target Drive folder |
| `GOOGLE_APPLICATION_CREDENTIALS` | One of two | Service account JSON |
| `OAUTH_CREDENTIALS_FILE` | One of two | OAuth desktop credentials |
| `OAUTH_TOKEN_FILE` | No | Default: platform config dir token path |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Chat/group/channel id |
| `TELEGRAM_THREAD_ID` | No | Topic/thread id |
| `TELEGRAM_SEND_DOCUMENT` | No | Default `true` |
| `TELEGRAM_CLOUD_DOCUMENT_LIMIT_MB` | No | Default `50`, cloud API only |
| `TELEGRAM_API_BASE_URL` | No | Default `https://api.telegram.org` |
| `TELEGRAM_API_ID` | No | Needed only for local bot API container |
| `TELEGRAM_API_HASH` | No | Needed only for local bot API container |

## Telegram Chat and Thread Discovery

Use:

```bash
apkdist telegram-updates --timeout 10
```

It prints discovered `chat_id` and optional `thread_id` values from Telegram `getUpdates`.

## Telegram Delivery Behavior

- Drive upload happens on every run.
- Cloud Bot API (`api.telegram.org`):
  - Sends text message.
  - Sends document only when APK size is within `TELEGRAM_CLOUD_DOCUMENT_LIMIT_MB`.
- Local Bot API server:
  - With `TELEGRAM_SEND_DOCUMENT=true`, sends one document message (single release message).
  - Caption includes fallback Drive link button.

## Optional: Local Telegram Bot API Server (Separate Container)

This repository includes `docker-compose.yml` for `telegram-bot-api` only.
The APK pipeline runs locally on host and calls that server.

1. Add in `.env`:

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
TELEGRAM_API_BASE_URL=http://localhost:8081
```

2. Start server:

```bash
docker compose up -d telegram-bot-api
```

3. Run `apkdist` from host as usual.

## Google Drive Auth Modes

### Service account (recommended for shared/team setup)

- Enable Drive API in Google Cloud.
- Create service account and key JSON.
- Share target Drive folder/shared drive with service account email.
- Set `GOOGLE_APPLICATION_CREDENTIALS` and `DRIVE_FOLDER_ID`.

### OAuth desktop app (personal Google Drive)

- Enable Drive API in Google Cloud.
- Create OAuth client credentials (Desktop app).
- Set `OAUTH_CREDENTIALS_FILE`.
- First run opens browser consent and stores token in `OAUTH_TOKEN_FILE`.

## Cleanup Old APKs

```bash
apkdist cleanup --days 14
apkdist cleanup --days 14 --delete
```

`--delete` always prompts for confirmation.

## Troubleshooting

| Problem | Action |
|---|---|
| `Required environment variable ... not set` | Fill `.env` and rerun |
| `Could not find gradlew` | Confirm `ANDROID_PROJECT_PATH` points to Android root |
| `Service account file not found` | Use absolute path for credentials JSON |
| `Could not find APK in ...` | Verify build variant folder under `build/outputs/apk/` |
| `Telegram sendDocument Error` | Use local Bot API server or lower APK size |

## Development Checks

Before submitting changes:

```bash
python -m py_compile apkdist/cli.py apkdist/pipeline.py apkdist/env_check.py apkdist/cleanup.py apkdist/config.py apkdist/telegram.py apkdist/drive_auth.py apkdist/telegram_updates.py
apkdist make patch --dry-run
```

## License

[MIT](LICENSE.md)
