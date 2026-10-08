"""Small, local bridge to HA's official Assist tools over stateless MCP HTTP.

Only explicit on/off of one resolved light is enabled in this experiment. The
provider retains its existing audio path and never receives HA credentials.
"""
import asyncio
import json
import re
import time

from aiohttp import ClientError, ClientTimeout

MAX_RESPONSE = 256 * 1024
INTENTS = {'turn_on': 'HassTurnOn', 'turn_off': 'HassTurnOff'}


class AssistLights:
    def __init__(self, ha):
        self.ha = ha
        self.tools = {}
        self.checked_at = 0
        self.lock = asyncio.Lock()
        self.sequence = 0

    async def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        # Use the specific built-in Assist API, never an arbitrary configured
        # MCP API. HA's installed integration owns exposure and intent handling.
        try:
            async with self.ha.session.post(self.ha.base + '/mcp/assist',
                    headers={'Authorization': 'Bearer ' + self.ha.token,
                             'Accept': 'application/json, text/event-stream'},
                    json={'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params},
                    allow_redirects=False, timeout=ClientTimeout(total=10)) as response:
                if response.status != 200:
                    raise ConnectionError('Home Assistant Assist is unavailable. Set up its Model Context Protocol Server integration with Assist access.')
                body = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE:
                        raise ValueError('Home Assistant Assist returned too much data.')
                result = json.loads(body)
        except (ClientError, TimeoutError):
            # A timed out command may already have run. Never retry or fall back
            # to a direct HA service, and never log URLs, tokens or response text.
            raise ConnectionError('Home Assistant Assist did not confirm the request.') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError('Home Assistant Assist returned an invalid response.') from None
        if (not isinstance(result, dict) or result.get('jsonrpc') != '2.0'
                or result.get('id') != request_id or 'error' in result
                or not isinstance(result.get('result'), dict)):
            raise ValueError('Home Assistant Assist did not confirm the request.')
        return result['result']

    async def check(self, *, force=False):
        async with self.lock:
            if not force and self.tools and time.monotonic() - self.checked_at < 60:
                return
            result = await self.request('tools/list', {})
            tools = result.get('tools')
            if not isinstance(tools, list):
                raise ValueError('Home Assistant Assist did not list its tools.')
            selected = {}
            for action, intent in INTENTS.items():
                matches = [tool for tool in tools if isinstance(tool, dict)
                           and tool.get('name') in (intent, 'intent__' + intent)]
                if len(matches) != 1:
                    raise ValueError('Home Assistant Assist must offer both light on and off tools.')
                schema = matches[0].get('inputSchema') or {}
                if not isinstance(schema, dict):
                    raise ValueError('Home Assistant Assist has an unsupported light tool schema.')
                properties = schema.get('properties') or {}
                if (not isinstance(properties, dict)
                        or not isinstance(properties.get('name'), dict)
                        or not isinstance(properties.get('domain'), dict)
                        or properties.get('name', {}).get('type') != 'string'
                        or properties.get('domain', {}).get('type') != 'array'):
                    raise ValueError('Home Assistant Assist has an unsupported light tool schema.')
                selected[action] = matches[0]['name']
            self.tools, self.checked_at = selected, time.monotonic()

    async def set_light(self, entity_id, action):
        if not isinstance(entity_id, str) or not re.fullmatch(r'light\.[a-z0-9_]+', entity_id) or action not in INTENTS:
            raise ValueError('Assist light control needs one light and an explicit on/off action.')
        await self.check()
        result = await self.request('tools/call', {'name': self.tools[action],
            # HA's intent matcher accepts entity ids in the name slot. This
            # keeps Tessera label priority without renaming anything in HA.
            'arguments': {'name': entity_id, 'domain': ['light']}})
        contents = result.get('content')
        if (result.get('isError') or not isinstance(contents, list) or len(contents) != 1
                or not isinstance(contents[0], dict)):
            raise ValueError('Home Assistant Assist did not confirm the light command.')
        try:
            receipt = json.loads(contents[0]['text']) if contents[0].get('type') == 'text' else None
        except (KeyError, TypeError, json.JSONDecodeError):
            receipt = None
        if not isinstance(receipt, dict):
            raise ValueError('Home Assistant Assist returned an invalid action receipt.')
        data = receipt.get('data') or {}
        if not isinstance(data, dict):
            raise ValueError('Home Assistant Assist returned an invalid action receipt.')
        success = data.get('success') or []
        if (receipt.get('response_type') != 'action_done' or data.get('failed')
                or not isinstance(success, list) or not success
                or any(not isinstance(target, dict) or target.get('type') != 'entity'
                                     or target.get('id') != entity_id for target in success)):
            raise ValueError('Home Assistant Assist did not confirm the requested light command.')
        # Acceptance is not proof of the eventual device state. Keep the same
        # small receipt as the direct path, including silent simple completion.
        return {'status': 'accepted', 'entity_id': entity_id, 'action': action}
