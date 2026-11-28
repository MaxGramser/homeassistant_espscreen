"""The cameras of a video call start while it rings (server.Manager.call_prepare, docs/CALLS.md "Ready before the
answer"): the app keeps both screens' video sources running from the first ring until the call is live or over."""
import importlib.util
import itertools
import pathlib
import sys
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'screen_manager' / 'app'))
import calls  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
if HAS_AIOHTTP:
    from server import Manager


class Live:
    def __init__(self):
        self.kept, self.gone = [], []

    def keep(self, entity):
        self.kept.append(entity)
        return entity

    def let_go(self, held):
        self.gone += held


@unittest.skipUnless(HAS_AIOHTTP, 'the app needs aiohttp')
class ReadyBeforeTheAnswer(unittest.TestCase):
    def setUp(self):
        numbers = itertools.count(1)
        self.calls = calls.Calls(new_key=lambda: f'k{next(numbers)}')
        self.app = types.SimpleNamespace(live=Live(), call_ready={}, call_cameras_off=set(), call_relayed=set())
        self.known = {'hall': {'films': True}, 'kitchen': {'films': True}}

    def say(self, outs):
        for out in outs:
            if isinstance(out, calls.Say):
                Manager.call_prepare(self.app, out, self.known)

    def test_both_cameras_run_from_the_first_ring_and_are_let_go_when_the_call_is_live(self):
        self.say(self.calls.dial('hall', 'kitchen', True, 0, reachable=True))
        self.assertEqual(sorted(self.app.live.kept), ['screen:hall', 'screen:kitchen'], 'once each, though both screens are told')
        self.assertEqual(self.app.live.gone, [])
        self.say(self.calls.answer('k1', 'kitchen', 3))
        self.assertEqual(sorted(self.app.live.gone), ['screen:hall', 'screen:kitchen'])
        self.assertEqual(self.app.call_ready, {})

    def test_a_call_nobody_answers_lets_them_go(self):
        self.say(self.calls.dial('hall', 'kitchen', True, 0, reachable=True))
        self.say(self.calls.decline('k1', 'kitchen', 2))
        self.assertEqual(sorted(self.app.live.gone), ['screen:hall', 'screen:kitchen'])

    def test_a_call_with_sound_alone_a_camera_switched_off_and_a_screen_without_one_start_nothing(self):
        self.say(self.calls.dial('hall', 'kitchen', False, 0, reachable=True))
        self.assertEqual(self.app.live.kept, [])
        self.known['kitchen']['films'] = False
        self.app.call_cameras_off.add('hall')
        self.say(self.calls.hang_up('k1', 'hall', 1))
        self.say(self.calls.dial('hall', 'kitchen', True, 2, reachable=True))
        self.assertEqual(self.app.live.kept, [])

    def test_a_call_straight_between_the_screens_is_not_this_app_s_to_prepare(self):
        for facts in self.known.values():
            facts['direct'] = True
        self.say(self.calls.dial('hall', 'kitchen', True, 0, reachable=True))
        self.assertEqual(self.app.live.kept, [])


class AScreenThatWaitsForItsFirstPicture(unittest.TestCase):
    """The far end's stream stays alive while a screen's camera starts (screen_source.ScreenSource.quiet): a screen
    gives up on a stream that is quiet for 6 s."""

    def test_silence_goes_until_a_picture_comes_or_someone_speaks(self):
        import screen_source
        source = screen_source.ScreenSource(types.SimpleNamespace(), 'screen:hall', 'rtsp://example')
        self.assertTrue(source.quiet(100.0), 'no picture yet, nobody speaks')
        source.last_frame = 100.0
        self.assertFalse(source.quiet(100.5), 'pictures keep the stream alive')
        self.assertTrue(source.quiet(101.5), 'the pictures stopped')
        source.last_voice = 101.4
        self.assertFalse(source.quiet(101.5), 'a voice keeps it alive')


if __name__ == '__main__':
    unittest.main()
