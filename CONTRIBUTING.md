# Contributing

Keep changes readable. The desktop interface uses pinned Qt/PySide6 Essentials and the backend uses Python's standard library. Install `requirements.txt` before working on source.

```powershell
python -m unittest discover -s tests -v
python app.py --smoke-test .test-data/native-smoke.json --require-gl
python tools/package_release.py
```

Widget tests use Qt's offscreen platform on headless systems. Actual shader verification needs a working OpenGL display and `--require-gl`. Test account/submission behavior with fake Last.fm replies and temporary storage. Never submit real plays in automated tests or commit private logs/credentials/databases.

Linux source needs the distribution's EGL/OpenGL and xkbcommon libraries (Ubuntu: `libegl1 libgl1 libopengl0 libxkbcommon0`). Packaged Windows builds bundle their runtime.

Check both light/dark modes, live/still glass, scroll clipping, keyboard selection, long metadata, adjusted dates and window resizing. Keep network work off the Qt thread and preserve account/date confirmation and uncertain-result safeguards. See [architecture](docs/ARCHITECTURE.md) and [distribution](docs/DISTRIBUTION.md).

For Windows builds, install `requirements-build.txt` in a virtual environment and run `build.py`. Installer compilation also requires Inno Setup 6. Release binaries belong in GitHub Releases, not Git.
