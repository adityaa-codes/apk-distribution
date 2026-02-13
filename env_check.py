#!/usr/bin/env python3
"""
Helper script to detect Android Studio, Java, and Gradle Wrapper locations.
Run this to verify your environment before using the distribution pipeline.

Usage:
    python env_check.py [--project /path/to/android/project]
"""

import os
import sys
import glob
import shutil
import platform
import subprocess
import argparse


def find_java():
    """Finds Java installation and returns its path."""
    # 1. Check JAVA_HOME
    java_home = os.getenv('JAVA_HOME')
    if java_home:
        java_bin = os.path.join(java_home, 'bin', 'java')
        if os.path.isfile(java_bin):
            return java_home

    # 2. Check if java is on PATH
    java_path = shutil.which('java')
    if java_path:
        # Resolve symlinks to find the real install dir
        real_path = os.path.realpath(java_path)
        # java binary is typically at <java_home>/bin/java
        return os.path.dirname(os.path.dirname(real_path))

    # 3. Check common locations
    candidates = [
        # Linux
        *sorted(glob.glob('/usr/lib/jvm/java-*'), reverse=True),
        # macOS
        '/Library/Java/JavaVirtualMachines',
        # Android Studio bundled JDK (check multiple install locations)
        *sorted(glob.glob(os.path.expanduser('~/android-studio/jbr')), reverse=True),
        '/usr/local/android-studio/jbr',
        *sorted(glob.glob('/opt/android-studio/jbr'), reverse=True),
        *sorted(glob.glob('/snap/android-studio/current/android-studio/jbr'), reverse=True),
    ]
    for path in candidates:
        java_bin = os.path.join(path, 'bin', 'java')
        if os.path.isfile(java_bin):
            return path

    return None


def find_android_studio():
    """Finds Android Studio installation directory."""
    candidates = [
        # Linux
        os.path.expanduser('~/android-studio'),
        '/opt/android-studio',
        '/usr/local/android-studio',
        '/snap/android-studio/current/android-studio',
        # macOS
        '/Applications/Android Studio.app/Contents',
        # Windows
        os.path.join(os.getenv('PROGRAMFILES', ''), 'Android', 'Android Studio'),
        os.path.join(os.getenv('LOCALAPPDATA', ''), 'Android', 'Android Studio'),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def find_android_sdk():
    """Finds Android SDK directory."""
    for var in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        path = os.getenv(var)
        if path and os.path.isdir(path):
            return path
    candidates = [
        os.path.expanduser('~/Android/Sdk'),
        os.path.expanduser('~/Library/Android/sdk'),
        os.path.join(os.getenv('LOCALAPPDATA', ''), 'Android', 'Sdk'),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def find_gradlew(project_path):
    """Finds gradlew in the given project directory and returns its absolute path."""
    if not project_path:
        return None
    project_root = os.path.abspath(project_path)
    name = 'gradlew.bat' if platform.system() == 'Windows' else 'gradlew'
    gradlew = os.path.join(project_root, name)
    if os.path.isfile(gradlew):
        return gradlew
    return None


def get_version(cmd):
    """Runs a command and returns its first line of output, or None on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description='Check Android build environment')
    parser.add_argument('--project', help='Path to Android project root (where gradlew lives)')
    args = parser.parse_args()

    print("🔍 Scanning build environment...\n")

    all_ok = True
    result = {}

    # --- Android Studio ---
    studio = find_android_studio()
    if studio:
        print(f"  ✅ Android Studio : {studio}")
        result['android_studio'] = studio
    else:
        print("  ⚠️  Android Studio : not found (optional, but recommended)")

    # --- Android SDK ---
    sdk = find_android_sdk()
    if sdk:
        print(f"  ✅ Android SDK     : {sdk}")
        result['android_sdk'] = sdk
    else:
        print("  ❌ Android SDK     : not found — set ANDROID_HOME")
        all_ok = False

    # --- Java ---
    java_home = find_java()
    if java_home:
        version = get_version([os.path.join(java_home, 'bin', 'java'), '-version']) or ''
        print(f"  ✅ Java            : {java_home}")
        if version:
            print(f"                       {version}")
        result['java_home'] = java_home
    else:
        print("  ❌ Java            : not found — install JDK or set JAVA_HOME")
        all_ok = False

    # --- Gradle Wrapper ---
    gradlew = find_gradlew(args.project)
    if gradlew:
        executable = os.access(gradlew, os.X_OK)
        status = "" if executable else " (not executable — run: chmod +x gradlew)"
        print(f"  ✅ gradlew         : {gradlew}{status}")
        result['gradlew'] = gradlew
    elif args.project:
        print(f"  ❌ gradlew         : not found in {os.path.abspath(args.project)}")
        all_ok = False
    else:
        print("  ⏭️  gradlew         : skipped (use --project to check)")

    # --- Summary ---
    print()
    if all_ok:
        print("✅ Environment looks good!")
    else:
        print("❌ Some required tools are missing. See above.")

    # Print export hints for missing env vars
    exports = []
    if sdk and not os.getenv('ANDROID_HOME'):
        exports.append(f"export ANDROID_HOME={sdk}")
    if java_home and not os.getenv('JAVA_HOME'):
        exports.append(f"export JAVA_HOME={java_home}")
    if exports:
        print("\n💡 Suggested exports for your shell:")
        for e in exports:
            print(f"   {e}")

    return result


if __name__ == '__main__':
    main()
