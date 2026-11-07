import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

import trace_export_h as export
import trace_export_labels as labels_cli


PNG = b'\x89PNG\r\n\x1a\nsynthetic-test-bytes'


class FakeClient:
    def __init__(self, *, missing=False, truncated=False, changing=False):
        self.calls = []
        self.missing = missing
        self.changing = changing
        self.events = [
            {'type': 'AgentEvent', 'timestamp': '2026-11-07T19:00:00Z', 'data': {
                'kind': 'observation_event', 'image': {'type': 'base64', 'media_type': 'image/png',
                    'source': base64.b64encode(PNG).decode()}}},
            {'type': 'AgentEvent', 'timestamp': '2026-11-07T19:00:01Z', 'data': {
                'kind': 'policy_event', 'tool_reqs': [{'id': 'call-1', 'tool_name': 'type_text',
                    'args': {'text': 'x' * 400}}]}},
            {'type': 'AgentEvent', 'timestamp': '2026-11-07T19:00:02Z', 'data': {
                'kind': 'tool_result', 'tool_req': 'call-1', 'result': 'typed', 'truncated': truncated}},
        ]

    def get_json(self, sid, suffix=''):
        self.calls.append(suffix)
        if not suffix:
            result = {'id': sid, 'latest_answer': 'synthetic'}
        elif suffix == '/status':
            result = {'status': 'completed', 'usage_per_model': [{'name': 'holo4-27b', 'input_tokens': 100}]}
        elif 'page=1&' in suffix:
            result = {'items': self.events[:2], 'page': 1, 'total': 3}
        else:
            result = {'items': self.events[2:], 'page': 2, 'total': 4 if self.changing else 3}
        return result, json.dumps(result).encode()

    def image(self, sid, value):
        if self.missing:
            raise RuntimeError('signed-secret-must-not-leak')
        return PNG


