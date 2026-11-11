import datetime as dt
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import model
import providers
import credentials
import google_oauth
import sessione


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old = model.ENTRIES
        model.ENTRIES = self.root / 'entries.json'

    def tearDown(self):
        model.ENTRIES = self.old
        self.tmp.cleanup()

    def test_timer_and_check_are_separate_and_persist(self):
        t0 = dt.datetime(2026, 1, 2, 23, 50, tzinfo=dt.timezone.utc)
        t1 = dt.datetime(2026, 1, 3, 0, 10, tzinfo=dt.timezone.utc)
        with patch.object(model, 'now', side_effect=[t0, t1]):
            model.toggle_timer('timer')
            self.assertTrue(model.active('timer'))
            model.toggle_timer('timer')
        self.assertEqual(model.values('timer'), {'2026-01-02': 600, '2026-01-03': 600})
        day = dt.date(2026, 1, 3)
        model.toggle_check('check', day)
        self.assertEqual(model.values('check'), {'2026-01-03': 1})
        model.toggle_check('check', day)
        self.assertEqual(model.values('check'), {})
        self.assertEqual(sum(model.values('timer').values()), 1200)

    def test_new_goal_validation(self):
        self.assertEqual(model.new_goal('Lettura', 'timer', 60)['weekly_target'], 60)
        with self.assertRaises(ValueError): model.new_goal('', 'timer', 60)

    def test_center_action_respects_selected_goal_type(self):
        cfg = model.config()
        cfg['goals'].extend([
            {'id': 'a', 'name': 'Corsa', 'kind': 'timer', 'weekly_target': 60},
            {'id': 'b', 'name': 'Lettura', 'kind': 'check', 'weekly_target': 4},
        ])
        cfg['selected'] = 'a'
        with patch.object(model, 'config', return_value=cfg), \
             patch.object(model, 'toggle_timer') as timer, patch.object(model, 'toggle_check') as check:
            self.assertEqual(model.activate_selected(), 'a')
            timer.assert_called_once_with('a')
            check.assert_not_called()
            cfg['selected'] = 'b'
            self.assertEqual(model.activate_selected(), 'b')
            check.assert_called_once_with('b')

    def test_concurrent_goal_updates_do_not_lose_either_entry(self):
        script = ("import os, pathlib, sys; "
                  "sys.path.insert(0, os.environ['TEST_WIDGET_DIR']); import model; "
                  "model.ENTRIES=pathlib.Path(os.environ['TEST_ENTRIES']); "
                  "model.toggle_check(os.environ['TEST_GOAL'])")
        base = dict(os.environ, TEST_WIDGET_DIR=str(Path(__file__).parent), TEST_ENTRIES=str(model.ENTRIES))
        procs = [subprocess.Popen([sys.executable, '-c', script], env=dict(base, TEST_GOAL=goal))
                 for goal in ('first', 'second')]
        for proc in procs:
            self.assertEqual(proc.wait(timeout=10), 0)
        data = model.read(model.ENTRIES, {})
        self.assertEqual(set(data['goals']), {'first', 'second'})

    def test_training_timer_commands_record_once_with_lock(self):
        state, sessions = self.root/'active.json', self.root/'sessions.json'
        times = iter([dt.datetime(2026, 1, 2, 10, 0, tzinfo=dt.timezone.utc),
                      dt.datetime(2026, 1, 2, 10, 10, tzinfo=dt.timezone.utc)])
        with patch.object(sessione, 'STATE', state), patch.object(sessione, 'SESSIONS', sessions), \
             patch.object(sessione, 'now', side_effect=lambda: next(times)):
            with patch.object(sys, 'argv', ['sessione.py', 'inizia']): sessione.main()
            with patch.object(sys, 'argv', ['sessione.py', 'fine']): sessione.main()
        self.assertFalse(state.exists())
        records = model.read(sessions, {})['sessions']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['daily_seconds'], {'2026-01-02': 600})

    def test_dpapi_roundtrip(self):
        sample = b'isolated-test-secret'
        encrypted = credentials.transform(sample, True)
        self.assertNotEqual(encrypted, sample)
        self.assertEqual(credentials.transform(encrypted, False), sample)

    def test_google_oauth_client_endpoint_restrictions(self):
        client = {'installed': {'client_id':'example.apps.googleusercontent.com', 'client_secret':'example',
                                'auth_uri':'https://accounts.google.com/o/oauth2/auth',
                                'token_uri':'https://oauth2.googleapis.com/token'}}
        self.assertIs(google_oauth.validate_client(client), client)
        client['installed']['token_uri'] = 'https://example.com/collect'
        with self.assertRaises(ValueError): google_oauth.validate_client(client)

    def test_google_expired_credentials_are_refreshed_and_protected(self):
        from unittest.mock import MagicMock
        from google.oauth2.credentials import Credentials
        value = MagicMock()
        value.valid = False
        value.token = 'sample-access'
        value.to_json.return_value = '{"refresh_token":"sample"}'
        with patch.object(credentials, 'get', return_value='{}'), \
             patch.object(credentials, 'put') as save, \
             patch.object(Credentials, 'from_authorized_user_info', return_value=value):
            self.assertEqual(google_oauth.access_token(), 'sample-access')
        value.refresh.assert_called_once()
        save.assert_called_once_with('google_oauth', '{"refresh_token":"sample"}')

    def test_google_connect_uses_loopback_pkce_and_readonly_scope(self):
        import json
        from unittest.mock import MagicMock
        from google_auth_oauthlib.flow import InstalledAppFlow
        client = {'installed': {'client_id': 'example.apps.googleusercontent.com', 'client_secret': 'example',
                                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                                'token_uri': 'https://oauth2.googleapis.com/token'}}
        path = self.root / 'desktop-client.json'
        path.write_text(json.dumps(client), encoding='utf-8')
        flow, token = MagicMock(), MagicMock()
        token.refresh_token, token.token = 'test-refresh', 'test-access'
        token.to_json.return_value = '{"refresh_token":"test-refresh"}'
        flow.run_local_server.return_value = token
        with patch.object(InstalledAppFlow, 'from_client_config', return_value=flow) as factory, \
             patch.object(credentials, 'put') as save:
            self.assertEqual(google_oauth.connect(path), 'test-access')
        self.assertEqual(factory.call_args.kwargs['scopes'], [google_oauth.SCOPE])
        self.assertTrue(factory.call_args.kwargs['autogenerate_code_verifier'])
        self.assertEqual(flow.run_local_server.call_args.kwargs['bind_addr'], '127.0.0.1')
        self.assertEqual(flow.run_local_server.call_args.kwargs['port'], 0)
        save.assert_called_once_with('google_oauth', '{"refresh_token":"test-refresh"}')


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old = model.HERE
        model.HERE = self.root

    def tearDown(self):
        model.HERE = self.old
        self.tmp.cleanup()

    def test_github_parser(self):
        parser = providers.CalendarParser()
        parser.feed('<td data-date="2026-01-02" data-level="3"></td><td data-date="bad" data-level="4"></td>')
        self.assertEqual(parser.days, {'2026-01-02': 3})

    def test_calendar_pagination_and_only_aggregate(self):
        responses = [
            {'items': [{'start': {'date': '2026-01-03'}, 'summary': 'private title'}], 'nextPageToken': 'next'},
            {'items': [{'start': {'date': '2026-01-03'}}, {'status': 'cancelled', 'start': {'date': '2026-01-04'}}]},
        ]
        with patch.object(providers, 'request_json', side_effect=responses) as request:
            result = providers.external_fetch('google', 'test-secret', year=2026)
        self.assertEqual(result['counts'], {'2026-01-03': 2})
        self.assertIn('pageToken=next', request.call_args_list[1].args[1])
        cache = (self.root/'cache-google.json').read_text(encoding='utf-8')
        self.assertNotIn('private title', cache)
        self.assertNotIn('test-secret', cache)

    def test_todoist_quarters_and_pagination(self):
        seen = []
        def fake(service, url, token, body=None):
            seen.append(url)
            return {'items': [{'completed_at': '2026-01-05T12:00:00+01:00'}] if len(seen) == 1 else []}
        with patch.object(providers, 'request_json', side_effect=fake):
            result = providers.external_fetch('todoist', 'secret', year=2026)
        self.assertEqual(len(seen), 4)
        self.assertEqual(result['counts'], {'2026-01-05': 1})

    def test_outlook_pagination(self):
        pages = [{'value': [{'start': {'dateTime': '2026-02-01T10:00:00'}}], '@odata.nextLink': 'https://graph.microsoft.com/next'},
                 {'value': [{'start': {'dateTime': '2026-02-02T10:00:00'}}]}]
        with patch.object(providers, 'request_json', side_effect=pages):
            result = providers.external_fetch('outlook', 'secret', year=2026)
        self.assertEqual(result['counts'], {'2026-02-01': 1, '2026-02-02': 1})

    def test_strava_and_notion(self):
        with patch.object(providers, 'request_json', return_value=[{'start_date_local':'2026-03-04T09:00:00Z'}]):
            self.assertEqual(providers.external_fetch('strava','secret',year=2026)['counts'], {'2026-03-04':1})
        page={'results':[{'properties':{'Done':{'type':'date','date':{'start':'2026-03-05'}}}}], 'next_cursor':None}
        with patch.object(providers, 'request_json', return_value=page):
            self.assertEqual(providers.external_fetch('notion','secret',{'data_source_id':'a'*32,'date_property':'Done'},2026)['counts'], {'2026-03-05':1})

    def test_reject_external_url_before_sending_token(self):
        with self.assertRaises(ValueError):
            providers.request_json('outlook', 'https://example.com/steal', 'secret')

    def test_failure_preserves_previous_cache(self):
        cache = self.root / 'cache-google.json'
        cache.write_text('{"year":2026,"counts":{"2026-01-01":3}}', encoding='utf-8')
        before = cache.read_bytes()
        with patch.object(providers, 'request_json', side_effect=ValueError('authorization failed')):
            with self.assertRaises(ValueError):
                providers.external_fetch('google', 'test-secret', year=2026)
        self.assertEqual(cache.read_bytes(), before)

    def test_incomplete_provider_payload_preserves_previous_cache(self):
        for service, payload, options in [
            ('google', {}, {}),
            ('outlook', {}, {}),
            ('todoist', {}, {}),
            ('notion', {'results': [], 'has_more': True, 'next_cursor': None},
             {'data_source_id': 'a'*32, 'date_property': 'Date'}),
        ]:
            cache = self.root / f'cache-{service}.json'
            cache.write_text('{"year":2026,"counts":{"2026-01-01":3}}', encoding='utf-8')
            before = cache.read_bytes()
            with self.subTest(service=service), patch.object(providers, 'request_json', return_value=payload):
                with self.assertRaises(ValueError):
                    providers.external_fetch(service, 'test-secret', options, year=2026)
                self.assertEqual(cache.read_bytes(), before)

    def test_notion_wrong_property_does_not_look_like_no_activity(self):
        page = {'results': [{'object': 'page', 'properties': {'Other': {'type': 'date'}}}]}
        with patch.object(providers, 'request_json', return_value=page):
            with self.assertRaisesRegex(ValueError, 'non trovata'):
                providers.external_fetch('notion', 'secret',
                                         {'data_source_id': 'a'*32, 'date_property': 'Date'}, year=2026)

    def test_cache_is_tied_to_calendar_and_connection(self):
        first = {'calendar_id': 'primary', 'connection_id': 'account-a'}
        response = {'items': [{'start': {'date': '2026-04-01'}}]}
        with patch.object(providers, 'request_json', return_value=response):
            providers.external_fetch('google', 'secret', first, year=2026)
        self.assertIsNotNone(providers.external_cached('google', 2026, first))
        self.assertIsNone(providers.external_cached('google', 2026,
                                                   {'calendar_id': 'other', 'connection_id': 'account-a'}))
        self.assertIsNone(providers.external_cached('google', 2026,
                                                   {'calendar_id': 'primary', 'connection_id': 'account-b'}))
        raw = (self.root / 'cache-google.json').read_text(encoding='utf-8')
        self.assertNotIn('account-a', raw)


