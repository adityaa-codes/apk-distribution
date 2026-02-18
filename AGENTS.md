# Repository Guidelines

## Project Structure & Module Organization
- `main.py`: Primary pipeline (`bump -> build -> upload -> notify`).
- `env_check.py`: Local environment validation (Android Studio/SDK, Java, `gradlew`).
- `cleanup.py`: Google Drive APK retention cleanup.
- `requirements.txt`: Python dependencies.
- `.env.example`: Configuration template; copy to `.env` for local runs.
- `README.md`, `CONTRIBUTING.md`, `RELEASE_NOTES.md`: Setup, contribution flow, and release history.

This repository is currently script-first (no `src/` or `tests/` directory). Keep new modules focused and place shared helpers in small, reusable functions.

## Build, Test, and Development Commands
- `pip install -e .`: Install package in editable mode for development.
- `apkdist-env-check --project /path/to/android/project`: Validate local Android toolchain.
- `apkdist patch --dry-run`: Validate pipeline behavior without side effects.
- `apkdist patch --variant staging --force`: Force a fresh build/upload for a specific variant.
- `apkdist-cleanup --days 14`: Preview old APKs eligible for deletion.
- `apkdist-cleanup --days 14 --delete`: Delete old APKs after confirmation.
- `python -m py_compile apkdist/pipeline.py apkdist/env_check.py apkdist/cleanup.py`: Quick syntax validation before PR.

## Coding Style & Naming Conventions
- Follow Python 3.8+ conventions with 4-space indentation and PEP 8 style.
- Use `snake_case` for functions/variables and `UPPER_CASE` for constants/env keys.
- Keep CLI output explicit and consistent with existing emoji-prefixed status lines.
- Prefer clear guard clauses and actionable error messages over silent failures.

## Testing Guidelines
- No formal automated test suite is committed yet.
- Minimum verification for changes:
  - Run `apkdist patch --dry-run`.
  - Run `python -m py_compile apkdist/pipeline.py apkdist/env_check.py apkdist/cleanup.py`.
  - Exercise affected flags/paths locally and record expected output in PR notes.
- If adding tests, use `pytest` with files named `tests/test_<feature>.py`.

## Commit & Pull Request Guidelines
- Keep each commit and PR focused on one feature/fix.
- Use imperative, specific commit subjects (example: `main: handle missing version.properties`).
- PRs should include: what changed, why, config/env impact, validation commands run, and linked issue(s).
- Include screenshots or sample message payloads only when notification formatting changes.

## Security & Configuration Tips
- Never commit secrets or tokens (`.env`, `token.json`, service-account keys).
- Keep placeholders in `.env.example`; store real credentials locally.
- Validate Drive folder/chat targets in non-production contexts before running destructive cleanup.
