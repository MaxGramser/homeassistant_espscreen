"""The audio owner's wiring (components/smart_display/audio_owner.h; docs/PLATFORM_PLAN.md 3.4).

The owner's behaviour and its ranking are tests/test_audio_owner.cpp. A live camera's sound, what it lets into its
buffer, how it reaches the speaker and what it claims and gives back, is live_view.h's SoundPart, SoundPump and
SoundClaim, which tests/test_live_sound.cpp drives with an owner of its own, and the role a full view claims in
(live_view::view_role: a ring's view the ring's, a call's the call's), which it proves too. Here: the rules over the files that claim,
and what only a screen can show."""
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'components' / 'smart_display'
LIVE = COMPONENT / 'live_view.cpp'


class _Loader(yaml.SafeLoader):
    """ESPHome's own tags (!include, !lambda, !secret) read as plain values: the structure is what is checked."""


_Loader.add_multi_constructor('!', lambda loader, suffix, node: loader.construct_scalar(node)
                              if isinstance(node, yaml.ScalarNode) else None)


def claimants():
    """Every file of the core that claims the speaker or the microphone itself, with the code that does."""
    for path in sorted(COMPONENT.glob('*.[hc]*')) + sorted((ROOT / 'packages').rglob('*.yaml')):
        text = path.read_text()
        if 'audio_owner::' in text:
            yield path, text


class Claims(unittest.TestCase):
    def test_every_role_a_file_claims_it_also_releases(self):
        # A claim never given back keeps the speaker from every lower role for good: the music would never play again.
        named = 0
        for path, text in claimants():
            for role in set(re.findall(r'\.role\s*=\s*audio_owner::Role::(\w+)', text)):
                named += 1
                self.assertRegex(text, r'release\([^;]*audio_owner::Role::' + role + r'\b',
                                 f'{path.relative_to(ROOT)} claims as {role} and must release as {role} too, '
                                 'with the claim\'s own id, when what claimed ends')
        self.assertGreaterEqual(named, 3, 'the media player, the doorbell and the call claim in a role of their own')

    def test_a_streams_sound_goes_through_the_tested_rules(self):
        # live_view.cpp's task, main loop and open() reach the sound buffer, the speaker and the owner only through
        # live_view.h's rules, which tests/test_live_sound.cpp proves.
        live = LIVE.read_text()
        self.assertEqual(live.count('xStreamBufferSend('), 1, 'one place, the stream\'s task, writes the sound buffer')
        for rule, what in (('sound_part(', 'the task lets a part in through sound_part (whole samples, none while held back)'),
                           ('pump.tick(', 'speak() hands the buffer to the speaker through SoundPump::tick'),
                           ('sound_on(', 'the main loop plays only while sound_on (not stopping, muted or yielded)'),
                           ('owned.claim(', 'open() claims through SoundClaim'),
                           ('owned.release(', 'the tick that frees a stream releases through SoundClaim')):
            self.assertTrue(rule in live, what)
        self.assertFalse('audio_owner::the().claim(' in live, 'live_view.cpp claims only through SoundClaim')
        self.assertFalse('audio_owner::the().release(' in live, 'live_view.cpp releases only through SoundClaim')
        self.assertEqual(live.count('speaker->play('), 1, 'the speaker is fed in one place, speak()\'s Out for SoundPump')

    def test_a_view_opened_without_a_role_is_a_cameras_sound(self):
        # Every declaration of live_view::open, the streams' and the stub of a board without them, takes the same
        # default: a caller that names no role opens a camera someone looks at.
        header = (COMPONENT / 'live_view.h').read_text()
        declared = re.findall(r'Handle open\(([^)]*)\)\s*[;{]', header)
        self.assertEqual(len(declared), 2, 'live_view.h declares open twice: with USE_LIVE_VIEW and the stub without')
        for parameters in declared:
            role = re.search(r'audio_owner::Role(?: \w+)?\s*=\s*([\w:]+)', parameters)
            self.assertTrue(role and role.group(1) == 'audio_owner::Role::CAMERA_SOUND',
                            'live_view::open\'s role defaults to CAMERA_SOUND, in both its declarations')



class Music(unittest.TestCase):
    # glass: with music playing on a board with a speaker, a camera opened full screen with sound pauses the music, and
    # music started while a ring is up is paused at once; neither starts again by itself.
    def test_music_claims_through_the_media_player(self):
        player = yaml.load((ROOT / 'packages' / 'features' / 'audio-player.yaml').read_text(), Loader=_Loader)
        media = [p for p in player['media_player'] if p.get('id') == 'ts_media_player']
        self.assertEqual(len(media), 1, 'features/audio-player.yaml has the one media player, ts_media_player')
        hooks = {name: ' '.join(str(step.get('lambda')) for step in media[0].get(name) or []) for name in
                 ('on_play', 'on_pause', 'on_idle')}
        play = hooks['on_play']
        self.assertRegex(play, r'\.role = audio_owner::Role::MEDIA;', 'on_play claims the speaker as MEDIA')
        self.assertRegex(play, r'audio_owner::the\(\)\.claim\(audio_owner::Side::OUT,', 'music claims the speaker alone')
        # Refused or taken: paused, never left playing against the owner.
        lost = re.search(r'\.lost = \[\]\(\) \{([^}]*)\}', play)
        self.assertTrue(lost and 'MEDIA_PLAYER_COMMAND_PAUSE' in lost.group(1), 'the music\'s `lost` pauses it')
        refused = re.search(r'if \(!audio_owner::the\(\)\.claim\([^)]*\)\)\s*([^;]*;)', play)
        self.assertTrue(refused and 'MEDIA_PLAYER_COMMAND_PAUSE' in refused.group(1),
                        'music that starts while a higher role holds the speaker is paused at once')
        self.assertNotIn('.regained', play, 'music does not start again by itself after a higher role')
        for hook in ('on_pause', 'on_idle'):
            self.assertRegex(hooks[hook], r'audio_owner::the\(\)\.release\(audio_owner::Side::OUT, audio_owner::Role::MEDIA\)',
                             f'{hook} gives the speaker back')


class PluginApi(unittest.TestCase):
    def test_the_plugin_api_offers_the_owner(self):
        # tessera::audio (plugin API 0.19): a plugin claims in the core's roles through the screen's one owner. Taking one
        # of these away breaks every plugin that plays or listens (docs/PLUGINS.md).
        api = (COMPONENT / 'plugin_api.h').read_text()
        block = re.search(r'namespace audio \{(.*?)\n\}  // namespace audio', api, re.S)
        self.assertTrue(block, 'plugin_api.h has namespace tessera::audio')
        body = block.group(1)
        self.assertIn('using Role = audio_owner::Role;', body, 'a plugin ranks in the core\'s own roles')
        self.assertIn('using Side = audio_owner::Side;', body)
        offered = dict(re.findall(r'inline \w+ (\w+)\([^)]*\) \{[^\n]*?audio_owner::the\(\)\.(\w+)\(', body))
        claim = re.search(r'inline bool claim\(.*?audio_owner::the\(\)\.claim\(', body, re.S)
        self.assertTrue(claim, 'audio::claim claims through audio_owner::the()')
        self.assertEqual(offered, {'release': 'release', 'open': 'would_grant', 'held': 'held', 'holder': 'holder'},
                         'audio::release, open, held and holder each ask audio_owner::the()')


if __name__ == '__main__':
    unittest.main()
