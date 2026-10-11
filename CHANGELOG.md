# Changelog

## 1.1.0 | 2026-10-10

- Converted to a standalone native desktop window; removed HTML/JavaScript and the local HTTP server.
- Added persistent dark mode across the queue, settings and reading panels.
- Added Windows Setup and portable releases containing a private Python/Tcl/Tk runtime, with no FFmpeg dependency.
- Added tagged release automation, checksums, installer/uninstaller smoke checks and native UI integration tests.
- Preserved existing queue storage, credentials, receipts, date adjustment and explicit submission confirmation.
- Replaced the WebGL decoration with a static native Aero-inspired design and updated documentation/screenshots.


## 1.0.0

- Import and review Rockbox scrobbler logs, including entries treated as at least 50% listened.
- Connect Last.fm through desktop authorization and submit reviewed batches of up to 50.
- Preserve local queue, account-specific receipts, original dates, and duplicate protection.
- Enforce a 14-day submission window, with optional date adjustment for older unsent plays.
- Match Last.fm receipts by timestamp and hold unverifiable outcomes for manual review.
- Add the Achilleus-branded Frutiger Aero interface and supplied Achilleus logos.
- Refine the interface with liquid glass panels, pill controls, soft reflections, and reduced-transparency fallbacks.
- Add a local WebGL liquid glass shader with background refraction, pointer lighting, click ripples, an appearance switch, and graphics/motion fallbacks.
- Publish setup, troubleshooting and architecture guides, community contribution templates, and a source release.
