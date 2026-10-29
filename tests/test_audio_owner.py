"""The audio owner's wiring (components/smart_display/audio_owner.h; docs/PLATFORM_PLAN.md 3.4): the core's own claims
are where the plan says, each matched by a release, the media player's hooks claim and release, the plugin API offers
it, and the host test is in the runner. The owner's behaviour itself is tests/test_audio_owner.cpp."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'components' / 'smart_display'


class Wiring(unittest.TestCase):
    def test_a_cameras_sound_claims_and_releases(self):
        source = (COMPONENT / 'live_view.cpp').read_text()
        self.assertIn('#include "audio_owner.h"', source)
        # The role is the opener's: CAMERA_SOUND by default, DOORBELL for the view a ring opened; released as claimed.
        self.assertIn('bool sound, audio_owner::Role role)', source)
        self.assertIn('claim.role = role;', source)
        # The speaker, and for a ring the microphone too (the wake word rests while someone is at the door); released as
        # claimed.
        self.assertIn('s->claimed = role == audio_owner::Role::DOORBELL ? audio_owner::Side::BOTH : audio_owner::Side::OUT;',
                      source)
        self.assertIn('audio_owner::the().claim(s->claimed, claim);', source)
        self.assertIn('if (s->claims) audio_owner::the().release(s->claimed, s->sound_role, static_cast<uint32_t>(slot));', source)
        header = (COMPONENT / 'live_view.h').read_text()
        self.assertEqual(header.count('audio_owner::Role role = audio_owner::Role::CAMERA_SOUND'), 1)
        # What it lost holds the sound back as a mute does, in the task and on the main loop.
        self.assertIn('if (s.muted || s.yielded) return;', source)
        # A part goes in whole or not at all: a static stream buffer holds one byte less than its storage, and a part cut
        # to the room left was an odd count that put every later sample a byte off (full-scale noise, 2026-10-25).
        self.assertIn('if (xStreamBufferSpacesAvailable(s.sound) >= whole)\n            xStreamBufferSend(s.sound, s.sound_part, '
                      'whole, 0);', source)
        self.assertEqual(source.count('xStreamBufferSend('), 1)
        # The sound keeps up with the picture: the main loop leaves the oldest out above SOUND_HIGH, down to SOUND_LOW.
        # Every tick, before the speaker is fed: a speaker that is full does not hold the catching up back.
        self.assertIn('if (held > SOUND_HIGH && (s.piece_at & 1) == 0) {', source)
        self.assertLess(source.index('if (held > SOUND_HIGH'), source.index('for (int rounds = 0; rounds < 8; ++rounds) {'))
        self.assertIn('for (size_t drop = held - SOUND_LOW; drop > 0;) {', source)
        self.assertIn('if (xStreamBufferBytesAvailable(s.sound) < SOUND_LOW) return;', source)
        self.assertIn('speak(*s, !s->stopping && !s->muted && !s->yielded);', source)
        self.assertLess(source.index('t->yielded = true;'), source.index('t->yielded = false;'))

    def test_a_rings_view_claims_as_the_doorbell(self):
        # The ring's view is one stream: it claims DOORBELL through live_view::open from the full view's opener, so its
        # own camera sound plays (a separate ring claim would refuse it) and nothing takes the speaker from a ring.
        runtime = (COMPONENT / 'runtime_tiles.h').read_text()
        self.assertIn('if (doorbell::shown()) role = audio_owner::Role::DOORBELL;', runtime)
        self.assertIn('live_view::has_speaker(), role));', runtime)
        doorbell = (COMPONENT / 'module_doorbell.cpp').read_text()
        self.assertNotIn('audio_owner::the().claim', doorbell)
        self.assertNotIn('audio_owner::the().release', doorbell)

    def test_music_claims_through_the_media_player(self):
        yaml = (ROOT / 'packages' / 'features' / 'audio-player.yaml').read_text()
        self.assertIn('claim.role = audio_owner::Role::MEDIA;', yaml)
        for hook in ('on_play:', 'on_pause:', 'on_idle:'):
            self.assertIn(hook, yaml)
        # Refused or taken: paused, never left playing against the owner.
        self.assertEqual(yaml.count('MEDIA_PLAYER_COMMAND_PAUSE'), 2)
        self.assertEqual(yaml.count('audio_owner::the().release(audio_owner::Side::OUT, audio_owner::Role::MEDIA);'), 2)

    def test_the_plugin_api_offers_it_and_the_ranking_is_the_one_max_set(self):
        api = (COMPONENT / 'plugin_api.h').read_text()
        self.assertIn('#include "audio_owner.h"', api)
        for name in ('namespace audio {', 'inline bool claim(Side side, Role role, uint32_t id', 'inline void release(Side side, Role role',
                     'inline bool open(Side side, Role role)', 'inline Role holder(Side side)'):
            self.assertIn(name, api)
        owner = (COMPONENT / 'audio_owner.h').read_text()
        self.assertRegex(owner, r'enum class Role : uint8_t \{ MEDIA = 0, CAMERA_SOUND = 1, VOICE = 2, DOORBELL = 3 \}')
        self.assertIn('#include "audio_owner.h"', (COMPONENT / 'smart_display.h').read_text())
        self.assertTrue((ROOT / 'tests' / 'test_audio_owner.cpp').exists())
        plan = (ROOT / 'docs' / 'PLATFORM_PLAN.md').read_text()
        self.assertIn('enum class Role { MEDIA, CAMERA_SOUND, VOICE, DOORBELL };', plan)


if __name__ == '__main__':
    unittest.main()
