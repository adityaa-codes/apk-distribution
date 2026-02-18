#!/usr/bin/env python3
"""
Helper script to detect Android Studio, Java, and Gradle Wrapper locations.

Usage:
    apkdist-env-check --project /path/to/android/project
"""

import argparse
import glob
import os
import platform
import shutil
import subprocess
from typing import Dict, Optional


def find_java() -> Optional[str]:
    """Find Java installation and return its path."""
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        java_bin = os.path.join(java_home, "bin", "java")
        if os.path.isfile(java_bin):
            return java_home

    java_path = shutil.which("java")
    if java_path:
        real_path = os.path.realpath(java_path)
        return os.path.dirname(os.path.dirname(real_path))

    candidates = [
        *sorted(glob.glob("/usr/lib/jvm/java-*"), reverse=True),
        "/Library/Java/JavaVirtualMachines",
        *sorted(glob.glob(os.path.expanduser("~/android-studio/jbr")), reverse=True),
        "/usr/local/android-studio/jbr",
        *sorted(glob.glob("/opt/android-studio/jbr"), reverse=True),
        *sorted(glob.glob("/snap/android-studio/current/android-studio/jbr"), reverse=True),
    ]
    for path in candidates:
        java_bin = os.path.join(path, "bin", "java")
        if os.path.isfile(java_bin):
            return path

    return None


def find_android_studio() -> Optional[str]:
    """Find Android Studio installation directory."""
    candidates = [
        os.path.expanduser("~/android-studio"),
        "/opt/android-studio",
        "/usr/local/android-studio",
        "/snap/android-studio/current/android-studio",
        "/Applications/Android Studio.app/Contents",
        os.path.join(os.getenv("PROGRAMFILES", ""), "Android", "Android Studio"),
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Android", "Android Studio"),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def find_android_sdk() -> Optional[str]:
    """Find Android SDK directory."""
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        path = os.getenv(var)
        if path and os.path.isdir(path):
            return path

    candidates = [
        os.path.expanduser("~/Android/Sdk"),
        os.path.expanduser("~/Library/Android/sdk"),
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Android", "Sdk"),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def find_gradlew(project_path: Optional[str]) -> Optional[str]:
    """Find gradlew in the given project directory and return absolute path."""
    if not project_path:
        return None

    project_root = os.path.abspath(project_path)
    name = "gradlew.bat" if platform.system() == "Windows" else "gradlew"
    gradlew = os.path.join(project_root, name)
    if os.path.isfile(gradlew):
        return gradlew
    return None


def get_version(cmd) -> Optional[str]:
    """Run a command and return its first output line, or None on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def main(argv=None) -> Dict[str, str]:
    parser = argparse.ArgumentParser(description="Check Android build environment")
    parser.add_argument("--project", help="Path to Android project root (where gradlew lives)")
    args = parser.parse_args(argv)

    print("🔍 Scanning build environment...\n")

    all_ok = True
    result: Dict[str, str] = {}

    studio = find_android_studio()
    if studio:
        print(f"  ✅ Android Studio : {studio}")
        result["android_studio"] = studio
    else:
        print("  ⚠️  Android Studio : not found (optional, but recommended)")

    sdk = find_android_sdk()
    if sdk:
        print(f"  ✅ Android SDK     : {sdk}")
        result["android_sdk"] = sdk
    else:
        print("  ❌ Android SDK     : not found — set ANDROID_HOME")
        all_ok = False

    java_home = find_java()
    if java_home:
        version = get_version([os.path.join(java_home, "bin", "java"), "-version"]) or ""
        print(f"  ✅ Java            : {java_home}")
        if version:
            print(f"                       {version}")
        result["java_home"] = java_home
    else:
        print("  ❌ Java            : not found — install JDK or set JAVA_HOME")
        all_ok = False

    gradlew = find_gradlew(args.project)
    if gradlew:
        executable = os.access(gradlew, os.X_OK)
        status = "" if executable else " (not executable — run: chmod +x gradlew)"
        print(f"  ✅ gradlew         : {gradlew}{status}")
        result["gradlew"] = gradlew
    elif args.project:
        print(f"  ❌ gradlew         : not found in {os.path.abspath(args.project)}")
        all_ok = False
    else:
        print("  ⏭️  gradlew         : skipped (use --project to check)")

    print()
    if all_ok:
        print("✅ Environment looks good!")
    else:
        print("❌ Some required tools are missing. See above.")

    exports = []
    if sdk and not os.getenv("ANDROID_HOME"):
        exports.append(f"export ANDROID_HOME={sdk}")
    if java_home and not os.getenv("JAVA_HOME"):
        exports.append(f"export JAVA_HOME={java_home}")

    if exports:
        print("\n💡 Suggested exports for your shell:")
        for line in exports:
            print(f"   {line}")

    return result


if __name__ == "__main__":
    main()
