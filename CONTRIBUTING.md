# Contributing

Keep changes readable and avoid unnecessary runtime dependencies. The desktop interface uses Tk/ttk and the backend uses Python's standard library.

```powershell
python -m unittest discover -s tests -v
python app.py --smoke-test .test-data/native-smoke.json
python tools/package_release.py
```

On Linux, use `xvfb-run -a` for GUI tests on a headless machine. Test account/submission behavior with fake Last.fm replies and temporary storage. Never submit real plays in automated tests or commit private logs/credentials/databases.

Check both light/dark modes, keyboard selection, long metadata, adjusted dates and window resizing. Keep network work off the Tk thread and preserve account/date confirmation and uncertain-result safeguards. See [architecture](docs/ARCHITECTURE.md) and [distribution](docs/DISTRIBUTION.md).

For Windows builds, install `requirements-build.txt` in a virtual environment and run `build.py`. Installer compilation also requires Inno Setup 6. Release binaries belong in GitHub Releases, not Git.
