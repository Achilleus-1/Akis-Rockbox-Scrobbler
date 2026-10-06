"""Aki's Rockbox Scrobbler: a local, dependency-free Rockbox -> Last.fm scrobbler."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 8 * 1024 * 1024
MAX_ROWS = 20000
SCROBBLE_WINDOW = 14 * 86400
API_URL = "https://ws.audioscrobbler.com/2.0/"


class AppError(Exception):
    pass


class LastfmError(AppError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def signature(params, secret):
    # MD5 is required by Last.fm's protocol; it is not used for local encryption.
    text = "".join(k + str(params[k]) for k in sorted(params) if k not in {"format", "callback", "api_sig"})
    return hashlib.md5((text + secret).encode("utf-8")).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Lastfm:
    def __init__(self, credentials):
        self.credentials = credentials

    def call(self, method, **values):
        params = {"method": method, "api_key": self.credentials["api_key"], **values}
        params["api_sig"] = signature(params, self.credentials["secret"])
        params["format"] = "json"
        request = urllib.request.Request(API_URL, urllib.parse.urlencode(params).encode("utf-8"),
                                         headers={"User-Agent": "AkisRockboxScrobbler/1.0", "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            raw = exc.read(65536)
            try:
                data = json.loads(raw)
                if "error" in data:
                    raise LastfmError(str(data.get("message", "Last.fm rejected the request.")), int(data["error"]))
            except (ValueError, TypeError):
                pass
            raise LastfmError("Last.fm returned an HTTP error. The submission outcome may be unknown.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise LastfmError("Could not reach Last.fm securely. Check your connection. If submitting, the outcome may be unknown.") from None
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError
            if "error" in data:
                raise LastfmError(str(data.get("message", "Last.fm rejected the request.")), int(data["error"]))
            return data
        except (ValueError, TypeError):
            raise LastfmError("Last.fm returned an unreadable response. The outcome may be unknown.") from None


def protect(data: bytes, decrypt=False):
    """Encrypt with Windows DPAPI for the current Windows user. Never fall back to plaintext."""
    if os.name != "nt":
        raise AppError("Remembering credentials requires Windows. Leave 'Remember on this PC' unchecked.")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(source), "Aki's Rockbox Scrobbler", None, None, None, 1, ctypes.byref(result))
    fn.restype = wintypes.BOOL
    if not fn(*args):
        raise AppError("Windows could not unlock/save credentials for this user. Reconnect your account.")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


def fingerprint(artist, track, timestamp):
    # Album is deliberately excluded: the same play may be re-exported with improved metadata.
    return hashlib.sha256(json.dumps([artist.casefold().strip(), track.casefold().strip(), timestamp],
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def scrobble_results(batch, response):
    """Match receipts by listening time, without assuming Last.fm's array order."""
    def unknown(reason):
        raise LastfmError(f"Could not verify Last.fm's response: {reason}. "
                          "This batch may already be on your profile. Check its outcome before retrying.")

    def text(value):
        return value.get("#text") if isinstance(value, dict) else value

    def integer(value):
        value = text(value)
        if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r"[0-9]+", str(value)):
            return None
        return int(value)

    container = response.get("scrobbles") if isinstance(response, dict) else None
    if not isinstance(container, dict):
        unknown("missing scrobble results")
    results = container.get("scrobble", [])
    if isinstance(results, dict):
        results = [results]
    if not isinstance(results, list) or len(results) != len(batch):
        unknown("the number of returned plays does not match the submitted batch")
    requested, returned = {}, {}
    for row in batch:
        requested.setdefault(row["timestamp"], []).append(row)
    for result in results:
        if not isinstance(result, dict):
            unknown("a play result is malformed")
        message = result.get("ignoredMessage", result.get("ignoredmessage"))
        if not isinstance(message, dict):
            unknown("a play has no readable acceptance code")
        attrs = message.get("@attr", {})
        code = integer(message.get("code", attrs.get("code") if isinstance(attrs, dict) else None))
        if code is None:
            unknown("a play has no readable acceptance code")
        timestamp = integer(result.get("timestamp"))
        if timestamp not in requested:
            unknown("a returned listening time does not match any submitted play")
        returned.setdefault(timestamp, []).append((result, str(code), str(message.get("#text", ""))))
    if any(len(returned.get(timestamp, [])) != len(rows) for timestamp, rows in requested.items()):
        unknown("returned listening times do not match the submitted batch")

    parsed = []
    for timestamp, rows in requested.items():
        receipts = returned[timestamp]
        if len(rows) == 1 or len({(code, message) for _, code, message in receipts}) == 1:
            parsed.extend((row, code, message) for row, (_, code, message) in zip(rows, receipts))
            continue
        # Shared timestamps need metadata to distinguish different outcomes. Corrections
        # may prevent a unique match; hold such a batch rather than assigning wrong receipts.
        unmatched = list(rows)
        for result, code, message in receipts:
            identity = tuple(str(text(result.get(field)) or "").strip().casefold() for field in ("artist", "track"))
            matches = [row for row in unmatched if (row["artist"].strip().casefold(), row["track"].strip().casefold()) == identity]
            if len(matches) != 1:
                unknown("plays sharing a listening time cannot be distinguished")
            row = matches[0]
            unmatched.remove(row)
            parsed.append((row, code, message))

    attrs = container.get("@attr", container)
    if isinstance(attrs, dict):
        for name, count in (("accepted", sum(code == "0" for _, code, _ in parsed)),
                            ("ignored", sum(code != "0" for _, code, _ in parsed))):
            if name in attrs and integer(attrs[name]) != count:
                unknown("the response totals conflict with individual play results")
    return parsed


