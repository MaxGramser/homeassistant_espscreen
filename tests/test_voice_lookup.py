"""Public-information lookup contract, using a local fake Responses server."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager/app'))
import voice_lookup as lookup


def response():
    return {'status': 'completed', 'output': [
        {'type': 'web_search_call', 'status': 'completed'},
        {'type': 'message', 'role': 'assistant', 'content': [
            {'type': 'output_text', 'text': 'The forecast is cloudy.', 'annotations': [
                {'type': 'url_citation', 'url': 'https://weather.example/forecast', 'title': 'Forecast'}]}]}]}


class LookupResultTests(unittest.TestCase):
    def test_requires_completed_search_answer_and_citation(self):
        good = response()
        for bad in [None, [], {}, {**good, 'status': 'incomplete'},
                    {**good, 'output': good['output'][1:]},
                    {**good, 'output': good['output'][:1]}]:
            with self.subTest(bad=bad):
                self.assertEqual(lookup.result(bad), lookup.UNAVAILABLE)
        for field, value in [('text', ''), ('text', 'x' * 12001), ('annotations', []), ('annotations', None)]:
            bad = deepcopy(good)
            bad['output'][1]['content'][0][field] = value
            self.assertEqual(lookup.result(bad), lookup.UNAVAILABLE)

    def test_citations_are_deduplicated_and_urls_must_be_public_link_schemes(self):
        data = response()
        annotations = data['output'][1]['content'][0]['annotations']
        annotations.append(deepcopy(annotations[0]))
        for url in ['javascript:alert(1)', 'data:text/html,hello', 'file:///etc/passwd',
                    '//example.com', 'https://user:password@example.com/', 'https://example.com/\n',
                    'https://[invalid', 'https://', 'https://' + 'a' * 2048]:
            annotations.append({'type': 'url_citation', 'url': url})
        annotations += [None, {}, {'type': 'file_citation', 'url': 'https://example.com'}]
        result = lookup.result(data)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['answer'], 'The forecast is cloudy.')
        self.assertEqual(result['sources'], [{'url': 'https://weather.example/forecast', 'title': 'Forecast'}])
        self.assertTrue(result['retrieved_at'].endswith('+00:00'))

    def test_query_rejects_extra_fields_and_invalid_lengths(self):
        for arguments in [None, [], {}, {'query': None}, {'query': ' '}, {'query': 'x' * 801},
                          {'query': 'weather', 'entity_id': 'light.private'}]:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                lookup.question(arguments)
        self.assertEqual(lookup.question({'query': ' weather today '}), 'weather today')


class LookupHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.status, self.data, self.calls = 200, response(), []
        async def handle(request):
            self.calls.append(await request.json())
            self.assertEqual(request.headers['Authorization'], 'Bearer test-only')
            return web.json_response(self.data, status=self.status)
        app = web.Application()
        app.router.add_post('/responses', handle)
        self.server = TestServer(app)
        await self.server.start_server()
        self.url = patch.object(lookup, 'RESPONSES_URL', str(self.server.make_url('/responses')))
        self.url.start()
        self.http = ClientSession()

    async def asyncTearDown(self):
        await self.http.close()
        await self.server.close()
        self.url.stop()

    async def test_search_receives_only_the_question_and_forces_live_search(self):
        result = await lookup.lookup(self.http, 'test-only', {'query': 'Current weather in Amsterdam?'}, model='test-model')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(self.calls), 1)
        body = self.calls[0]
        self.assertEqual(body['input'], 'Current weather in Amsterdam?')
        self.assertEqual(body['model'], 'test-model')
        self.assertFalse(body['store'])
        self.assertEqual(body['tools'], [{'type': 'web_search', 'external_web_access': True}])
        self.assertEqual(body['tool_choice'], 'required')
        self.assertIn('Current time:', body['instructions'])
        self.assertNotIn('context', body)

    async def test_provider_errors_are_unavailable_without_leaking_details(self):
        for status in [400, 401, 429, 500]:
            self.status, self.data = status, {'error': 'provider detail must stay private'}
            self.assertEqual(await lookup.lookup(self.http, 'test-only', {'query': 'Weather?'}), lookup.UNAVAILABLE)
        self.status, self.data = 200, {'unexpected': 'shape'}
        self.assertEqual(await lookup.lookup(self.http, 'test-only', {'query': 'Weather?'}), lookup.UNAVAILABLE)

    async def test_timeout_returns_unavailable(self):
        with patch.object(self.http, 'post', side_effect=TimeoutError):
            self.assertEqual(await lookup.lookup(self.http, 'test-only', {'query': 'Weather?'}), lookup.UNAVAILABLE)


if __name__ == '__main__':
    unittest.main()
