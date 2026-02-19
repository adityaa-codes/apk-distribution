import json
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class TelegramDeliveryPlan:
    send_message: bool
    send_document: bool
    skip_document_reason: Optional[str] = None


def _telegram_api_url(base_url: str, telegram_token: str, method: str) -> str:
    return f"{base_url}/bot{telegram_token}/{method}"


def _telegram_ok(response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    return response.status_code == 200 and bool(payload.get("ok"))


def is_cloud_telegram_api(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host == "api.telegram.org"


def build_delivery_plan(
    *,
    is_cloud_api: bool,
    send_document: bool,
    apk_size_bytes: Optional[int],
    cloud_document_limit_mb: int,
) -> TelegramDeliveryPlan:
    if not send_document:
        return TelegramDeliveryPlan(send_message=True, send_document=False)

    if apk_size_bytes is None:
        return TelegramDeliveryPlan(
            send_message=True,
            send_document=False,
            skip_document_reason="Could not read APK file size.",
        )

    if is_cloud_api:
        limit_bytes = cloud_document_limit_mb * 1024 * 1024
        if apk_size_bytes > limit_bytes:
            apk_size_mb = apk_size_bytes / (1024 * 1024)
            return TelegramDeliveryPlan(
                send_message=True,
                send_document=False,
                skip_document_reason=(
                    "APK is too large for cloud Bot API "
                    f"({apk_size_mb:.2f} MB > {cloud_document_limit_mb} MB)."
                ),
            )

    return TelegramDeliveryPlan(
        send_message=is_cloud_api,
        send_document=True,
    )


def send_release_notification(
    *,
    version_name: str,
    direct_link: Optional[str],
    drive_folder_id: Optional[str],
    variant: str,
    telegram_token: str,
    chat_id: str,
    thread_id: Optional[int],
    telegram_api_base_url: str,
    apk_path: str,
    send_document: bool,
    cloud_document_limit_mb: int,
) -> None:
    import requests

    print("🚀 Sending Telegram Notification...")
    is_cloud_api = is_cloud_telegram_api(telegram_api_base_url)

    try:
        apk_size_bytes = os.path.getsize(apk_path) if send_document else None
    except OSError:
        apk_size_bytes = None

    plan = build_delivery_plan(
        is_cloud_api=is_cloud_api,
        send_document=send_document,
        apk_size_bytes=apk_size_bytes,
        cloud_document_limit_mb=cloud_document_limit_mb,
    )

    folder_link = f"https://drive.google.com/drive/folders/{drive_folder_id}" if drive_folder_id else None
    link_buttons = []
    if direct_link:
        link_buttons.append([{"text": "⬇️ Download APK", "url": direct_link}])
    if folder_link:
        link_buttons.append([{"text": "📂 Open Drive Folder", "url": folder_link}])

    if plan.send_message:
        hint = "<i>Tap below to update directly.</i>" if link_buttons else "<i>APK attached when available.</i>"
        message = (
            "<b>🚀 New Update Released!</b>\n\n"
            f"<b>Version:</b> {version_name}\n"
            f"<b>Branch:</b> {variant.capitalize()}\n\n"
            f"{hint}"
        )

        url = _telegram_api_url(telegram_api_base_url, telegram_token, "sendMessage")
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        if link_buttons:
            payload["reply_markup"] = {"inline_keyboard": link_buttons}
        if thread_id is not None:
            payload["message_thread_id"] = thread_id

        response = requests.post(url, json=payload, timeout=30)
        if not _telegram_ok(response):
            print(f"❌ Telegram Error: {response.text}")
        else:
            print("✅ Notification Sent!")

    if plan.skip_document_reason:
        print(f"⚠️  Skipping sendDocument — {plan.skip_document_reason}")

    if not plan.send_document:
        return

    print("📎 Uploading APK to Telegram via sendDocument...")
    send_document_url = _telegram_api_url(telegram_api_base_url, telegram_token, "sendDocument")
    caption = (
        "<b>📱 APK Ready to Install</b>\n"
        f"<b>Version:</b> {version_name}\n"
        f"<b>Branch:</b> {variant.capitalize()}\n"
        "<i>If install is blocked, allow \"Install unknown apps\" for Telegram.</i>"
    )

    document_buttons = []
    if direct_link:
        document_buttons.append([{"text": "🔗 Fallback Drive Download", "url": direct_link}])
    if folder_link:
        document_buttons.append([{"text": "📂 Open Drive Folder", "url": folder_link}])

    document_payload = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML",
    }
    if document_buttons:
        document_payload["reply_markup"] = json.dumps({"inline_keyboard": document_buttons})
    if thread_id is not None:
        document_payload["message_thread_id"] = thread_id

    try:
        with open(apk_path, "rb") as handle:
            files = {
                "document": (
                    os.path.basename(apk_path),
                    handle,
                    "application/vnd.android.package-archive",
                )
            }
            response = requests.post(
                send_document_url,
                data=document_payload,
                files=files,
                timeout=180,
            )
    except OSError as exc:
        print(f"❌ Telegram sendDocument Error: Could not read APK file: {exc}")
        return

    if not _telegram_ok(response):
        print(f"❌ Telegram sendDocument Error: {response.text}")
    else:
        print("✅ APK uploaded to Telegram!")