class ExportTests(unittest.TestCase):
    def test_two_pages_archive_exact_tool_arguments_images_and_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = export.archive_session(FakeClient(), 'session-123', root, size=2)
            self.assertTrue(result['archive_complete'])
            self.assertFalse(result['ready_for_sft'])
            self.assertEqual(result['event_count'], 3)
            events = [json.loads(line) for line in (root/'session-123/events.jsonl').read_text().splitlines()]
            self.assertEqual(events[1]['data']['tool_reqs'][0]['args']['text'], 'x' * 400)
            self.assertEqual((root/'session-123'/result['images'][0]['path']).read_bytes(), PNG)
            self.assertEqual(len(list((root/'session-123/pages').glob('*.json'))), 2)
            self.assertIn('status-after.json', result['files'])

    def test_missing_image_is_partial_and_error_does_not_leak_signed_url(self):
        with tempfile.TemporaryDirectory() as directory:
            result = export.archive_session(FakeClient(missing=True), 'session-123', Path(directory), size=2)
            self.assertFalse(result['archive_complete'])
            self.assertIn('image_not_archived', [item['kind'] for item in result['issues']])
            self.assertNotIn('signed-secret', json.dumps(result))

    def test_upstream_truncation_is_explicitly_not_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            result = export.archive_session(FakeClient(truncated=True), 'session-123', Path(directory), size=2)
            self.assertFalse(result['archive_complete'])
            self.assertIn('upstream_truncation', [item['kind'] for item in result['issues']])

    def test_pagination_changing_total_preserves_partial_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = export.archive_session(FakeClient(changing=True), 'session-123', root, size=2)
            self.assertFalse(result['archive_complete'])
            self.assertTrue((root/'session-123/manifest.json').exists())
            self.assertIn('export_failed', [item['kind'] for item in result['issues']])

    def test_auth_is_stripped_for_s3_redirect(self):
        class RedirectOpener:
            def __init__(self): self.requests = []
            def open(self, req, timeout):
                self.requests.append(req)
                if len(self.requests) == 1:
                    raise HTTPError(req.full_url, 302, 'redirect', {'Location': 'https://bucket.s3.eu-west-1.amazonaws.com/image.png?signature=secret'}, None)
                return BytesIO(PNG)
        for route in ['/api/v2/sessions/s1', '/api/v1/trajectories/s1']:
            with self.subTest(route=route):
                client = export.CloudClient('test-key-not-real')
                client.opener = RedirectOpener()
                image = {'type': 'url', 'source': route + '/resources/screenshots/s1/a.png'}
                self.assertEqual(client.image('s1', image), PNG)
                first, second = client.opener.requests
                self.assertEqual(first.get_header('Authorization'), 'Bearer test-key-not-real')
                self.assertIsNone(second.get_header('Authorization'))

    def test_legacy_image_urls_from_v2_events_are_archived(self):
        class ImageOpener:
            def __init__(self): self.requests = []
            def open(self, req, timeout):
                self.requests.append(req)
                return BytesIO(PNG)
        client = FakeClient()
        cloud = export.CloudClient('test-key-not-real')
        cloud.opener = ImageOpener()
        client.image = cloud.image
        client.events[0]['data']['image'] = {
            'type': 'url', 'media_type': 'image/png',
            'source': 'https://agp.eu.hcompany.ai/api/v1/trajectories/session-123/resources/screenshots/session-123/a.png',
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = export.archive_session(client, 'session-123', root, size=2)
            self.assertTrue(result['archive_complete'])
            self.assertEqual(len(result['images']), 1)
            self.assertEqual((root/'session-123'/result['images'][0]['path']).read_bytes(), PNG)
            self.assertEqual(len(cloud.opener.requests), 1)

    def test_legacy_route_is_allowed_only_for_own_session_resources(self):
        for url in [
            '/api/v1/trajectories/other/resources/screenshots/a.png',
            '/api/v1/trajectories/s1-other/resources/screenshots/a.png',
            '/api/v1/trajectories/s1/status',
            '/api/v1/trajectories/s1/resources/screenshots/%2e%2e/a.png',
            'https://evil.example/api/v1/trajectories/s1/resources/screenshots/a.png',
        ]:
            with self.subTest(url=url), self.assertRaises(export.ExportError):
                export.checked_url(url, 's1')
        with self.assertRaises(export.ExportError):
            export.checked_url('/api/v1/trajectories/s1/resources/screenshots/a.png', 's1', api=True)

    def test_rejects_foreign_urls_traversal_and_simulated_ids(self):
        for url in ['http://agp.eu.hcompany.ai/api/v2/sessions/s1/resources/a/b',
                    'https://localhost/a', 'https://evil.example/a',
                    'https://agp.eu.hcompany.ai/api/v2/sessions/other/resources/a/b',
                    'https://agp.eu.hcompany.ai/api/v2/sessions/s1/status',
                    'https://agp.eu.hcompany.ai/api/v2/sessions/s1/resources/a/%2e%2e/b',
                    'https://secret@bucket.s3.amazonaws.com/image.png']:
            with self.subTest(url=url), self.assertRaises(export.ExportError):
                export.checked_url(url, 's1')
        with tempfile.TemporaryDirectory() as directory:
            for sid in ['../private', 'sim_123']:
                with self.assertRaises(export.ExportError):
                    export.archive_session(FakeClient(), sid, Path(directory))

    def test_refuses_git_output_and_existing_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'.git').mkdir()
            with self.assertRaises(export.ExportError):
                export.private_destination(root/'traces')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(export.ExportError):
                export.private_destination(Path(directory))

    def test_feedback_keeps_objective_unknown_and_does_not_enable_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'export.json').write_text('{}')
            (root/'labels.json').write_text(json.dumps({'simulated': False, 'objective_success': None,
                'allow_training': False, 'include_for_training': False}))
            labels_cli.main(['--archive', directory, '--task-success-user', 'partial', '--useful', 'yes',
                             '--comment', 'Utile mais incomplet', '--correction', 'Le stock prévu a été confondu avec le stock réel'])
            labels = json.loads((root/'labels.json').read_text())
            self.assertEqual(labels['task_success_user'], 'partial')
            self.assertTrue(labels['useful'])
            self.assertIsNone(labels['objective_success'])
            self.assertFalse(labels['allow_training'])
            self.assertFalse(labels['include_for_training'])

    def test_objective_feedback_requires_independent_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'export.json').write_text('{}')
            (root/'labels.json').write_text('{}')
            with self.assertRaises(SystemExit):
                labels_cli.main(['--archive', directory, '--task-success-user', 'success', '--useful', 'yes',
                                 '--objective-success', 'yes'])
            labels_cli.main(['--archive', directory, '--task-success-user', 'success', '--useful', 'yes',
                             '--objective-success', 'yes', '--objective-evidence', 'checks/odoo-state.json',
                             '--allow-training', 'yes', '--reviewed'])
            labels = json.loads((root/'labels.json').read_text())
            self.assertTrue(labels['objective_success'])
            self.assertTrue(labels['allow_training'])
            self.assertTrue(labels['reviewed'])
            self.assertFalse(labels['include_for_training'])


if __name__ == '__main__':
    unittest.main()
