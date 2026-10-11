# Distribution

## Release layout

Published downloads live in GitHub Releases, separately from the source tree:

- Versioned Windows x64 Setup EXE: private runtime, shortcuts, uninstall.
- Versioned Windows x64 portable ZIP: EXE plus `_internal`, README and licenses.
- Versioned source ZIP: explicit reviewed file manifest, no runtime or user data.
- `SHA256SUMS.txt`: SHA-256 hashes for the release downloads.

The installer wraps the same PyInstaller one-folder application as the portable ZIP. End users do not install Python, Tk, PyInstaller or FFmpeg. Setup requires no network connection; Last.fm operations require internet. The app does not change system Python or PATH. FFmpeg is neither needed nor downloaded.

Setup uses `PrivilegesRequired=lowest`, installs under `%LOCALAPPDATA%\Programs\Akis-Rockbox-Scrobbler`, creates a Start menu shortcut and optionally a desktop shortcut. Windows Installed apps handles uninstall. Queue/credentials/theme data live separately in `%LOCALAPPDATA%\RockboxRelay` and are preserved on uninstall.

## Build

Use x64 Python 3.12+ with OpenSSL 3 on Windows. Install the pinned `requirements-build.txt` into a virtual environment. Run `build.py`, `tools/package_release.py`, then `tools/build_installer.py` with Inno Setup 6 installed. Output is in `dist/`. Build on the target operating system as required by PyInstaller.

Python/Tcl/Tk are collected from the builder's Python installation. The release includes that runtime's Python license, Tcl/Tk's permissive license and PyInstaller's bootloader exception. Original source remains MIT. No Qt or FFmpeg binaries are included. [Third-party notices](../THIRD-PARTY-NOTICES.txt).

The GitHub release workflow checks Python 3.10/3.12 on Windows/Linux, builds on Windows with Python 3.12 and PyInstaller 6.22.3, compiles Setup with Inno Setup 6.7.3, runs offline GUI/import/theme smoke checks on both portable and installed apps with system Python removed from PATH, checks shortcuts/uninstall and user-data preservation, then publishes assets on a matching `v1.1.1` tag. Manual workflow runs produce artifacts without publishing a Release.

## Repository hygiene

Commit source, assets, tests, docs, dependency pins and installer/build configuration. Ignore virtual environments, Python runtimes, EXEs, downloaded dependencies, build/dist outputs and all user queues/credentials/logs. Source archives use an explicit allowlist rather than packaging the working directory.

Releases are currently unsigned. Distribute the complete portable folder, not its EXE alone. Checksums help verify downloads, but are not code signing.