class RenderTests(unittest.TestCase):
    def test_year_source_and_appearance_change_render_without_merging_sources(self):
        desktop = runpy.run_path(str(Path(__file__).with_name('desktop.pyw')))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replacements = {'CONFIG': root/'config.json', 'ENTRIES': root/'entries.json',
                            'TRAINING': root/'training.json', 'TRAINING_SESSIONS': root/'sessions.json',
                            'TRAINING_ACTIVE': root/'active.json'}
            with patch.multiple(model, **replacements), patch.object(providers, 'CACHE', root/'github.json'):
                model.save(model.TRAINING, {'days': {'2026-01-05': 60}})
                cfg = model.config()
                cfg['github'] = {'enabled': True, 'username': 'Example', 'year_mode': 'personal'}
                model.save(model.CONFIG, cfg)
                model.save(providers.CACHE, {'username': 'Example', 'year': 2026,
                                             'levels': {'2026-01-05': 0, '2026-01-06': 4}})
                day = dt.date(2026, 1, 6)
                personal = desktop['create_image'](day)
                cfg['github']['year_mode'] = 'github'
                model.save(model.CONFIG, cfg)
                external = desktop['create_image'](day)
                self.assertEqual(personal.size, (2650, 450))
                self.assertNotEqual(personal.tobytes(), external.tobytes())
                # La griglia del mese resta personale anche quando cambia quella annuale.
                self.assertEqual(personal.crop((400, 105, 675, 350)).tobytes(),
                                 external.crop((400, 105, 675, 350)).tobytes())
                cfg['appearance']['scale_percent'] = 50
                cfg['appearance']['opacity_percent'] = 50
                model.save(model.CONFIG, cfg)
                small = desktop['create_image'](day)
                self.assertEqual(small.size, (1325, 225))
                self.assertLess(small.getchannel('A').getextrema()[1], 100)

    def test_strava_local_date_does_not_shift_at_midnight(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(model, 'HERE', Path(directory)):
            with patch.object(providers, 'request_json', return_value=[{'start_date_local': '2026-03-04T23:50:00Z'}]):
                result = providers.external_fetch('strava', 'secret', year=2026)
        self.assertEqual(result['counts'], {'2026-03-04': 1})


if __name__ == '__main__':
    unittest.main()