def parse_log(text, offset=0, now=None):
    now = int(time.time()) if now is None else now
    rows, issues, seen = [], [], set()
    lines = text.lstrip("\ufeff").splitlines()
    if len(lines) > 100000:
        raise AppError("This log has too many lines. Split it into files of at most 100,000 lines.")
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) not in (7, 8):
            issues.append({"line": number, "reason": "Expected 7 or 8 tab-separated fields. Export .scrobbler.log from Rockbox's lastfm_scrobbler plugin; playback.log is a different format."})
            continue
        artist, album, track, tracknum, duration, rating, timestamp = (v.strip() for v in fields[:7])
        try:
            duration, timestamp, tracknum = int(duration), int(timestamp), int(tracknum)
        except ValueError:
            issues.append({"line": number, "reason": "Invalid duration, track number, or timestamp."})
            continue
        reason = ""
        # User preference: treat every parseable entry as at least 50% listened.
        # Preserve Rockbox's original flag for provenance; do not filter by it.
        if not artist or not track or artist.casefold() in {"<untagged>", "untagged", "unknown artist"}:
            reason = "Missing artist or title metadata."
        elif duration <= 0:
            reason = "Track duration must be positive."
        elif timestamp <= 0:
            reason = "No valid listening time; set the player's clock."
        timestamp += offset
        if not reason and timestamp > now:
            reason = "Listening time is in the future; check the player's clock or time correction."
        if any(len(v) > 2000 for v in (artist, album, track)):
            reason = "Metadata is too long."
        key = fingerprint(artist, track, timestamp)
        if not reason and key in seen:
            reason = "Duplicate play in this file."
        if reason:
            issues.append({"line": number, "reason": reason})
            continue
        seen.add(key)
        rows.append({"id": key, "artist": artist, "album": album, "track": track, "tracknum": tracknum,
                     "duration": duration, "timestamp": timestamp, "mbid": fields[7].strip() if len(fields) == 8 else "",
                     "original_rating": rating, "assumed_listened_percent": 50})
        if len(rows) > MAX_ROWS:
            raise AppError("This log has too many tracks. Import at most 20,000 plays at once.")
    return rows, issues


