import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request

from scrobbler import App, AppError, Lastfm, LastfmError, Server, acquire_instance_lock, parse_log, protect, signature


NOW = 1791216000


def log(artist="Björk", title="Jóga", timestamp=NOW - 3600, rating="L", duration=300, album="Homogenic", mbid=""):
    return f"{artist}\t{album}\t{title}\t1\t{duration}\t{rating}\t{timestamp}\t{mbid}"


def response(rows, codes=None):
    codes = codes or ["0"] * len(rows)
    return {"scrobbles": {"@attr": {"accepted":sum(c == "0" for c in codes), "ignored":sum(c != "0" for c in codes)},
                          "scrobble": [{"timestamp": str(r["timestamp"]),
                                       "artist":{"corrected":"0", "#text":r.get("artist", "")},
                                       "track":{"corrected":"0", "#text":r.get("track", "")},
                                       "ignoredMessage": {"code": c, "#text": "Filtered" if c != "0" else ""}} for r, c in zip(rows, codes)]}}


class ParserTests(unittest.TestCase):
    def test_real_export_format_unicode_bom_comments_crlf(self):
        content = "\ufeff#AUDIOSCROBBLER/1.1\r\n#TZ/UNKNOWN\r\n" + log(mbid="abc") + "\r\n" + log(title="Army of Me", timestamp=NOW - 500)[:-1]
        rows, issues = parse_log(content, now=NOW)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["artist"], "Björk")
        self.assertEqual(rows[0]["mbid"], "abc")
        self.assertFalse(issues)

    def test_each_exclusion_has_a_reason(self):
        content = "\n".join([log(duration=0), log(duration=-10), log(artist=""), log(timestamp=0),
                             log(timestamp=NOW + 1), log(title=""),
                             "1791216000:10000:20000:/music/test.mp3", log(duration="bad")])
        rows, issues = parse_log(content, now=NOW)
        self.assertFalse(rows)
        self.assertEqual(len(issues), 8)
        self.assertEqual([i["line"] for i in issues], list(range(1, 9)))
        self.assertIn("playback.log", issues[6]["reason"])

    def test_skipped_old_and_short_entries_assumed_listened(self):
        content = "\n".join([log(rating="S", timestamp=NOW - 400 * 86400),
                             log(rating="L", timestamp=NOW - 30 * 86400),
                             log(rating="S", duration=20, timestamp=NOW - 1000)])
        rows, issues = parse_log(content, now=NOW)
        self.assertFalse(issues)
        self.assertEqual(len(rows), 3)
        self.assertEqual([row['timestamp'] for row in rows], [NOW - 400 * 86400, NOW - 30 * 86400, NOW - 1000])
        self.assertEqual([row['original_rating'] for row in rows], ['S', 'L', 'S'])
        self.assertTrue(all(row['assumed_listened_percent'] == 50 for row in rows))

    def test_duplicates_differently_timed_repeats_and_album_changes(self):
        rows, issues = parse_log("\n".join([log(), log(album="Other"), log(timestamp=NOW - 500)]), now=NOW)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(issues), 1)

    def test_explicit_clock_offset_only(self):
        rows, _ = parse_log(log(timestamp=NOW + 3600), offset=-7200, now=NOW)
        self.assertEqual(rows[0]["timestamp"], NOW - 3600)
        rows, _ = parse_log(log(timestamp=0), offset=NOW, now=NOW)
        self.assertFalse(rows)

    def test_signature_sorts_keys_excludes_format_and_handles_unicode(self):
        params = {"track[2]":"Jóga", "format":"json", "api_key":"key", "method":"track.scrobble", "track[10]":"ten"}
        expected = hashlib.md5("api_keykeymethodtrack.scrobbletrack[10]tentrack[2]Jógasecret".encode()).hexdigest()
        self.assertEqual(signature(params, "secret"), expected)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(self.temp.name)
        self.app.credentials = {"api_key":"a"*32, "secret":"b"*32, "session_key":"c"*32, "username":"Alice"}

    def tearDown(self):
        self.app.db.close()
        self.temp.cleanup()

    def import_rows(self, count=1):
        content = "\n".join(log(timestamp=int(time.time()) - 3600 - i * 300) for i in range(count))
        self.app.dispatch('/api/import', {"content":content, "filename":".scrobbler.log"})
        return sorted(self.app.state()["tracks"], key=lambda r:r["timestamp"])

    def test_reimport_receipts_survive_clear_and_account_scoping(self):
        rows = self.import_rows()
        self.app.record("alice", rows, "accepted")
        self.app.dispatch('/api/clear', {})
        rows = self.import_rows()
        self.assertEqual(rows[0]["status"], "accepted")
        self.app.credentials["username"] = "Bob"
        self.assertEqual(self.app.state()["tracks"][0]["status"], "pending")
        self.assertNotIn("secret", self.app.state())
        self.assertNotIn("session_key", self.app.state())

    def test_mixed_accept_and_ignored_response(self):
        rows = self.import_rows(2)
        with patch.object(Lastfm, 'call', return_value=response(rows, ["0","3"])):
            self.app.submit(rows, self.app.credentials.copy())
        statuses = [r["status"] for r in sorted(self.app.state()["tracks"], key=lambda r:r["timestamp"])]
        self.assertEqual(statuses, ["accepted", "ignored"])
        self.assertFalse(self.app.job["running"])

    def test_batches_at_most_50_chronological(self):
        rows = self.import_rows(51)
        calls = []
        def fake(method, **params):
            stamps = [int(params[f'timestamp[{i}]']) for i in range(len([k for k in params if k.startswith('timestamp[')]))]
            calls.append(stamps)
            return response([{"timestamp":stamp} for stamp in stamps])
        with patch.object(Lastfm, 'call', side_effect=fake), patch('scrobbler.time.sleep'):
            self.app.submit(rows, self.app.credentials.copy())
        self.assertEqual([len(c) for c in calls], [50, 1])
        self.assertEqual(calls[0] + calls[1], sorted(calls[0] + calls[1]))
        self.assertTrue(all(r["status"] == "accepted" for r in self.app.state()["tracks"]))

    def test_timeout_holds_batch_and_remaining_plays_can_still_send(self):
        rows = self.import_rows(51)
        with patch.object(Lastfm, 'call', side_effect=LastfmError('Timeout')):
            self.app.submit(rows, self.app.credentials.copy())
        statuses = [r['status'] for r in self.app.state()['tracks']]
        self.assertEqual(statuses.count('uncertain'), 50)
        self.assertEqual(statuses.count('pending'), 1)
        with self.assertRaises(AppError):
            self.app.dispatch('/api/resolve', {'ids':[rows[0]['id']], 'action':'retry', 'account':'Alice'})
        self.app.dispatch('/api/resolve', {'ids':[rows[0]['id']], 'action':'accepted', 'account':'Alice', 'confirmed':True})
        self.assertEqual(next(r for r in self.app.state()['tracks'] if r['id'] == rows[0]['id'])['status'], 'accepted')

    def test_reported_rejection_is_not_marked_accepted(self):
        rows = self.import_rows()
        with patch.object(Lastfm, 'call', side_effect=LastfmError('Rate limit', 29)):
            self.app.submit(rows, self.app.credentials.copy())
        self.assertEqual(self.app.state()['tracks'][0]['status'], 'pending')

    def test_incomplete_or_wrong_timestamp_response_is_uncertain(self):
        rows = self.import_rows()
        for data in ({'scrobbles':{}}, response([{'timestamp':10}])):
            with patch.object(Lastfm, 'call', return_value=data):
                self.app.submit(rows, self.app.credentials.copy())
            self.assertEqual(self.app.state()['tracks'][0]['status'], 'uncertain')

    def test_reordered_batch_receipts_match_the_right_plays(self):
        rows = self.import_rows(50)
        codes = ['3' if index % 7 == 0 else '0' for index in range(50)]
        reply = response(rows, codes)
        results = reply['scrobbles']['scrobble']
        # Exercise both reverse order and the 0,1,10,... ordering of string indices.
        for order in (list(reversed(range(50))), sorted(range(50), key=str)):
            with self.subTest(order=order[:3]):
                reply['scrobbles']['scrobble'] = [results[index] for index in order]
                with patch.object(Lastfm, 'call', return_value=reply):
                    self.app.submit(rows, self.app.credentials.copy())
                states = {row['id']:row for row in self.app.state()['tracks']}
                for row, code in zip(rows, codes):
                    self.assertEqual(states[row['id']]['status'], 'accepted' if code == '0' else 'ignored')

    def test_single_receipt_and_text_node_fields(self):
        rows = self.import_rows()
        reply = response(rows)
        result = reply['scrobbles']['scrobble'][0]
        result['timestamp'] = {'#text':str(rows[0]['timestamp'])}
        result['ignoredmessage'] = {'@attr':{'code':0}, '#text':''}
        del result['ignoredMessage']
        reply['scrobbles']['scrobble'] = result
        with patch.object(Lastfm, 'call', return_value=reply):
            self.app.submit(rows, self.app.credentials.copy())
        self.assertEqual(self.app.state()['tracks'][0]['status'], 'accepted')

    def test_shared_timestamp_mixed_receipts_match_metadata(self):
        timestamp = int(time.time()) - 1000
        self.app.dispatch('/api/import', {'content':'\n'.join(log(title=title, timestamp=timestamp) for title in ['First', 'Second'])})
        rows = self.app.state()['tracks']
        reply = response(rows, ['0', '2'])
        reply['scrobbles']['scrobble'].reverse()
        with patch.object(Lastfm, 'call', return_value=reply):
            self.app.submit(rows, self.app.credentials.copy())
        by_id = {row['id']:row['status'] for row in self.app.state()['tracks']}
        self.assertEqual(by_id[rows[0]['id']], 'accepted')
        self.assertEqual(by_id[rows[1]['id']], 'ignored')

    def test_ambiguous_shared_timestamp_does_not_assign_receipts(self):
        timestamp = int(time.time()) - 1000
        self.app.dispatch('/api/import', {'content':'\n'.join(log(title=title, timestamp=timestamp) for title in ['First', 'Second'])})
        rows = self.app.state()['tracks']
        reply = response(rows, ['0', '2'])
        for result in reply['scrobbles']['scrobble']:
            result['track'] = {'corrected':'1', '#text':'Same corrected title'}
        with patch.object(Lastfm, 'call', return_value=reply):
            self.app.submit(rows, self.app.credentials.copy())
        self.assertTrue(all(row['status'] == 'uncertain' for row in self.app.state()['tracks']))
        self.assertIn('cannot be distinguished', self.app.job['message'])

    def test_malformed_receipts_and_conflicting_totals_hold_entire_batch(self):
        rows = self.import_rows(2)
        cases = []
        missing_code = response(rows)
        missing_code['scrobbles']['scrobble'][1]['ignoredMessage'] = {}
        cases.append((missing_code, 'acceptance code'))
        wrong_total = response(rows)
        wrong_total['scrobbles']['@attr']['accepted'] = 1
        cases.append((wrong_total, 'totals conflict'))
        repeated = response(rows)
        repeated['scrobbles']['scrobble'][1]['timestamp'] = str(rows[0]['timestamp'])
        cases.append((repeated, 'listening times do not match'))
        for reply, reason in cases:
            with self.subTest(reason=reason), patch.object(Lastfm, 'call', return_value=reply):
                self.app.submit(rows, self.app.credentials.copy())
                self.assertTrue(all(row['status'] == 'uncertain' for row in self.app.state()['tracks']))
                self.assertIn(reason, self.app.job['message'])

    def test_crash_recovery(self):
        rows = self.import_rows()
        self.app.record('alice', rows, 'sending')
        self.app.db.close()
        self.app = App(self.temp.name)
        self.app.credentials = {'username':'Alice'}
        self.assertEqual(self.app.state()['tracks'][0]['status'], 'uncertain')

    def test_settings_validation_disconnect_and_no_plaintext_storage(self):
        with self.assertRaises(AppError):
            self.app.dispatch('/api/settings', {'api_key':'bad', 'secret':'bad'})
        self.app.dispatch('/api/settings', {'api_key':'a'*32, 'secret':'b'*32, 'remember':False})
        self.assertFalse((Path(self.temp.name)/'credentials.dpapi').exists())
        self.app.dispatch('/api/disconnect', {})
        self.assertFalse(self.app.credentials)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI only')
    def test_dpapi_save_reload_disconnect(self):
        raw = b'secret session credential'
        encrypted = protect(raw)
        self.assertNotIn(raw, encrypted)
        self.assertEqual(protect(encrypted, decrypt=True), raw)
        self.app.remember = True
        self.app.save_credentials()
        reopened = App(self.temp.name)
        try:
            self.assertEqual(reopened.credentials['username'], 'Alice')
        finally:
            reopened.db.close()
        self.app.dispatch('/api/disconnect', {})
        self.assertFalse((Path(self.temp.name)/'credentials.dpapi').exists())

    def test_invalid_ids_offset_and_concurrent_changes_rejected(self):
        with self.assertRaises(AppError):
            self.app.dispatch('/api/import', {'content':log(), 'offset':'nan'})
        with self.assertRaises(AppError):
            self.app.dispatch('/api/submit', {'ids':['bogus'], 'confirmed':True})
        self.app.job['running'] = True
        for route in ['/api/clear','/api/disconnect','/api/settings','/api/import']:
            with self.assertRaises(AppError):
                self.app.dispatch(route, {})

    def test_single_instance_lock(self):
        first = acquire_instance_lock(Path(self.temp.name))
        try:
            second = acquire_instance_lock(Path(self.temp.name))
            self.assertIsNone(second)
        finally:
            first.close()

    def test_submission_requires_current_account_and_excludes_accepted_rows(self):
        rows = self.import_rows()
        with self.assertRaises(AppError):
            self.app.dispatch('/api/submit', {'ids':[rows[0]['id']], 'account':'Bob', 'confirmed':True})
        self.app.record('alice', rows, 'accepted')
        with self.assertRaises(AppError):
            self.app.dispatch('/api/submit', {'ids':[rows[0]['id']], 'account':'Alice', 'confirmed':True})

    def test_official_auth_flow_and_errors(self):
        self.app.credentials = {'api_key':'a'*32,'secret':'b'*32}
        with patch.object(Lastfm, 'call', return_value={'token':'d'*32}):
            result = self.app.dispatch('/api/auth/start', {})
        self.assertTrue(result['url'].startswith('https://www.last.fm/api/auth/?'))
        self.assertEqual(self.app.pending_token, 'd'*32)
        with patch.object(Lastfm, 'call', side_effect=LastfmError('Not authorized', 14)):
            with self.assertRaises(LastfmError):
                self.app.dispatch('/api/auth/finish', {})
        self.assertIsNotNone(self.app.pending_token)
        with patch.object(Lastfm, 'call', return_value={'session':{'name':'Alice','key':'c'*32}}):
            self.app.dispatch('/api/auth/finish', {})
        self.assertEqual(self.app.account(), 'alice')
        self.assertIsNone(self.app.pending_token)

    def test_auth_tokens_are_opaque_and_passed_unchanged(self):
        self.app.credentials = {'api_key':'a'*32, 'secret':'b'*32}
        for token in ['d'*32, 'GZijKLMNopQRsTuVwXyZ123456789012',
                      'different-length-token', 'Mixed_Case-Token~with+/=symbols']:
            with self.subTest(token=token):
                with patch.object(Lastfm, 'call', return_value={'token':token}):
                    result = self.app.dispatch('/api/auth/start', {})
                self.assertEqual(self.app.pending_token, token)
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(result['url']).query)
                self.assertEqual(query['token'], [token])
                with patch.object(Lastfm, 'call', return_value={'session':{'name':'Alice','key':'c'*32}}) as call:
                    self.app.dispatch('/api/auth/finish', {})
                    call.assert_called_once_with('auth.getSession', token=token)

    def test_auth_token_text_node_response(self):
        with patch.object(Lastfm, 'call', return_value={'token':{'#text':'MixedCaseToken_123'}}):
            self.app.dispatch('/api/auth/start', {})
        self.assertEqual(self.app.pending_token, 'MixedCaseToken_123')

    def test_malformed_auth_response_does_not_expose_secrets(self):
        for token in [None, '', 123, {}, {'#text':None}, 'with whitespace', 'line\nbreak', 'x'*4097]:
            with self.subTest(token_type=type(token).__name__):
                with patch.object(Lastfm, 'call', return_value={'token':token}):
                    with self.assertRaises(AppError) as error:
                        self.app.dispatch('/api/auth/start', {})
                self.assertIn('auth.getToken response', str(error.exception))
                self.assertIsNone(self.app.pending_token)
                self.assertNotIn('a'*32, str(error.exception))
                self.assertNotIn('b'*32, str(error.exception))

    def test_submit_job_runs_and_confirmed_selection_only(self):
        rows = self.import_rows(2)
        with patch.object(Lastfm, 'call', return_value=response(rows[:1])):
            self.app.dispatch('/api/submit', {'ids':[rows[0]['id']], 'account':'Alice', 'confirmed':True})
            for _ in range(100):
                if not self.app.state()['job']['running']:
                    break
                time.sleep(.01)
        statuses = [r['status'] for r in self.app.state()['tracks']]
        self.assertEqual(statuses.count('accepted'), 1)
        self.assertEqual(statuses.count('pending'), 1)

    def test_old_skipped_plays_import_and_submit_with_original_timestamp(self):
        timestamp = int(time.time()) - 365 * 86400
        result = self.app.dispatch('/api/import', {'content':log(rating='S', timestamp=timestamp), 'filename':'old.log'})
        self.assertEqual(result['added'], 1)
        self.assertEqual(result['excluded'], 0)
        rows = self.app.state()['tracks']
        self.assertEqual(rows[0]['status'], 'expired')
        self.assertEqual(rows[0]['timestamp'], timestamp)
        self.app.dispatch('/api/preferences', {'remap_outdated':True})
        rows = self.app.state()['tracks']
        self.assertEqual(rows[0]['status'], 'pending')
        self.assertEqual(rows[0]['original_timestamp'], timestamp)
        self.assertTrue(rows[0]['date_adjusted'])
        with patch.object(Lastfm, 'call', return_value=response(rows)) as call:
            self.app.submit(rows, self.app.credentials.copy())
            self.assertEqual(call.call_args.kwargs['timestamp[0]'], rows[0]['timestamp'])
        self.assertEqual(self.app.state()['tracks'][0]['status'], 'accepted')
        result = self.app.dispatch('/api/import', {'content':log(rating='S', timestamp=timestamp), 'filename':'old.log'})
        self.assertEqual(result['added'], 0)
        self.assertEqual(result['duplicates'], 1)

    def test_default_age_cutoff_is_enforced_for_submission(self):
        timestamp = int(time.time()) - 20 * 86400
        self.app.dispatch('/api/import', {'content':log(timestamp=timestamp)})
        row = self.app.state()['tracks'][0]
        self.assertFalse(self.app.preferences()['remap_outdated'])
        self.assertEqual(row['status'], 'expired')
        with self.assertRaises(AppError):
            self.app.dispatch('/api/submit', {'ids':[row['id']], 'account':'Alice', 'confirmed':True})

    def test_remap_preserves_order_bounds_recent_plays_and_deduplication(self):
        now = int(time.time())
        content = '\n'.join(log(timestamp=now - days * 86400) for days in [365, 100, 20, 1])
        self.app.dispatch('/api/import', {'content':content})
        result = self.app.dispatch('/api/preferences', {'remap_outdated':True})
        self.assertEqual(result['adjusted'], 3)
        rows = sorted(self.app.state()['tracks'], key=lambda row:row['original_timestamp'])
        self.assertTrue(all(row['status'] == 'pending' for row in rows))
        mapped = rows[:3]
        self.assertEqual([row['timestamp'] for row in mapped], sorted(row['timestamp'] for row in mapped))
        self.assertEqual(len({row['timestamp'] for row in mapped}), 3)
        self.assertTrue(all(now - 14 * 86400 < row['timestamp'] < now for row in mapped))
        self.assertFalse(rows[3]['date_adjusted'])
        self.assertEqual(rows[3]['timestamp'], now - 86400)
        ids = [row['id'] for row in rows]
        dates = [row['timestamp'] for row in rows]
        imported = self.app.dispatch('/api/import', {'content':content})
        self.assertEqual(imported['added'], 0)
        self.assertEqual(imported['duplicates'], 4)
        refreshed = sorted(self.app.state()['tracks'], key=lambda row:row['original_timestamp'])
        self.assertEqual([row['id'] for row in refreshed], ids)
        self.assertEqual([row['timestamp'] for row in refreshed], dates)

    def test_remapping_persists_and_turning_off_preserves_accepted_receipts(self):
        now = int(time.time())
        self.app.dispatch('/api/import', {'content':'\n'.join(log(timestamp=now - days*86400) for days in [100, 200])})
        self.app.dispatch('/api/preferences', {'remap_outdated':True})
        rows = self.app.state()['tracks']
        self.app.record('alice', rows[:1], 'accepted')
        sent_date = rows[0]['timestamp']
        self.app.db.close()
        self.app = App(self.temp.name)
        self.app.credentials = {'username':'Alice'}
        self.assertTrue(self.app.preferences()['remap_outdated'])
        self.app.dispatch('/api/preferences', {'remap_outdated':False})
        statuses = {row['id']:row for row in self.app.state()['tracks']}
        self.assertEqual(statuses[rows[0]['id']]['status'], 'accepted')
        self.assertEqual(statuses[rows[0]['id']]['timestamp'], sent_date)
        self.assertEqual(statuses[rows[1]['id']]['status'], 'expired')
        self.assertEqual(statuses[rows[1]['id']]['timestamp'], rows[1]['original_timestamp'])

    def test_preferences_do_not_clear_other_rejections_or_uncertain_outcomes(self):
        now = int(time.time())
        self.app.dispatch('/api/import', {'content':'\n'.join(log(timestamp=now - days*86400) for days in [100, 200, 300, 400])})
        rows = self.app.state()['tracks']
        self.app.record('alice', rows[:1], 'ignored', 'Timestamp too old', ignored_code='3')
        self.app.record('alice', rows[1:2], 'ignored', 'Filtered artist', ignored_code='1')
        self.app.record('alice', rows[2:3], 'uncertain')
        self.app.record('alice', rows[3:4], 'accepted')
        self.app.dispatch('/api/preferences', {'remap_outdated':True})
        by_id = {row['id']:row for row in self.app.state()['tracks']}
        self.assertEqual(by_id[rows[0]['id']]['status'], 'pending')
        for index, status in [(1,'ignored'), (2,'uncertain'), (3,'accepted')]:
            self.assertEqual(by_id[rows[index]['id']]['status'], status)
            self.assertFalse(by_id[rows[index]['id']]['date_adjusted'])

    def test_adjusted_submission_must_match_dates_reviewed_in_queue(self):
        self.app.dispatch('/api/import', {'content':log(timestamp=int(time.time())-100*86400)})
        self.app.dispatch('/api/preferences', {'remap_outdated':True})
        row = self.app.state()['tracks'][0]
        request = {'ids':[row['id']], 'account':'Alice', 'confirmed':True}
        with self.assertRaises(AppError):
            self.app.dispatch('/api/submit', request)
        with patch.object(Lastfm, 'call', return_value=response([row])):
            self.app.dispatch('/api/submit', {**request, 'timestamps':{row['id']:row['timestamp']}})
            for _ in range(100):
                if not self.app.state()['job']['running']:
                    break
                time.sleep(.01)
        self.assertEqual(self.app.state()['tracks'][0]['status'], 'accepted')

    def test_legacy_receipts_do_not_adopt_another_accounts_adjusted_dates(self):
        timestamp = int(time.time()) - 100 * 86400
        self.app.dispatch('/api/import', {'content':log(timestamp=timestamp)})
        row = self.app.state()['tracks'][0]
        with self.app.db:
            self.app.db.execute("INSERT INTO outcomes(account,id,status,message,updated) VALUES(?,?,?,?,?)",
                                ('alice', row['id'], 'accepted', '', int(time.time())))
        self.app.credentials = {'username':'Bob'}
        self.app.dispatch('/api/preferences', {'remap_outdated':True})
        self.assertTrue(self.app.state()['tracks'][0]['date_adjusted'])
        self.app.credentials = {'username':'Alice'}
        accepted = self.app.state()['tracks'][0]
        self.assertEqual(accepted['status'], 'accepted')
        self.assertEqual(accepted['timestamp'], timestamp)
        self.assertFalse(accepted['date_adjusted'])

    def test_confirmed_uncertain_retry_gets_an_adjusted_date(self):
        self.app.dispatch('/api/import', {'content':log(timestamp=int(time.time()) - 100 * 86400)})
        row = self.app.state()['tracks'][0]
        self.app.record('alice', [row], 'uncertain')
        self.app.dispatch('/api/preferences', {'remap_outdated':True})
        self.assertFalse(self.app.state()['tracks'][0]['date_adjusted'])
        self.app.dispatch('/api/resolve', {'ids':[row['id']], 'account':'Alice', 'action':'retry', 'confirmed':True})
        retried = self.app.state()['tracks'][0]
        self.assertEqual(retried['status'], 'pending')
        self.assertTrue(retried['date_adjusted'])


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(self.temp.name)
        self.server = Server(self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = self.server.origin
        self.cookie = self.server.cookie_name + '=' + self.server.session_token

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.app.db.close()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        base = {'Cookie':self.cookie}
        if data is not None:
            base.update({'Origin':self.origin,'X-CSRF':self.server.csrf,'Content-Type':'application/json'})
        base.update(headers or {})
        request = urllib.request.Request(self.origin + path, data=None if data is None else json.dumps(data).encode(), headers=base)
        try:
            return urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            return error

    def test_auth_origin_csrf_and_host_guards(self):
        for headers in ({'Cookie':''}, {'Origin':'https://evil.example'}, {'X-CSRF':'wrong'}, {'Host':'evil.example'}):
            with self.request('/api/clear', {}, headers) as reply:
                self.assertEqual(reply.status, 403)
        with self.request('/api/clear', {}) as reply:
            self.assertEqual(reply.status, 200)

    def test_assets_and_no_arbitrary_files(self):
        for path in ['/', '/app.js', '/liquid-glass.js', '/style.css', '/favicon.svg', '/logo-black.png', '/logo-white.png']:
            with self.request(path) as reply:
                self.assertEqual(reply.status, 200)
                self.assertIn("frame-ancestors 'none'", reply.headers['Content-Security-Policy'])
                if path.endswith('.png'):
                    self.assertEqual(reply.headers['Content-Type'], 'image/png')
                    self.assertTrue(reply.read().startswith(b'\x89PNG\r\n\x1a\n'))
        for path in ['/scrobbler.py', '/../../README.md', '/credentials.dpapi']:
            with self.request(path) as reply:
                self.assertEqual(reply.status, 404)

    def test_malformed_request_and_local_import(self):
        with self.request('/api/import', {'content':log(timestamp=int(time.time()) - 1000), 'filename':'test.log'}) as reply:
            self.assertEqual(reply.status, 200)
            self.assertEqual(json.load(reply)['added'], 1)
        with self.request('/api/state') as reply:
            state = json.load(reply)
            self.assertEqual(len(state['tracks']), 1)
            self.assertNotIn('credentials', state)
        with self.request('/api/clear', [], {}) as reply:
            self.assertEqual(reply.status, 400)


if __name__ == '__main__':
    unittest.main()
