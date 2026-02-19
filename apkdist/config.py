from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def user_config_dir() -> Path:
    """Return the platform-specific config directory for apkdist."""
    if platform.system() == "Windows":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "apkdist"
        return Path.home() / "AppData" / "Roaming" / "apkdist"

    xdg_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_home:
        return Path(xdg_home) / "apkdist"
    return Path.home() / ".config" / "apkdist"


def default_env_path() -> Path:
    """Return the standard .env location for global installs."""
    return user_config_dir() / ".env"


def default_token_path() -> Path:
    """Return the standard OAuth token location for global installs."""
    return user_config_dir() / "token.json"


@dataclass(frozen=True)
class PipelineConfig:
    android_root: str
    module_name: str
    build_variant: str
    telegram_token: str
    chat_id: str
    thread_id: Optional[int]
    telegram_api_base_url: str
    drive_folder_id: str
    send_document: bool
    cloud_document_limit_mb: int
    service_account_file: Optional[str]
    oauth_credentials_file: Optional[str]
    oauth_token_file: str


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise ValueError(f"Required environment variable '{name}' is not set.")
    return value.strip()


def _optional_int_env(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable '{name}' must be an integer.") from exc


def _optional_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable '{name}' must be a boolean (true/false).")


def _optional_positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable '{name}' must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"Environment variable '{name}' must be > 0.")
    return parsed


def _telegram_api_base_url() -> str:
    base = os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org").strip()
    if not base:
        raise ValueError("TELEGRAM_API_BASE_URL cannot be empty.")
    return base.rstrip("/")


def load_pipeline_config(variant: str) -> PipelineConfig:
    service_account_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    oauth_credentials_file = os.getenv("OAUTH_CREDENTIALS_FILE")
    oauth_token_file = os.getenv("OAUTH_TOKEN_FILE") or str(default_token_path())

    return PipelineConfig(
        android_root=os.path.abspath(_require_env("ANDROID_PROJECT_PATH")),
        module_name=os.getenv("APP_MODULE_NAME", "app"),
        build_variant=variant,
        telegram_token=_require_env("TELEGRAM_BOT_TOKEN"),
        chat_id=_require_env("TELEGRAM_CHAT_ID"),
        thread_id=_optional_int_env("TELEGRAM_THREAD_ID"),
        telegram_api_base_url=_telegram_api_base_url(),
        drive_folder_id=_require_env("DRIVE_FOLDER_ID"),
        send_document=_optional_bool_env("TELEGRAM_SEND_DOCUMENT", default=True),
        cloud_document_limit_mb=_optional_positive_int_env(
            "TELEGRAM_CLOUD_DOCUMENT_LIMIT_MB",
            default=50,
        ),
        service_account_file=service_account_file,
        oauth_credentials_file=oauth_credentials_file,
        oauth_token_file=oauth_token_file,
    )


def load_environment(env_file: Optional[str] = None) -> Optional[Path]:
    """
    Load environment variables from one source.

    Priority:
    1) --env-file path (explicit)
    2) ./.env (current working directory)
    3) platform config path (~/.config/apkdist/.env or %APPDATA%/apkdist/.env)
    """
    if env_file:
        path = Path(env_file).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f".env file not found: {path}")
        load_dotenv(dotenv_path=path, override=False)
        return path

    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        load_dotenv(dotenv_path=cwd_env, override=False)
        return cwd_env

    global_env = default_env_path()
    if global_env.is_file():
        load_dotenv(dotenv_path=global_env, override=False)
        return global_env

    return None