class App:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.credentials = {}
        self.pending_token = None
        self.remember = False
        self.warning = ""
        self.job = {"running": False, "message": "", "done": 0, "total": 0}
        self.db = sqlite3.connect(self.data_dir / "relay.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS tracks (id TEXT PRIMARY KEY, data TEXT NOT NULL, filename TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS outcomes (account TEXT, id TEXT, status TEXT, message TEXT, updated INTEGER, PRIMARY KEY(account,id))")
        outcome_columns = {row[1] for row in self.db.execute("PRAGMA table_info(outcomes)")}
        if "ignored_code" not in outcome_columns:
            self.db.execute("ALTER TABLE outcomes ADD COLUMN ignored_code TEXT NOT NULL DEFAULT ''")
        if "submitted_timestamp" not in outcome_columns:
            self.db.execute("ALTER TABLE outcomes ADD COLUMN submitted_timestamp INTEGER")
        self.db.execute("CREATE TABLE IF NOT EXISTS preferences (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS remaps (id TEXT PRIMARY KEY, timestamp INTEGER NOT NULL)")
        self.db.execute("UPDATE outcomes SET status='uncertain', message='App closed during submission. Check your Last.fm history before retrying.' WHERE status='sending'")
        self.db.commit()
        credential_file = self.data_dir / "credentials.dpapi"
        if credential_file.exists():
            try:
                self.credentials = json.loads(protect(credential_file.read_bytes(), decrypt=True))
                self.remember = True
            except (AppError, ValueError, OSError):
                self.warning = "Saved credentials could not be unlocked. Connect again from Settings."

    def save_credentials(self):
        target = self.data_dir / "credentials.dpapi"
        if self.remember:
            encrypted = protect(json.dumps(self.credentials).encode("utf-8"))
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(encrypted)
            temporary.replace(target)
        else:
            target.unlink(missing_ok=True)

    def account(self):
        return self.credentials.get("username", "").casefold()

    def preferences(self):
        saved = self.db.execute("SELECT value FROM preferences WHERE name='remap_outdated'").fetchone()
        return {"remap_outdated": bool(saved and saved[0] == "true")}

    def update_remaps(self, force=False):
        """Plan dates once, retaining source fingerprints and all submitted/uncertain receipts."""
        if not self.preferences()["remap_outdated"]:
            return 0
        now = int(time.time())
        candidates = []
        saved_dates = dict(self.db.execute("SELECT id,timestamp FROM remaps"))
        for key, raw, status, code, message in self.db.execute(
            "SELECT t.id,t.data,o.status,o.ignored_code,o.message FROM tracks t "
            "LEFT JOIN outcomes o ON t.id=o.id AND o.account=?", (self.account(),)):
            row = json.loads(raw)
            old_timestamp_rejection = status == "ignored" and (code == "3" or
                (not code and "timestamp" in (message or "").casefold() and
                 any(word in (message or "").casefold() for word in ("old", "past"))))
            if row["timestamp"] < now - SCROBBLE_WINDOW and (status in (None, "pending") or old_timestamp_rejection):
                candidates.append(row)
        if not candidates:
            return 0
        needed = force or any(not now - SCROBBLE_WINDOW < saved_dates.get(row["id"], 0) <= now for row in candidates)
        if not needed:
            return 0
        candidates.sort(key=lambda row: (row["timestamp"], row["id"]))
        end = now - 60
        # Spread the older plays through at most 13 days, preserving their order.
        span = min(13 * 86400, max(candidates[-1]["timestamp"] - candidates[0]["timestamp"], len(candidates) - 1))
        start = end - span
        with self.db:
            for index, row in enumerate(candidates):
                timestamp = end if len(candidates) == 1 else start + index * span // (len(candidates) - 1)
                self.db.execute("INSERT OR REPLACE INTO remaps VALUES(?,?)", (row["id"], timestamp))
                self.db.execute("DELETE FROM outcomes WHERE account=? AND id=? AND status='ignored' "
                                "AND (ignored_code='3' OR ignored_code='')", (self.account(), row["id"]))
        return len(candidates)

    def set_preferences(self, data):
        value = data.get("remap_outdated")
        if not isinstance(value, bool):
            raise AppError("Choose whether to adjust outdated listening dates.")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO preferences VALUES('remap_outdated',?)", ("true" if value else "false",))
        return self.update_remaps(force=value)

    def state(self):
        with self.lock:
            rows = []
            remap = self.preferences()["remap_outdated"]
            now = int(time.time())
            for raw, filename, status, message, submitted_timestamp, adjusted in self.db.execute(
                "SELECT t.data,t.filename,o.status,o.message,o.submitted_timestamp,r.timestamp FROM tracks t "
                "LEFT JOIN outcomes o ON t.id=o.id AND o.account=? LEFT JOIN remaps r ON t.id=r.id",
                (self.account(),)):
                row = json.loads(raw)
                row["original_timestamp"] = row["timestamp"]
                row.update(filename=filename, status=status or "pending", message=message or "")
                if row["status"] != "pending" and submitted_timestamp:
                    row["timestamp"] = submitted_timestamp
                elif row["status"] == "pending" and remap and adjusted and row["original_timestamp"] < now - SCROBBLE_WINDOW:
                    row["timestamp"] = adjusted
                row["date_adjusted"] = row["timestamp"] != row["original_timestamp"]
                if row["status"] == "pending" and row["timestamp"] < now - SCROBBLE_WINDOW:
                    row.update(status="expired", message="Older than Last.fm's 14-day window. Enable date adjustment in Settings to include it.")
                rows.append(row)
            rows.sort(key=lambda r: r["timestamp"], reverse=True)
            return {"tracks": rows, "username": self.credentials.get("username", ""),
                    "configured": bool(self.credentials.get("api_key")), "remember": self.remember,
                    "auth_pending": bool(self.pending_token), "job": dict(self.job), "warning": self.warning,
                    "storage": str(self.data_dir), "preferences": self.preferences()}

    def require_idle(self):
        if self.job["running"]:
            raise AppError("Wait for the current submission to finish first.")

    def dispatch(self, route, data):
        with self.lock:
            if route == "/api/import":
                self.require_idle()
                content = data.get("content", "")
                if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_UPLOAD:
                    raise AppError("Choose a UTF-8 log smaller than 8 MB.")
                try:
                    offset = float(data.get("offset", 0))
                    if not -24 <= offset <= 24 or offset * 4 != int(offset * 4):
                        raise ValueError
                except (TypeError, ValueError, OverflowError):
                    raise AppError("Time correction must be between -24 and +24 hours, in 15-minute steps.") from None
                rows, issues = parse_log(content, int(offset * 3600))
                existing = {row[0] for row in self.db.execute("SELECT id FROM tracks")}
                if len(existing | {row["id"] for row in rows}) > MAX_ROWS:
                    raise AppError("Your queue can hold 20,000 plays. Finish or clear it before importing more.")
                filename = str(data.get("filename", "scrobbler.log"))[:255].replace("\\", "/").split("/")[-1]
                added = 0
                with self.db:
                    for row in rows:
                        added += self.db.execute("INSERT OR IGNORE INTO tracks VALUES(?,?,?)",
                                                 (row["id"], json.dumps(row), filename)).rowcount
                self.warning = ""
                self.update_remaps()
                outdated = sum(row["status"] == "expired" for row in self.state()["tracks"])
                return {"added": added, "duplicates": len(rows) - added, "excluded": len(issues), "issues": issues[:300], "outdated": outdated}
            if route == "/api/preferences":
                self.require_idle()
                return {"ok": True, "adjusted": self.set_preferences(data)}
            if route == "/api/settings":
                self.require_idle()
                key, secret = str(data.get("api_key", "")).strip(), str(data.get("secret", "")).strip()
                if not re.fullmatch(r"[a-fA-F0-9]{32}", key) or not re.fullmatch(r"[a-fA-F0-9]{32}", secret):
                    raise AppError("Enter the 32-character API key and shared secret provided by Last.fm.")
                previous, previous_remember = self.credentials, self.remember
                self.credentials = {"api_key": key, "secret": secret}
                self.remember = data.get("remember") is True
                try:
                    self.save_credentials()
                except AppError:
                    self.credentials, self.remember = previous, previous_remember
                    raise
                self.pending_token = None
                self.warning = ""
                return {"ok": True}
            if route == "/api/auth/start":
                self.require_idle()
                if not self.credentials.get("api_key"):
                    raise AppError("Add your Last.fm API key and shared secret in Settings first.")
                result = Lastfm(self.credentials).call("auth.getToken")
                token = result.get("token")
                # Treat service-issued tokens as opaque values, not MD5 hashes.
                # The API signature is hexadecimal; the request token need not be.
                # Also tolerate the text-node representation used by XML-to-JSON serializers.
                if isinstance(token, dict):
                    token = token.get("#text")
                if not isinstance(token, str) or not 1 <= len(token) <= 4096 or any(
                    ord(char) < 33 or ord(char) > 126 for char in token
                ):
                    raise AppError("Last.fm's auth.getToken response did not contain a usable token. "
                                   "Please try connecting again. Your API credentials were kept.")
                self.pending_token = token
                return {"url": "https://www.last.fm/api/auth/?" + urllib.parse.urlencode({"api_key": self.credentials["api_key"], "token": token})}
            if route == "/api/auth/finish":
                self.require_idle()
                if not self.pending_token:
                    raise AppError("Start the Last.fm connection first.")
                result = Lastfm(self.credentials).call("auth.getSession", token=self.pending_token)
                session = result.get("session", {})
                if not session.get("key") or not session.get("name"):
                    raise AppError("Last.fm did not return an account session.")
                self.credentials.update(session_key=session["key"], username=session["name"])
                self.pending_token = None
                self.save_credentials()
                self.update_remaps()
                return {"ok": True}
            if route == "/api/disconnect":
                self.require_idle()
                self.credentials = {}
                self.pending_token = None
                self.remember = False
                self.save_credentials()
                return {"ok": True}
            if route == "/api/clear":
                self.require_idle()
                with self.db:
                    self.db.execute("DELETE FROM tracks")
                    self.db.execute("DELETE FROM remaps")
                return {"ok": True}
            if route == "/api/resolve":
                self.require_idle()
                if not self.account():
                    raise AppError("Connect your Last.fm account first.")
                if str(data.get("account", "")).casefold() != self.account():
                    raise AppError("The connected account changed. Refresh and review this play again.")
                action = data.get("action")
                if action not in {"retry", "accepted"} or data.get("confirmed") is not True:
                    raise AppError("Confirm that you checked your Last.fm listening history first.")
                with self.db:
                    for key in self.validate_ids(data):
                        if action == "retry":
                            self.db.execute("DELETE FROM outcomes WHERE account=? AND id=? AND status='uncertain'", (self.account(), key))
                        else:
                            self.db.execute("UPDATE outcomes SET status='accepted',message='Confirmed in profile by user' WHERE account=? AND id=? AND status='uncertain'", (self.account(), key))
                self.update_remaps()
                return {"ok": True}
            if route == "/api/submit":
                self.require_idle()
                if not self.credentials.get("session_key"):
                    raise AppError("Connect your Last.fm account before submitting.")
                if data.get("confirmed") is not True:
                    raise AppError("Review and confirm the submission first.")
                if str(data.get("account", "")).casefold() != self.account():
                    raise AppError("The connected account changed. Refresh and confirm the destination again.")
                ids = set(self.validate_ids(data))
                rows = [r for r in self.state()["tracks"] if r["id"] in ids and r["status"] == "pending"]
                rows.sort(key=lambda r: r["timestamp"])
                if not rows:
                    raise AppError("Select at least one eligible, unsent play.")
                reviewed_dates = data.get("timestamps", {})
                if not isinstance(reviewed_dates, dict) or any(
                    row["date_adjusted"] and reviewed_dates.get(row["id"]) != row["timestamp"] for row in rows
                ):
                    raise AppError("Adjusted dates changed or were not reviewed. Refresh the queue and confirm again.")
                self.job = {"running": True, "message": "Submitting to Last.fm…", "done": 0, "total": len(rows)}
                threading.Thread(target=self.submit, args=(rows, dict(self.credentials)), daemon=True).start()
                return {"ok": True}
            raise AppError("Unknown action.")

    @staticmethod
    def validate_ids(data):
        ids = data.get("ids")
        if not isinstance(ids, list) or len(ids) > MAX_ROWS or any(not isinstance(i, str) or not re.fullmatch(r"[a-f0-9]{64}", i) for i in ids):
            raise AppError("Invalid track selection.")
        return ids

    def record(self, account, rows, status, message="", ignored_code=""):
        with self.lock, self.db:
            for row in rows:
                self.db.execute("INSERT OR REPLACE INTO outcomes(account,id,status,message,updated,ignored_code,submitted_timestamp) VALUES(?,?,?,?,?,?,?)",
                                (account, row["id"], status, message, int(time.time()), ignored_code, row["timestamp"]))

    def submit(self, rows, credentials):
        account = credentials["username"].casefold()
        client = Lastfm(credentials)
        accepted, ignored = 0, 0
        batch = []
        try:
            for start in range(0, len(rows), 50):
                batch = rows[start:start + 50]
                self.record(account, batch, "sending", "Waiting for Last.fm's response")
                params = {"sk": credentials["session_key"]}
                for index, row in enumerate(batch):
                    for name, value in (("artist", row["artist"]), ("track", row["track"]), ("album", row["album"]),
                                        ("timestamp", row["timestamp"]), ("duration", row["duration"]),
                                        ("trackNumber", row["tracknum"] if row["tracknum"] > 0 else ""), ("mbid", row["mbid"])):
                        if value != "":
                            params[f"{name}[{index}]"] = value
                response = client.call("track.scrobble", **params)
                # Validate the entire response before marking any row accepted.
                parsed = scrobble_results(batch, response)
                for row, code, message in parsed:
                    if code == "0":
                        self.record(account, [row], "accepted", "Added to your Last.fm profile")
                        accepted += 1
                    else:
                        self.record(account, [row], "ignored", message or f"Last.fm ignored this play (code {code})", ignored_code=code)
                        ignored += 1
                with self.lock:
                    self.job.update(done=start + len(batch), message=f"{accepted} accepted · {ignored} ignored")
                batch = []
                if start + 50 < len(rows):
                    time.sleep(1)
            with self.lock:
                self.job["message"] = f"Finished: {accepted} accepted, {ignored} ignored by Last.fm."
        except Exception as exc:
            # A timeout/crash can occur AFTER Last.fm stores the batch. Never blindly retry it.
            known_rejected = isinstance(exc, LastfmError) and exc.code is not None
            status = "pending" if known_rejected else "uncertain"
            message = str(exc) if isinstance(exc, AppError) else "Submission interrupted. Check your profile before retrying."
            if batch:
                try:
                    self.record(account, batch, status, message)
                except sqlite3.Error:
                    pass  # Durable 'sending' becomes 'uncertain' on next startup.
            with self.lock:
                self.job["message"] = message
                if isinstance(exc, LastfmError) and exc.code == 9:
                    self.credentials.pop("session_key", None)
                    self.credentials.pop("username", None)
                    try:
                        self.save_credentials()
                    except (AppError, OSError):
                        pass
        finally:
            with self.lock:
                self.job["running"] = False


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, app, port=0):
        super().__init__(("127.0.0.1", port), Handler)
        self.app = app
        self.launch_token = secrets.token_urlsafe(32)
        self.session_token = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.cookie_name = f"relay_session_{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Avoid logging local session tokens and metadata.

    def respond(self, status, body, content_type="application/json", headers=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def allowed_host(self):
        return self.headers.get("Host") == urllib.parse.urlsplit(self.server.origin).netloc

    def authorized(self):
        cookies = self.headers.get("Cookie", "").split(";")
        expected = self.server.cookie_name + "=" + self.server.session_token
        return any(secrets.compare_digest(cookie.strip(), expected) for cookie in cookies)

    def do_GET(self):
        if not self.allowed_host():
            self.respond(403, {"error": "Invalid local host."})
            return
        path = urllib.parse.urlsplit(self.path).path
        if secrets.compare_digest(path, "/launch/" + self.server.launch_token):
            self.respond(303, b"", headers={"Location": "/", "Set-Cookie": f"{self.server.cookie_name}={self.server.session_token}; HttpOnly; SameSite=Strict; Path=/"})
            return
        if not self.authorized():
            self.respond(403, {"error": "Open the app using Start Akis Rockbox Scrobbler.cmd to unlock this local session."})
            return
        if path == "/api/state":
            state = self.server.app.state()
            state["csrf"] = self.server.csrf
            self.respond(200, state)
        elif path in {"/", "/app.js", "/style.css", "/favicon.svg", "/logo-black.png", "/logo-white.png"}:
            name, mime = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                          "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.svg": ("logo-black.png", "image/png"),
                          "/logo-black.png": ("logo-black.png", "image/png"), "/logo-white.png": ("logo-white.png", "image/png")}[path]
            self.respond(200, (ROOT / "web" / name).read_bytes(), mime)
        else:
            self.respond(404, {"error": "Not found."})

    def do_POST(self):
        if not self.allowed_host() or not self.authorized() or self.headers.get("Origin") != self.server.origin or not secrets.compare_digest(self.headers.get("X-CSRF", ""), self.server.csrf):
            self.respond(403, {"error": "Local session check failed. Reopen the app from its launcher."})
            return
        if self.headers.get("Content-Type") != "application/json":
            self.respond(415, {"error": "Expected JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_UPLOAD * 2:
                self.respond(413, {"error": "File is too large (8 MB maximum)."})
                return
            self.connection.settimeout(15)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError
            result = self.server.app.dispatch(urllib.parse.urlsplit(self.path).path, data)
            self.respond(200, result)
        except (AppError, ValueError, TypeError) as exc:
            self.respond(400, {"error": str(exc) if isinstance(exc, AppError) else "Invalid request."})
        except Exception:
            self.respond(500, {"error": "The local action could not be completed. Check available disk space and try again."})


def acquire_instance_lock(directory):
    handle = open(directory / "instance.lock", "a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "RockboxRelay")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    instance = acquire_instance_lock(args.data_dir)
    launch_file = args.data_dir / "launch.url"
    if instance is None:
        if launch_file.exists() and not args.no_browser:
            url = launch_file.read_text().strip()
            if re.fullmatch(r"http://127\.0\.0\.1:\d+/launch/[A-Za-z0-9_-]+", url):
                webbrowser.open(url)
        print("Aki's Rockbox Scrobbler is already running. Use its browser tab or close its existing terminal first.")
        return
    app = App(args.data_dir)
    server = Server(app, args.port)
    url = server.origin + "/launch/" + server.launch_token
    launch_file.write_text(url)
    print(f"Aki's Rockbox Scrobbler is running at {server.origin}")
    print("Keep this window open. Press Ctrl+C here to stop the app.")
    if args.no_browser:
        print("Launch URL:", url)
    else:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Aki's Rockbox Scrobbler…")
    finally:
        server.server_close()
        launch_file.unlink(missing_ok=True)
        instance.close()


if __name__ == "__main__":
    main()
