# Contributing

Aki's Rockbox Scrobbler is a Product of Achilleus. Keep changes small, readable, and dependency-free where practical.

Run these checks before opening a pull request:

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
python tools/package_release.py
```

Use `python scrobbler.py --no-browser --data-dir .test-data` for an isolated local queue. Use fake credentials and synthetic listening logs in tests. Never include API keys, shared secrets, session or launch tokens, databases, or personal listening logs in a commit or issue.

For UI changes, check the queue, search and selection, settings, dialogs, guide, and narrow-screen layout. Keep keyboard focus visible, render imported metadata as text, and use local assets.

Preserve the original play fingerprints and uncertain-submission guard. Changes must not silently resend a play, change a submitted date, modify source logs, or weaken the localhost session checks. New Last.fm response formats need regression coverage with anonymized fixtures.
