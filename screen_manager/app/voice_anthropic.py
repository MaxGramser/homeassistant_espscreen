"""Claude text and search adapters. No HA access or speech processing here."""
from datetime import datetime, timezone
import json

from aiohttp import ClientError, ClientTimeout

import voice_lookup

MESSAGES_URL = 'https://api.anthropic.com/v1/messages'
DEFAULT_MODEL = 'claude-sonnet-4-6'


async def message(http, key, body):
    try:
        async with http.post(MESSAGES_URL, headers={'x-api-key': key, 'anthropic-version': '2023-06-01'},
                json=body, timeout=ClientTimeout(total=60), allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError(f'Claude refused the request (HTTP {response.status}). Check the API key, model access and billing.')
            raw = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                raw.extend(chunk)
                if len(raw) > 1024*1024:
                    raise ValueError('Claude returned an oversized reply.')
            result = json.loads(raw)
            if not isinstance(result, dict) or not isinstance(result.get('content'), list):
                raise ValueError('Claude returned an invalid reply.')
            return result
    except (ClientError, TimeoutError):
        raise ConnectionError('Claude could not be reached. No automatic retry was made.') from None


class ClaudeText:
    id = 'claude'
    default_model = DEFAULT_MODEL

    async def respond(self, http, key, *, model, instructions, tools, messages):
        result = await message(http, key, {'model': model, 'max_tokens': 2048, 'system': instructions,
            'tools': [{'name': t['name'], 'description': t['description'], 'input_schema': t['parameters']} for t in tools],
            'tool_choice': {'type': 'auto', 'disable_parallel_tool_use': True}, 'messages': messages})
        if result.get('stop_reason') not in {'end_turn', 'tool_use'}:
            raise ValueError('Claude did not complete its reply. No incomplete tool calls were executed.')
        content = result['content']
        calls = [{'id': p['id'], 'name': p['name'], 'arguments': p['input']} for p in content if p.get('type') == 'tool_use']
        return {'message': {'role': 'assistant', 'content': content}, 'calls': calls,
                'text': '\n'.join(p['text'] for p in content if p.get('type') == 'text').strip()}

    def tool_results(self, results):
        return {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': call_id,
            'content': json.dumps(result, ensure_ascii=False)} for call_id, result in results]}


class ClaudeLookup:
    id = 'claude'
    default_model = DEFAULT_MODEL

    async def lookup(self, http, key, arguments, *, model):
        query = voice_lookup.question(arguments)
        try:
            result = await message(http, key, {'model': model, 'max_tokens': 2048,
                'system': voice_lookup.INSTRUCTIONS + '\nCurrent time: ' + datetime.now(timezone.utc).isoformat(),
                'messages': [{'role': 'user', 'content': query}],
                'tools': [{'type': 'web_search_20250305', 'name': 'web_search', 'max_uses': 3}],
                'tool_choice': {'type': 'any'}})
            if result.get('stop_reason') != 'end_turn':
                return dict(voice_lookup.UNAVAILABLE)
            texts, sources, searched = [], {}, False
            for part in result['content']:
                if part.get('type') == 'web_search_tool_result' and isinstance(part.get('content'), list):
                    searched = True
                if part.get('type') == 'text':
                    texts.append(part['text'])
                    for citation in part.get('citations', []):
                        if citation.get('type') == 'web_search_result_location':
                            source = voice_lookup.source({**citation, 'type': 'url_citation'})
                            if source:
                                sources[source['url']] = source
            answer = '\n'.join(texts).strip()
            if not searched or not sources or not answer or len(answer) > 12000:
                return dict(voice_lookup.UNAVAILABLE)
            return {'status': 'ok', 'answer': answer, 'sources': list(sources.values()),
                    'retrieved_at': datetime.now(timezone.utc).isoformat()}
        except (ValueError, ConnectionError, KeyError, TypeError):
            return dict(voice_lookup.UNAVAILABLE)
