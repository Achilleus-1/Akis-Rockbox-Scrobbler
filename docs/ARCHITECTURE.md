# Architecture

The interface is native Tk/ttk. There is no HTML, JavaScript, WebView or HTTP listener. The previous browser renderer and local server have been removed.

| Component | Responsibility |
| --- | --- |
| `app.py` | Desktop entry point. |
| `desktop.py` | Native window, themes, selection, dialogs, confirmation and worker-result handling. |
| `scrobbler.py` | Parser, SQLite queue, Last.fm protocol, Windows DPAPI and instance lock. |
| `version.py` | Shared application identity and release version. |
| `assets/` | App icon and Achilleus branding. |
| `tests/` | Backend tests and actual native UI integration tests using fake Last.fm replies. |
| `build.py` | PyInstaller one-folder build and portable ZIP with runtime/licenses. |
| `installer/setup.iss` | Per-user Windows installation, shortcuts and uninstall. |
| `tools/` | Installer compiler wrapper and explicit source archive manifest. |

## Threads

Tk widgets are accessed only from the main thread. Import and account operations run on a background worker and return through a thread-safe queue. Submission has its own backend worker. Polling avoids acquiring backend state while a network operation holds its lock, so authentication cannot freeze the window. Closing is held during active work.

The backend's `/api/...` dispatch identifiers remain internal operation names for compatibility with existing backend tests. They are direct Python calls and are never exposed over HTTP.

## Storage

SQLite uses WAL journaling and full synchronization. `tracks` holds original metadata and filenames; `outcomes` stores account-specific receipts and actual submitted timestamps; `remaps` stores planned adjusted dates; `preferences` stores history settings and `dark_mode`.

Fingerprints use normalized artist/title and original listening timestamps. Remapping does not change identity. Receipts survive clearing the queue. Windows DPAPI credentials are separate from SQLite. The original `RockboxRelay` storage path and schema are retained for upgrades.

## Submission lifecycle

The UI confirms the selected account and timestamps. Backend validation rejects an outdated account/date plan. Plays are submitted oldest first in batches of 50; `sending` is persisted before network I/O. Receipts are matched to timestamps, with metadata matching for ambiguous shared times. Entire responses are validated before assigning outcomes.

Verified acceptance becomes `accepted`, service rejection becomes `ignored`, and unverifiable/interrupted outcomes become `uncertain`. Remaining `sending` records become `uncertain` after restart. They require a manual profile check before retrying.

Last.fm uses verified HTTPS, timeouts and no redirects. MD5 is used only for Last.fm's required API signature. Native source operation uses Python's standard library; releases bundle Python and Tcl/Tk. FFmpeg is unnecessary.
