"""Small, local bridge to HA's official Assist tools over stateless MCP HTTP.

Explicit on/off of one resolved light or switch, plus light brightness. The
provider retains its existing audio path and never receives HA credentials.
"""
import asyncio
import json
import math
import re
import time

from aiohttp import ClientError, ClientTimeout

MAX_RESPONSE = 256 * 1024
INTENTS = {'turn_on': ('intent__HassTurnOn', 'HassTurnOn'),
           'turn_off': ('intent__HassTurnOff', 'HassTurnOff'),
           'brightness': ('light__HassLightSet', 'HassLightSet')}


def supported_schema(schema, action):
    if not isinstance(schema, dict) or schema.get('type') != 'object':
        return False
    properties = schema.get('properties')
    if not isinstance(properties, dict):
        return False
    name, domain = properties.get('name'), properties.get('domain')
    if (not isinstance(name, dict) or name.get('type') != 'string'
            or not isinstance(domain, dict) or domain.get('type') != 'array'):
        return False
    items = domain.get('items')
    domains = {'light'} if action == 'brightness' else {'light', 'switch'}
    if not isinstance(items, dict) or items.get('type') != 'string':
        return False
    if 'enum' in items and (not isinstance(items['enum'], list)
                           or not all(value in items['enum'] for value in domains)):
        return False
    required = schema.get('required', [])
    arguments = {'name', 'domain'} | ({'brightness'} if action == 'brightness' else set())
    if not isinstance(required, list) or any(not isinstance(value, str) or value not in arguments for value in required):
        return False
    if action == 'brightness':
        brightness = properties.get('brightness')
        if not isinstance(brightness, dict) or brightness.get('type') != 'integer':
            return False
        lower, upper = brightness.get('minimum', 0), brightness.get('maximum', 100)
        if (type(lower) not in (int, float) or type(upper) not in (int, float)
                or not math.isfinite(lower) or not math.isfinite(upper) or lower > 0 or upper < 100):
            return False
    return True


class AssistControls:
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
            for action, names in INTENTS.items():
                matches = [tool for tool in tools if isinstance(tool, dict)
                           and tool.get('name') in names]
                if len(matches) != 1 or not supported_schema(matches[0].get('inputSchema'), action):
                    if action == 'brightness':
                        continue  # Older HA setups can still use light/switch on/off.
                    raise ValueError('Home Assistant Assist must offer on/off tools for lights and switches.')
                selected[action] = matches[0]['name']
            self.tools, self.checked_at = selected, time.monotonic()

    async def control(self, entity_id, action, brightness=None):
        if (not isinstance(entity_id, str) or not re.fullmatch(r'(light|switch)\.[a-z0-9_]+', entity_id)
                or not isinstance(action, str) or action not in INTENTS):
            raise ValueError('Assist control needs one light or switch and a supported action.')
        domain = entity_id.split('.')[0]
        arguments = {'name': entity_id, 'domain': [domain]}
        if action == 'brightness':
            if (domain != 'light' or type(brightness) not in (int, float)
                    or not math.isfinite(brightness) or not 0 <= brightness <= 100):
                raise ValueError('Assist brightness needs one dimmable light and a percentage from 0 to 100.')
            # HA's intent uses whole percentages. Only an explicit zero may
            # turn the light off; a small positive fraction stays at least 1%.
            arguments['brightness'] = 0 if brightness == 0 else max(1, math.floor(brightness + .5))
        elif brightness is not None:
            raise ValueError('Brightness is only valid for a brightness command.')
        await self.check()
        if action not in self.tools:
            raise ValueError('Home Assistant Assist does not offer a compatible brightness tool.')
        result = await self.request('tools/call', {'name': self.tools[action],
            # HA's intent matcher accepts entity ids in the name slot. This
            # keeps Tessera label priority without renaming anything in HA.
            'arguments': arguments})
        contents = result.get('content')
        if (result.get('isError') or not isinstance(contents, list) or len(contents) != 1
                or not isinstance(contents[0], dict)):
            raise ValueError('Home Assistant Assist did not confirm the device command.')
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
            raise ValueError('Home Assistant Assist did not confirm the requested device command.')
        # Acceptance is not proof of the eventual device state. Keep the same
        # small receipt as the direct path, including silent simple completion.
        return {'status': 'accepted', 'entity_id': entity_id, 'action': action}
