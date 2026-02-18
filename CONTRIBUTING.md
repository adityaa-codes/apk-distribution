# Contributing

Thanks for your interest in contributing to APK Distribution Pipeline!

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/<your-username>/apk-distribution.git
   cd apk-distribution
   ```
3. Install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```
4. Copy `.env.example` to `.env` and fill in your values (see [README](README.md) for details)

## Making Changes

1. Create a branch for your change:
   ```bash
   git checkout -b my-feature
   ```
2. Make your changes — keep them focused and minimal
3. Test with `--dry-run` to make sure nothing breaks:
   ```bash
   apkdist patch --dry-run
   ```
4. Commit with a clear message:
   ```bash
   git commit -m "Add support for X"
   ```

## Pull Requests

- One feature or fix per PR
- Describe what changed and why
- Make sure core modules pass a syntax check:
  ```bash
  python -m py_compile apkdist/pipeline.py apkdist/env_check.py apkdist/cleanup.py
  ```

## Reporting Issues

Open an issue with:
- What you expected to happen
- What actually happened
- Your Python version (`python --version`)
- Any relevant error output

## Code Style

- Keep it simple — no over-engineering
- Use `print()` with emoji prefixes for user-facing output (✅ ❌ ⚠️ 🔄 etc.)
- Handle edge cases — don't let errors pass silently

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE.md).
