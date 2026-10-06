# Troubleshooting

[Back to the project](../README.md) · [User guide](USER_GUIDE.md)

## The launcher does not open the app

Install Python 3.10 or newer, then check `python --version` or `py -3 --version` in a terminal. On Windows, enable Python's PATH option during installation. Extract the release ZIP before starting it; the launcher needs `scrobbler.py` and the `web` directory beside it.

Keep the launcher terminal open. Closing it stops the local server. Launch again to reopen an existing instance. If the browser reports a local session error, use the launcher instead of copying an old `127.0.0.1` URL from another run.

## Last.fm will not connect

Use the API key and **shared secret** from the same Last.fm API application. Your Last.fm password is not an API secret. Create the application through the Settings link, leaving optional callback and website fields blank.

Authorize in Last.fm's own tab, then return and click **I've authorized access**. If authorization has expired, start connecting again. Check your internet connection and PC clock when HTTPS requests fail. Do not disable certificate verification.

If Last.fm returns an unexpected authentication response, include the app's displayed error in a bug report, with credentials removed. Tokens are opaque strings; a token need not look like an API key.

## Many entries are excluded or held back

| Message or status | What to do |
| --- | --- |
| Too old | Entries remain in your queue. To use newer submission dates, enable **Adjust outdated listening dates** and save. Last.fm will show the newer dates. |
| Missing artist or title | Fix the music file's tags and export a new log on the player. |
| Invalid timestamp or duration | Check the player's clock and export. Entries without usable times cannot be imported. |
| Future listening time | Check the player clock and UTC offset. Use import clock correction only when the offset is known. |
| Duplicate | An identical artist, title, and original timestamp is already queued, or a receipt exists for this account. Repeated songs at different times are preserved. |
| Malformed fields or wrong format | Export `.scrobbler.log`; do not import raw `playback.log`. |

Skipped Rockbox entries are included when their metadata, duration and timestamp are valid. The 50% assumption is not measured listening time.

## Dates are wrong

Unix timestamps are interpreted as UTC and shown in your PC's local time zone. If the player wrote a local time as UTC, apply the known clock correction during import. Use the time-zone offset that applied when you listened, including daylight saving changes. Preview before sending.

Adjusted older entries show both their planned submission date and original listening date. If a planned date has itself expired, save the history setting again to refresh eligible unsent dates.

## A play is Uncertain or Last.fm returned an unexpected result

The request may have reached Last.fm even if the reply could not be verified. **Check your Last.fm library before retrying.** Use **Check outcome** on that play to mark it received, or allow a retry if it is missing. A retry can create a duplicate if Last.fm already received it.

The app validates the complete response before recording acceptance and holds ambiguous results back. An interrupted submission also becomes Uncertain after restart. Do not clear receipt data to force a resend.

## Last.fm ignored a play

Read its returned reason in the queue. An API request can succeed while individual entries are ignored. Date adjustment can make entries rejected specifically for an old timestamp eligible for another attempt; it does not override other Last.fm rules.

## Liquid glass is slow or unavailable

Turn off **Settings → Appearance → Interactive liquid glass**. The static theme keeps all application features. If WebGL is unavailable or its context is lost, the static theme activates automatically. Reduced motion disables continuous animation and click waves.

The shader bends its locally rendered Aero environment, rather than capturing your desktop or text. Queue text and controls stay native. Graphics and driver compatibility vary; include browser and graphics information with visual bug reports.

## Remembered credentials cannot be unlocked

Windows DPAPI ties credentials to your Windows user. Reconnect if the saved credentials were moved from another PC or user. Outside Windows, leave **Remember on this PC** unchecked. There is no plaintext credential fallback.

## Back up or move the queue

Stop the app, then copy its entire data directory. On Windows this is `%LOCALAPPDATA%\RockboxRelay`; other platforms normally use `~/.local/share/RockboxRelay`. Keep the database and any SQLite sidecar files together. Do not publish this folder: it contains listening history and may contain encrypted credentials.

Use `--data-dir PATH` to run against a different folder. DPAPI credentials may need reconnecting when moved. **Clear queue** removes imported metadata but keeps submission fingerprints for duplicate protection. Removing the entire data folder also removes that protection.

## Report a problem

[Open a bug report](https://github.com/Achilleus-1/Akis-Rockbox-Scrobbler/issues/new?template=bug_report.yml) with your app version, OS, Python and browser versions, steps, and the exact message. Prefer a small synthetic log. Remove API keys, secrets, session tokens, authenticated launch URLs and private history from screenshots. Report sensitive vulnerabilities using [SECURITY.md](../SECURITY.md).
