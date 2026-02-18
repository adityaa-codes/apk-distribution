from __future__ import annotations

import os
import platform
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
