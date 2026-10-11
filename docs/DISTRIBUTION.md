# Distribution

## Release layout

Published downloads live in GitHub Releases, separately from the source tree:

- Versioned Windows x64 Setup EXE: private runtime, shortcuts, uninstall.
- Versioned Windows x64 portable ZIP: EXE plus `_internal`, README and licenses.
- Versioned source ZIP: explicit reviewed file manifest, no runtime or user data.
- `SHA256SUMS.txt`: SHA-256 hashes for the release downloads.

The installer wraps the same PyInstaller one-folder application as the portable ZIP. The primary launcher is `Akis-Rockbox-Scrobbler.exe`. End users do not install Python, Qt, PyInstaller or FFmpeg. Setup requires no network connection; Last.fm operations require internet. The app does not change system Python or PATH. FFmpeg is neither needed nor downloaded.

Setup uses `PrivilegesRequired=lowest`, installs under `%LOCALAPPDATA%\Programs\Akis-Rockbox-Scrobbler`, creates a Start menu shortcut and optionally a desktop shortcut. Windows Installed apps handles uninstall. Queue/credentials/theme data live separately in `%LOCALAPPDATA%\RockboxRelay` and are preserved on uninstall.

## Build

Use x64 Python 3.12+ with OpenSSL 3 on Windows. Install the pinned `requirements-build.txt` into a virtual environment. Run `build.py`, `tools/package_release.py`, then `tools/build_installer.py` with Inno Setup 6 installed. `build.py` places the EXE and `_internal` directly in the project folder for local launching, and stages release packages in `dist/`. Build on the target operating system as required by PyInstaller.

Python is collected from the builder's installation. Qt/PySide6 Essentials 6.10.2 is installed from the pinned dependency and bundled as shared libraries. The release includes Python, Qt LGPL/GPL texts, QtBase third-party attributions, and PyInstaller's bootloader exception. Original application and restored shaders remain MIT. No FFmpeg binaries are included. [Third-party notices](../THIRD-PARTY-NOTICES.txt).

The GitHub release workflow checks Python 3.10/3.12 on Windows/Linux, builds on Windows with Python 3.12 and PyInstaller 6.22.3, compiles Setup with Inno Setup 6.7.3, runs offline GUI/import/theme/shader smoke checks on both portable and installed apps with system Python removed from PATH, checks shortcuts/uninstall and user-data preservation, then publishes assets on a matching version tag. Headless CI accepts the documented still graphics fallback; `--require-gl` is used locally to verify every live shader effect on actual OpenGL. Manual workflow runs produce artifacts without publishing a Release.

Qt/PySide6 shared libraries can be replaced by compatible modified builds in `_internal`; the executable does not verify their signatures. See the notices for exact-version upstream source and build instructions. The onedir packaging keeps those libraries separate rather than statically linking Qt.

## Repository hygiene

Commit source, assets, tests, docs, dependency pins and installer/build configuration. Ignore virtual environments, Python runtimes, EXEs, downloaded dependencies, build/dist outputs and all user queues/credentials/logs. Source archives use an explicit allowlist rather than packaging the working directory.

Releases are currently unsigned. Distribute the complete portable folder, not its EXE alone. Checksums help verify downloads, but are not code signing.
