# User guide

[Back to the project](../README.md)

## Installation

Download the Windows Setup EXE from [Releases](https://github.com/Achilleus-1/Akis-Rockbox-Scrobbler/releases/latest), run it, and launch the app from its Start menu shortcut. Setup needs no administrator account or downloads during installation. Uninstall through Windows Installed apps.

For the portable edition, extract the whole ZIP and double-click `Akis-Rockbox-Scrobbler.exe`. Keep `_internal` and the supporting files together. Both editions include Python and Tcl/Tk. No system Python, FFmpeg, terminal, or browser interface is required.

## Connect and import

1. Open **Settings**. [Create a Last.fm API account](https://www.last.fm/api/account/create), name it Aki's Rockbox Scrobbler, and leave optional callback/website fields blank. Save the API key and shared secret. These are app credentials, not your Last.fm password.
2. Click **Connect Last.fm**, approve access in the browser, return to the desktop app, and click **Finish connecting**.
3. In Rockbox, enable playback logging and run **Plugins > Applications > lastfm_scrobbler** to export `.scrobbler.log`. Raw `playback.log` contains paths rather than the required song metadata.
4. Import `.scrobbler.log` from your connected player or a copy on your PC. Leave time correction at zero unless the player clock needs adjustment. Review the import report for excluded lines and reasons.
5. Search/filter the queue and select plays by clicking their checkboxes or pressing Space on a highlighted row. **Select ready** selects eligible visible plays; **Deselect all** clears all selections, including hidden ones.
6. Click **Scrobble selected**. Confirm the account, count and date range before anything is sent.

Click **Dark mode** in the sidebar or Settings to change themes. The setting survives restarting the app. Close the window to quit; wait for any active operation to finish first.

## Behavior

- UTF-8/BOM, LF/CRLF, comments, 7-field logs and 8-field logs with optional MusicBrainz IDs are supported. Limits: 8 MB per file, 100,000 lines and 20,000 plays in the queue.
- Importing starts with no new selections and never submits automatically. Source files are never changed.
- All otherwise valid entries are treated as at least 50% listened, including skipped entries and short songs. The original flag is retained; the app cannot measure actual elapsed listening time.
- A 14-day submission cutoff applies by default. Older entries remain **Too old**.
- **Adjust outdated listening dates** spreads eligible older unsent entries through the last 13 days, in original order. Last.fm displays the new dates. Original timestamps remain stored and are shown below the queue. Adjusted table dates have an asterisk. Saving again refreshes stale adjusted dates.
- Accepted or uncertain outcomes never receive new automatic dates. Old-timestamp rejections may become eligible after enabling adjustment; other rejections remain held.
- Last.fm may independently ignore plays. Its replies determine acceptance.
- Duplicate protection uses artist, title and original timestamp, scoped to the destination account. Album changes do not create another play. It does not compare with plays submitted by other apps.
- Clear queue removes imported metadata and date plans but retains submission receipts.

## Clock correction

Correction is explicit, between -24 and +24 hours in 15-minute steps. For a player that logged UTC-5 local time as UTC, subtract 5 hours. Use the offset at the time you listened, including daylight saving time. Missing or invalid timestamps are excluded; the app does not invent dates for players without a working clock.

## Interrupted submissions

An interrupted reply may leave a play already on Last.fm. Such entries are marked **Check outcome** and held back. Highlight the play, click **Check outcome**, open your listening history, and check it. Confirm that you checked before choosing **Already received** or **Missing - allow retry**. A retry can duplicate a play already received by Last.fm.

Submission is oldest first in batches of at most 50. The interface remains available while network work runs. Queue/account changes and closing the app are held until the active operation finishes.

## Privacy and storage

The app starts no server and sends no telemetry. Network requests go directly to Last.fm over verified HTTPS. Your browser opens for authorization and external links. Confirmed submissions send song metadata, listening timestamps, duration and optional track number/MusicBrainz ID.

Credentials stay in memory unless **Remember on this PC** is selected. Windows DPAPI encrypts the API key, shared secret and session key for your Windows user. Software running as that user may still access them. On other platforms, leave remembering off.

The unencrypted SQLite queue, receipts and preferences live in `%LOCALAPPDATA%\RockboxRelay` on Windows (`~/.local/share/RockboxRelay` elsewhere). Existing version 1.0 storage is reused. Uninstall preserves it. To erase all data, close the app and remove that folder; duplicate protection will be lost. Tests and smoke checks use temporary data and fake responses.

Disconnect removes saved credentials and the active session. To revoke access on Last.fm too, remove the app from [Last.fm application settings](https://www.last.fm/settings/applications).
