# Aki's Rockbox Scrobbler

**[Product of Achilleus](https://linktr.ee/achilleus_)** — Created and maintained by [Achilleus (Achilleus-1)](https://github.com/Achilleus-1).

A lightweight local Windows app that brings your Rockbox listening history to Last.fm, with a Frutiger Aero-inspired music desk and interactive liquid glass. Import your `.scrobbler.log`, review the queue, connect Last.fm, and send the plays you choose. No third-party Python packages, installer, analytics, or hosted backend.

![Aki's Rockbox Scrobbler — liquid glass music desk](docs/images/preview.png)

The local WebGL shader refracts a flowing Aero background through rounded glass lenses. Move your pointer for shifting reflections and click for ripples. Text and controls remain native, with more opaque queue and reading surfaces. Settings → Appearance → **Interactive liquid glass** turns the effect off. Only this appearance preference is saved in browser local storage; pointer positions are never saved or sent. Rendering is capped at 30 FPS and 1.4 million pixels, pauses while the page is hidden, and uses still frames with reduced motion. Unsupported graphics use the static glass theme automatically.

## Installation

Download the source ZIP, extract it to a folder, and follow the steps below. Python 3.10 or newer and a modern browser are required. This is a local Python application; the ZIP is not a standalone executable.

## Start

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/) if needed. On Windows, enable “Add Python to PATH”.
2. Double-click **Start Akis Rockbox Scrobbler.cmd**. The interface opens in your default browser. Keep the terminal open; close it or press Ctrl+C to stop the app. Running the launcher again opens the existing instance.
3. Open **Settings**. [Create a Last.fm API account](https://www.last.fm/api/account/create), name it “Aki's Rockbox Scrobbler”, and leave optional callback/website fields blank. Paste the API key and shared secret. This step requires your Last.fm account; the app does not come with registered developer credentials.
4. Click **Connect Last.fm**, open the authorization link, and approve access on Last.fm. Return to the app and click **I've authorized access**. Never put your Last.fm password in the app.
5. Connect your player over USB and import `.scrobbler.log` from the root of its drive (or a copy on your PC). Review the dates, select plays, and click **Scrobble selected**. Confirm the destination account before sending.

On current Rockbox builds, enable playback logging, then run **Plugins → Applications → lastfm_scrobbler** to export `.scrobbler.log` first. The export only records an L/S flag, not elapsed play time. This app treats all entries as at least 50% listened, including entries marked S. Raw `playback.log` is not accepted: it contains paths and requires the player to export song metadata. Export before disconnecting the device.

## Behavior

- Supports UTF-8/BOM, LF/CRLF, comments, 7-field logs and 8-field logs with optional MusicBrainz IDs. Up to 8 MB per file and 20,000 eligible plays per import.
- Preview shows the actual account, artist, title, album and local listening time. Selection starts empty. Sample mode is an unsaved preview with submission disabled.
- All parseable entries are treated as at least 50% listened, including skipped entries and short songs. The original Rockbox flag is retained as metadata; the app does not measure elapsed listening time. Last.fm's API records a play, not a listening percentage.
- A two-week submission cutoff applies by default. Older plays are kept locally with a **Too old** status, and cannot be selected for submission.
- In **Settings**, optionally enable **Adjust outdated listening dates**, then click **Save history settings**. Older unsent plays are spread in chronological order across at most the last 13 days, ending one minute before adjustment. This applies to existing queued plays and subsequent imports. Adjusted dates are planned and saved, not silently moved on each page refresh. If a planned date ages out, save the setting again to refresh the plan.
- Original listening dates remain saved locally, while the queue displays the submission date and the original date beneath adjusted entries. The confirmation states how many selected dates were adjusted. Last.fm will count accepted plays on those newer dates; their original historical dates cannot be restored on Last.fm through this import.
- Source fingerprints, rather than adjusted dates, identify plays for duplicate protection. Reimporting an old log does not create fresh copies. Accepted and uncertain plays are never automatically retried or retimed. Plays specifically rejected for being too old can be retried after adjusting dates; other Last.fm rejections stay visible.
- Entries with missing artist/title metadata, non-positive durations, missing timestamps, future times, malformed fields, or exact duplicates still receive an exclusion reason.
- Apart from the optional date adjustment above, original timestamps are preserved. An explicit optional clock correction in 15-minute increments handles incorrectly configured player clocks. Treat exported Unix timestamps as UTC. If a UTC−5 local player clock was encoded as UTC, subtract 5 hours. Use the offset in effect when you listened, including daylight saving changes. Entries without valid timestamps are still excluded.
- Submits oldest first, at most 50 per request, with a one-second pause between batches. Every row's Last.fm ignored code is inspected. “Accepted” means Last.fm reported code 0; profile updates may lag.
- Response receipts are matched by their listening timestamps, so reordered batch results are handled correctly. Plays with a shared timestamp and different outcomes require a unique metadata match. Missing, conflicting, or ambiguous receipts hold the whole batch as **Uncertain** with a specific explanation; check your profile before choosing a retry.
- Local receipts deduplicate artist + title + timestamp per Last.fm account. Repeated songs at different times are preserved. This does not check listens uploaded by other apps; avoid importing logs already submitted elsewhere.
- Queue and receipts survive restarts. Confirmed accepted and ignored plays are held back. A request with an unknown outcome is held as **Uncertain**. Check your Last.fm library, then use **Check outcome** to mark it received or enable a manual retry. No automatic resend of ambiguous requests.
- A reported API rejection leaves the batch pending; fix the error before selecting and submitting again. Invalid sessions require reconnecting. Ignored plays retain Last.fm's reason; they are not automatically retried.
- Source logs and music files are never modified or deleted. Clearing the queue retains deduplication fingerprints. Reimporting a file shows previously accepted outcomes for the same account.

## Privacy and security

The Python server binds only to `127.0.0.1` on an available port. The launcher uses a random local session URL and an HttpOnly SameSite cookie. API actions require a per-run CSRF token, exact Origin and Host checks, and JSON requests. All assets are local; CSP blocks external resources and framing. The server serves explicitly allowed UI files and logos, and never accepts arbitrary filesystem paths. Uploaded metadata is rendered as text, not HTML.

API requests use `https://ws.audioscrobbler.com/2.0/`, with normal TLS certificate verification, redirects disabled and a 30-second timeout. Credentials are never returned by the state API or logged. MD5 signatures are required by Last.fm; local credential encryption uses Windows DPAPI, not MD5.

By default credentials stay in process memory. **Remember on this PC** encrypts the API key, shared secret and Last.fm session with Windows DPAPI for your Windows user. There is no plaintext fallback. DPAPI does not protect against malware running as your Windows user. Disconnect deletes local saved credentials; [revoke access on Last.fm](https://www.last.fm/settings/applications) to invalidate the remote session too.

Data lives in `%LOCALAPPDATA%\RockboxRelay`: `relay.sqlite3` (unencrypted track metadata and account-specific receipt fingerprints), `credentials.dpapi` if enabled, and local instance/session files. The existing `RockboxRelay` directory name is retained so previous installations keep their queue, settings, and receipts after the rename. To delete all data, stop the app and delete that folder. This also removes duplicate protection. Local queue metadata is not sent to any server during import.

The readable source can be reviewed; this is not a claim of an independent security audit. Python and your browser are the only runtime requirements. Non-Windows use is possible with memory-only credentials.

## Development and verification

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
node --check web/liquid-glass.js
node --test tests/test_liquid_glass.cjs
python scrobbler.py --no-browser --data-dir .test-data
```

`--no-browser` prints the authenticated local launch URL for testing. `--port` optionally fixes the local port. Tests use a temporary data directory and fake Last.fm responses. They do not submit real plays. Live Last.fm authorization/submission requires your own credentials and an account, and has not been performed as part of automated verification.

To build the distributable source ZIP, run `python tools/package_release.py`. The archive is created in `dist/` from an explicit file list; local queues, credentials, logs, and test tools are excluded. GitHub Actions runs the tests and JavaScript syntax checks on Windows and Linux. See [CONTRIBUTING.md](CONTRIBUTING.md) for changes and [SECURITY.md](SECURITY.md) for reports.

## License and branding

Source code is licensed under [MIT](LICENSE). Achilleus branding and the supplied logo are included as project identity; the code license does not grant trademark rights. This project is independent of Rockbox and Last.fm.

## Protocol references

- [Last.fm desktop authentication](https://www.last.fm/api/desktopauth)
- [Last.fm scrobbling rules, batching, and ignored codes](https://www.last.fm/api/scrobbling)
- [track.scrobble parameters](https://www.last.fm/api/show/track.scrobble)
- [Rockbox's official log exporter source](https://github.com/Rockbox/rockbox/blob/master/apps/plugins/lastfm_scrobbler.c)
