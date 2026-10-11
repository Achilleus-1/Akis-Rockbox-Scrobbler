# Architecture

The interface is native Qt/PySide6. There is no HTML, JavaScript, WebView or HTTP listener. The original MIT liquid glass GLSL has been ported to a private OpenGL context.

| Component | Responsibility |
| --- | --- |
| `app.py` | Desktop entry point. |
| `desktop.py` | Native window, themes, selection, dialogs, confirmation and worker-result handling. |
| `glass.py` | Two-pass OpenGL renderer, native fallback, panel lenses and pocket-player vector artwork. |
| `assets/shaders/` | Restored environment, glass/refraction and copy shaders with dark-mode support. |
| `scrobbler.py` | Parser, SQLite queue, Last.fm protocol, Windows DPAPI and instance lock. |
| `version.py` | Shared application identity and release version. |
| `assets/` | App icon and Achilleus branding. |
| `tests/` | Backend tests and actual native UI integration tests using fake Last.fm replies. |
| `build.py` | PyInstaller one-folder build and portable ZIP with runtime/licenses. |
| `installer/setup.iss` | Per-user Windows installation, shortcuts and uninstall. |
| `tools/` | Installer compiler wrapper and explicit source archive manifest. |

## Threads

Qt widgets are accessed only from the main thread. Import and account operations run on a background worker and return through a thread-safe queue. Submission has its own backend worker. Polling avoids acquiring backend state while a network operation holds its lock, so authentication cannot freeze the window. Closing is held during active work.

## Glass rendering

An offscreen OpenGL 2.1 context first draws the animated cyan/lavender/mint environment into a framebuffer texture. A second pass samples and refracts it through rounded panel lenses, adding edge dispersion, frosted centers, pointer reflections, and up to four click ripples. The final image is painted behind normal native controls. Scissor rectangles follow each panel and its scroll viewport. No desktop pixels are sampled.

Frames are capped at 30 fps and 1.4 million pixels. The timer stops when hidden, minimized, inactive, when live glass is disabled, or when Windows requests reduced motion. Unsupported graphics use native gradient/ribbon painting and glossy panel surfaces. Qt libraries remain replaceable shared DLLs in `_internal`.

The backend's `/api/...` dispatch identifiers remain internal operation names for compatibility with existing backend tests. They are direct Python calls and are never exposed over HTTP.

## Storage

SQLite uses WAL journaling and full synchronization. `tracks` holds original metadata and filenames; `outcomes` stores account-specific receipts and actual submitted timestamps; `remaps` stores planned adjusted dates; `preferences` stores history settings, `dark_mode`, and `live_glass`. Sample preview rows live only in the UI and cannot be submitted.

Fingerprints use normalized artist/title and original listening timestamps. Remapping does not change identity. Receipts survive clearing the queue. Windows DPAPI credentials are separate from SQLite. The original `RockboxRelay` storage path and schema are retained for upgrades.

## Submission lifecycle

The UI confirms the selected account and timestamps. Backend validation rejects an outdated account/date plan. Plays are submitted oldest first in batches of 50; `sending` is persisted before network I/O. Receipts are matched to timestamps, with metadata matching for ambiguous shared times. Entire responses are validated before assigning outcomes.

Verified acceptance becomes `accepted`, service rejection becomes `ignored`, and unverifiable/interrupted outcomes become `uncertain`. Remaining `sending` records become `uncertain` after restart. They require a manual profile check before retrying.

Last.fm uses verified HTTPS, timeouts and no redirects. MD5 is used only for Last.fm's required API signature. Releases bundle Python and Qt. FFmpeg is unnecessary.
