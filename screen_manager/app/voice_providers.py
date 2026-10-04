"""Provider contracts. Native audio and public lookup can evolve independently.

Native audio and text providers have different transports behind shared tools.
HA exposure, name resolution and actions belong in assistant_tools, never here.
"""
import contextlib
import json
import re
from typing import Protocol

from aiohttp import ClientError, ClientTimeout, FormData

import voice_lookup
from voice_anthropic import ClaudeText, ClaudeLookup

CALLS_URL = 'https://api.openai.com/v1/realtime/calls'


class AudioSession(Protocol):
    async def connect(self, sdp: str, *, model: str, voice: str, instructions: str, tools: list) -> str: ...
    async def close(self) -> None: ...


class AudioProvider(Protocol):
    id: str
    label: str
    default_model: str
    voices: tuple[str, ...]

    def session(self, http, key: str) -> AudioSession: ...


class LookupProvider(Protocol):
    id: str
    default_model: str

    async def lookup(self, http, key: str, arguments: dict, *, model: str) -> dict: ...


class TextProvider(Protocol):
    id: str
    default_model: str

    async def respond(self, http, key: str, *, model: str, instructions: str, tools: list, messages: list) -> dict: ...
    def tool_results(self, results: list) -> dict: ...


class OpenAIAudioSession:
    def __init__(self, http, key):
        self.http, self.key, self.call = http, key, ''

    async def connect(self, sdp, *, model, voice, instructions, tools):
        form = FormData()
        form.add_field('sdp', sdp, content_type='application/sdp')
        form.add_field('session', json.dumps({'type': 'realtime', 'model': model,
            'instructions': instructions, 'tools': [{'type': 'function', **tool} for tool in tools],
            'tool_choice': 'auto', 'max_output_tokens': 1024,
            'audio': {'input': {'turn_detection': {'type': 'semantic_vad'}}, 'output': {'voice': voice}}}), content_type='application/json')
        try:
            async with self.http.post(CALLS_URL, headers={'Authorization': 'Bearer ' + self.key}, data=form,
                                      timeout=ClientTimeout(total=30)) as response:
                if response.status not in (200, 201):
                    raise ValueError(f'OpenAI refused the voice session (HTTP {response.status}). Check the API key, model access and billing.')
                call = response.headers.get('Location', '').rsplit('/', 1)[-1]
                if not re.fullmatch(r'rtc_[a-zA-Z0-9_-]+', call):
                    raise ValueError('OpenAI returned no voice call identifier.')
                self.call = call
                return await response.text()
        except (ClientError, TimeoutError):
            raise ConnectionError('OpenAI voice could not be reached.') from None

    async def close(self):
        call, self.call = self.call, ''
        if call:
            with contextlib.suppress(ClientError, TimeoutError):
                async with self.http.post(f'{CALLS_URL}/{call}/hangup', headers={'Authorization': 'Bearer ' + self.key},
                                          timeout=ClientTimeout(total=5)) as response:
                    await response.read()


class OpenAIAudio:
    id = 'openai'
    label = 'OpenAI'
    default_model = 'gpt-realtime-2.1'
    voices = ('marin', 'cedar', 'alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse')

    def session(self, http, key):
        return OpenAIAudioSession(http, key)


class OpenAILookup:
    id = 'openai'
    default_model = voice_lookup.DEFAULT_MODEL

    async def lookup(self, http, key, arguments, *, model):
        return await voice_lookup.lookup(http, key, arguments, model=model)


AUDIO_PROVIDERS: dict[str, AudioProvider] = {'openai': OpenAIAudio()}
LOOKUP_PROVIDERS: dict[str, LookupProvider] = {'openai': OpenAILookup(), 'claude': ClaudeLookup()}
TEXT_PROVIDERS: dict[str, TextProvider] = {'claude': ClaudeText()}
