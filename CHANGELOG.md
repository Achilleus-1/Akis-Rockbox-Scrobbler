# Changelog

## 1.2.0 | 2026-10-10

- Restored the Frutiger Aero layout, pastel flowing scenery, glossy player artwork and rounded glass surfaces in native Qt.
- Ported the original liquid glass shader to native OpenGL with refraction, pointer reflections, click ripples and matching dark mode.
- Added remembered live/still glass, reduced-motion support, inactive-window pause and a still graphics fallback.
- Made the EXE the primary launch path: source builds put it directly in the project folder; removed the script launcher.
- Bundled replaceable Qt/Python libraries with complete Qt license texts and upstream source references.
- Restored file dropping and an unsaved, unsubmitable sample preview; preserved all backend protections and user data.

## 1.1.1 — 2026-10-10

- Added notices for the libraries bundled by Python, plus runtime version metadata.
- Added checks for required license files in the compiled-app smoke test.
- Required Python 3.12+ with OpenSSL 3 for release builds; source still supports Python 3.10+.

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
