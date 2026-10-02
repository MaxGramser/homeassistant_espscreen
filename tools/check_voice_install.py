#!/usr/bin/env python3
"""Check the built voice add-on with empty storage, no network and no host mounts.

Usage: python3 tools/check_voice_install.py --image <built-image>
This runs the packaged server, never paid AI calls or real Home Assistant actions.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def inside():
    import mutagen.mp3  # Packaged dependency for HA-generated MP3 speech.

    data = Path('/data')
    assert not list(data.iterdir()), 'The check requires empty, temporary storage.'
    assert not any(name in os.environ for name in (
        'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY_FILE', 'ANTHROPIC_API_KEY_FILE',
        'SCREEN_VOICE_POC', 'SCREEN_VOICE_ENABLED', 'HA_TOKEN_FILE'))
    translation = json.loads(Path('/app/translations/en.json').read_text())
    assert translation['configuration']['voice_assistant']['name'] == 'Enable voice assistant'
    process = None
    csrf = ''
    env = {**os.environ, 'SUPERVISOR_TOKEN': 'test-only-not-a-token',
           'HA_API': 'http://127.0.0.1:18125/api', 'SCREEN_DEV': '1',
           'SCREEN_DATA': '/data', 'ESPHOME_CONFIG': '/config'}
    # SCREEN_DEV permits this local test client; no voice flag or credentials are supplied.
    # The real packaged entry point, storage, HTTP routes and CSRF guard all run.
    def request(path, method='GET', body=None, expected=200):
        headers = {'X-Screen-CSRF': csrf, 'Content-Type': 'application/json'}
        req = Request('http://127.0.0.1:8099' + path, method=method, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        raw = response.read()
        assert response.status == expected, (path, response.status, raw[:250])
        if response.headers.get_content_type() == 'application/json':
            return json.loads(raw)
        return raw.decode()

    def stop():
        nonlocal process
        if process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
                raise AssertionError('Server did not shut down cleanly.')
            process = None

    def boot():
        nonlocal process, csrf
        stop()
        process = subprocess.Popen([sys.executable, '/app/server.py'], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            assert process.poll() is None, 'Packaged server exited during startup.'
            try:
                request('/health')
                break
            except URLError:
                time.sleep(.05)
        else:
            raise AssertionError('Server did not become healthy.')
        csrf = request('/api/inventory?light=1')['csrf']
        return request('/api/voice-preview/status')

    def options(value):
        (data / 'options.json').write_text(json.dumps({'voice_assistant': value}))

    root = '/api/voice-preview'
    try:
        # Empty installation, no keys or speech engines, and the default switch off.
        state = boot()
        assert not state['enabled'] and not state['configured']
        for route in ('/sessions', '/openai/sessions', '/claude/sessions'):
            request(root + route, 'POST', {}, expected=404)
        request(root + '/config', 'PUT', {'api_key': 'test-only-openai-key-000'}, expected=404)
        assert not list(data.glob('voice-*'))
        page = request('/')
        asset = re.search(r'src="\./(assets/[^\"]+\.js)"', page)
        assert asset, 'Packaged editor is missing.'
        assert 'voice-reply-speaker' in request('/' + asset[1])
        print('PASS empty install: healthy, editor bundled, voice off, endpoints disabled', flush=True)

        options(True)
        assert not request(root + '/status')['enabled'], 'Option applies after restart.'
        state = boot()
        assert state['enabled'] and not state['configured'] and state['provider'] == 'openai'
        assert state['speech_ready'] and state['pipelines'] == []
        assert state['idle_seconds'] == 5 and state['reply_speaker'] == ''
        key = 'test-only-openai-key-000'
        state = request(root + '/config', 'PUT', {'api_key': key})
        assert state['configured'] and key not in json.dumps(state)
        request(root + '/config', 'PUT', {'voice': 'cedar'})
        request(root + '/config', 'PUT', {'idle_seconds': 6})
        request(root + '/config', 'PUT', {'reply_speaker': '', 'reply_volume': 25})
        state = boot()
        assert state['configured'] and state['voice'] == 'cedar'
        assert state['idle_seconds'] == 6 and state['reply_volume'] == 25
        assert (data / 'voice-api-key').stat().st_mode & 0o777 == 0o600
        print('PASS OpenAI: no speech engine required; key and preferences persist privately', flush=True)

        request(root + '/config', 'PUT', {'provider': 'claude'})
        key = 'test-only-claude-key-000'
        state = request(root + '/config/claude', 'PUT', {'api_key': key})
        assert state['key_configured'] and not state['speech_ready'] and not state['configured']
        assert key not in json.dumps(state)
        error = request(root + '/claude/sessions', 'POST', {}, expected=400)
        assert 'speech-to-text and text-to-speech' in error['error']
        state = boot()
        assert state['provider'] == 'claude' and state['key_configured'] and not state['speech_ready']
        assert (data / 'voice-claude-api-key').stat().st_mode & 0o777 == 0o600
        print('PASS Claude: missing HA STT/TTS clearly blocks capture, key survives restart', flush=True)

        retained = {path.name: path.read_bytes() for path in data.glob('voice-*')}
        options(False)
        state = boot()
        assert not state['enabled'] and not state['key_configured']
        request(root + '/config', 'PUT', {'provider': 'openai'}, expected=404)
        for route in ('/sessions', '/openai/sessions', '/claude/sessions'):
            request(root + route, 'POST', {}, expected=404)
        assert retained == {path.name: path.read_bytes() for path in data.glob('voice-*')}
        options(True)
        state = boot()
        assert state['provider'] == 'claude' and state['key_configured'] and state['idle_seconds'] == 6
        state = request(root + '/config', 'PUT', {'provider': 'openai'})
        assert state['configured'] and state['reply_volume'] == 25
        print('PASS disable and re-enable: routes gated, saved settings retained, providers switch', flush=True)
    finally:
        stop()
    print('Clean image check passed. No network, host mounts, real API keys or device actions.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', help='Already-built Screen Manager image')
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        inside()
        return
    if not args.image:
        parser.error('--image is required')
    import yaml
    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / 'screen_manager/config.yaml').read_text())
    assert manifest['options']['voice_assistant'] is False
    assert manifest['schema']['voice_assistant'] == 'bool'
    subprocess.run(['docker', 'run', '--rm', '-i', '--pull=never', '--network=none',
                    '--tmpfs=/data', '--tmpfs=/config', '--entrypoint=python3',
                    args.image, '-', '--inside'], input=Path(__file__).read_bytes(), check=True, timeout=120)


if __name__ == '__main__':
    main()
