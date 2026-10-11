# Troubleshooting

[Back to the project](../README.md)

| Symptom | What to check |
| --- | --- |
| Portable EXE cannot start | Extract the whole ZIP. Keep `_internal` and all supporting files next to the EXE. Use the x64 Windows 10/11 build. |
| App is already running | Switch to the existing desktop window. The queue allows one instance per data directory. |
| `tkinter` is missing when running source | Use a Python installation with Tk. Linux may need `python3-tk`. Windows release users do not need Python installed. |
| Last.fm is disconnected | Save your own 32-character API key/shared secret, then Connect Last.fm, authorize, and Finish connecting. |
| Finish connecting fails | Approve the Last.fm authorization first. If it expired, disconnect in Settings and reconnect. |
| No plays imported | Export `.scrobbler.log` using Rockbox's `lastfm_scrobbler` plugin. Raw `playback.log` is a different format. Read the import report's line-specific errors. |
| Plays are Too old | Last.fm's 14-day cutoff is enabled by default. Date adjustment is optional; Last.fm will show the adjusted dates. |
| Scrobble selected is disabled | Connect an account and select eligible plays. Accepted, ignored, expired and uncertain plays cannot be submitted directly. |
| Listening dates look wrong | Review the original date below the table. Only apply explicit player clock correction if needed. An asterisk marks an adjusted date. |
| Check outcome | Check the destination account's Last.fm history. Mark received or explicitly allow retry; never retry blindly. |
| Saved credentials cannot unlock | Reconnect in Settings under the original Windows user. DPAPI files are not portable between users. |
| Network failure | Check connectivity and system time. The app keeps certificate verification enabled. Unknown submission outcomes remain held. |
| Queue disappeared after an update | Both releases use `%LOCALAPPDATA%\RockboxRelay`. Check that you used the same Windows account and did not change `--data-dir`. |

Reports should include version, Windows version, install/portable/source edition and a synthetic reproduction. Do not post API keys, secrets, session keys, databases or private listening logs. Source developers can run `python -m unittest discover -s tests -v` and `python app.py --smoke-test .test-data/native-smoke.json`.
