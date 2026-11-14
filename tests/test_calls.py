"""The calls' state machine (screen_manager/app/calls.py): who hears what, and the events that go into Home Assistant."""
import itertools
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'screen_manager' / 'app'))

import calls  # noqa: E402


def machine():
    numbers = itertools.count(1)
    return calls.Calls(new_key=lambda: f'k{next(numbers)}')


def states(out):
    return [(each.node, each.state, each.why) for each in out if isinstance(each, calls.Say)]


def events(out):
    return [each.event for each in out if isinstance(each, calls.Fire)]


def test_a_call_rings_is_answered_and_hung_up():
    c = machine()
    out = c.dial('a', 'b', True, 0)
    assert states(out) == [('a', calls.OUT, ''), ('b', calls.RING, '')]
    assert events(out) == [calls.STARTED]
    out = c.answer('k1', 'b', 2)
    assert states(out) == [('a', calls.LIVE, ''), ('b', calls.LIVE, '')]
    assert events(out) == [calls.ANSWERED]
    out = c.hang_up('k1', 'a', 62)
    assert states(out) == [('a', calls.END, calls.HUNG_UP), ('b', calls.END, calls.HUNG_UP)]
    ended = [each for each in out if isinstance(each, calls.Fire)][0]
    assert ended.event == calls.ENDED and ended.data['seconds'] == 60 and ended.data['from'] == 'a'
    assert c.of('a') is None and c.of('b') is None


def test_only_the_one_rung_answers_or_declines():
    c = machine()
    c.dial('a', 'b', False, 0)
    assert c.answer('k1', 'a', 1) == [] and c.decline('k1', 'a', 1) == []
    out = c.decline('k1', 'b', 2)
    assert states(out) == [('a', calls.END, calls.DECLINED), ('b', calls.END, calls.DECLINED)]
    assert events(out) == []


def test_busy_quiet_and_gone_leave_no_call():
    c = machine()
    c.dial('a', 'b', True, 0)
    assert states(c.dial('c', 'b', True, 1)) == [('c', calls.END, calls.BUSY)]
    assert states(c.dial('c', 'd', True, 1, quiet=True)) == [('c', calls.END, calls.QUIET)]
    assert states(c.dial('c', 'd', True, 1, reachable=False)) == [('c', calls.END, calls.GONE)]
    assert c.of('c') is None and c.of('d') is None


def test_a_screen_is_in_one_call_and_cannot_call_itself():
    c = machine()
    c.dial('a', 'b', True, 0)
    assert c.dial('a', 'c', True, 1) == []
    assert c.dial('x', 'x', True, 1) == []


def test_a_ring_nobody_answers_is_missed_after_its_time():
    c = machine()
    c.dial('a', 'b', True, 0)
    assert c.tick(calls.RING_SECONDS - 1) == []
    out = c.tick(calls.RING_SECONDS)
    assert states(out) == [('a', calls.END, calls.NO_ANSWER), ('b', calls.END, calls.MISSED)]
    assert events(out) == [calls.MISSED_EVENT]
    assert c.missed['b']['from'] == 'a'


def test_called_off_while_it_rings_is_missed_at_the_other_end():
    c = machine()
    c.dial('a', 'b', True, 0)
    out = c.hang_up('k1', 'a', 5)
    assert states(out) == [('a', calls.END, calls.HUNG_UP), ('b', calls.END, calls.MISSED)]
    assert c.missed['b']['from'] == 'a'


def test_a_screen_that_goes_away_ends_the_call_for_the_other():
    c = machine()
    c.dial('a', 'b', True, 0)
    c.answer('k1', 'b', 1)
    out = c.gone('b', 10)
    assert ('a', calls.END, calls.GONE) in states(out)
    assert c.of('a') is None
    assert c.gone('b', 11) == []


def test_the_door_goes_first_and_the_call_comes_back():
    c = machine()
    c.dial('a', 'b', True, 0)
    assert c.door('b', True) == [], 'it only rings yet: nothing to hold'
    c.answer('k1', 'b', 1)
    out = c.door('b', True)
    assert states(out) == [('a', calls.HELD, ''), ('b', calls.HELD, '')]
    assert c.door('b', True) == []
    assert states(c.door('b', False)) == [('a', calls.LIVE, ''), ('b', calls.LIVE, '')]


def test_the_list_says_what_each_screen_can_do():
    c = machine()
    screens = {
        'a': {'name': 'Hall', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': True},
        'b': {'name': 'Kitchen', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': True},
        'c': {'name': 'Attic', 'hears': True, 'speaks': True, 'films': False, 'shows': True, 'online': True},
        'd': {'name': 'Bedroom', 'hears': True, 'speaks': True, 'films': True, 'shows': True, 'online': True, 'quiet': True},
        'e': {'name': 'Shed', 'hears': True, 'speaks': True, 'online': False},
    }
    rows = {row['id']: row for row in c.contacts('a', screens)}
    assert 'a' not in rows
    assert (rows['b']['a'], rows['b']['v'], rows['b']['s']) == (1, 1, calls.FREE)
    assert (rows['c']['a'], rows['c']['v']) == (1, 0), 'no camera there: sound only'
    assert (rows['d']['a'], rows['d']['s']) == (0, calls.DND)
    assert (rows['e']['a'], rows['e']['s']) == (0, calls.OFFLINE)
    c.dial('b', 'c', True, 0)
    assert {row['id']: row for row in c.contacts('a', screens)}['b']['s'] == calls.IN_CALL


def test_a_missed_call_shows_until_the_list_is_seen():
    c = machine()
    screens = {'a': {'name': 'Hall', 'online': True}, 'b': {'name': 'Kitchen', 'online': True}}
    c.dial('a', 'b', False, 0)
    c.tick(calls.RING_SECONDS)
    assert c.contacts('b', screens)[0]['m'] == calls.RING_SECONDS
    assert c.seen('b') is True
    assert 'm' not in c.contacts('b', screens)[0]
    assert c.seen('b') is False


def test_the_app_starting_forgets_every_call():
    c = machine()
    c.dial('a', 'b', True, 0)
    out = c.forget()
    assert ('a', calls.END, calls.GONE) in states(out) and ('b', calls.END, calls.GONE) in states(out)
    assert c.calls == {}


def test_the_message_is_additive():
    live = calls.Say('a', 'k', calls.LIVE, 'b', True)
    assert calls.message(live, name='Kitchen', link='http://x/camera/t.mjpeg', peer_camera=False) == {
        'v': 1, 'op': 'call', 'k': 'k', 's': 'live', 'n': 'Kitchen', 'vd': 1, 'l': 'http://x/camera/t.mjpeg', 'pc': 0}
    end = calls.Say('a', 'k', calls.END, 'b', False, calls.BUSY)
    assert calls.message(end)['w'] == 'busy'


def test_thirty_screens_fit_the_messages():
    rows = [{'id': f'screen-{n}', 'n': 'A very long name of a screen in a large house ' * 3, 'i': 'x', 'a': 1, 'v': 1, 's': 'free'} for n in range(30)]
    parts = calls.contacts_messages(rows)
    assert len(parts) == 3 and [p['p'] for p in parts] == [0, 1, 2] and [p['more'] for p in parts] == [1, 1, 0]
    import json
    assert all(len(json.dumps(p)) < 4096 for p in parts)
    assert sum(len(p['r']) for p in parts) == 30


def test_the_ones_that_can_be_called_come_first():
    c = machine()
    screens = {'a': {'name': 'Me', 'hears': True, 'speaks': True, 'online': True},
               'b': {'name': 'Attic', 'online': False},
               'c': {'name': 'Zolder', 'hears': True, 'speaks': True, 'online': True}}
    assert [row['id'] for row in c.contacts('a', screens)] == ['c', 'b']


def tone(level, parts=1):
    import array
    return array.array('h', [level if i % 2 else -level for i in range(320)]).tobytes() * parts


def level_of(data):
    import array
    samples = array.array('h')
    samples.frombytes(data)
    return calls.rms(samples)


def test_the_one_who_speaks_holds_the_line_and_the_other_goes_down():
    s = calls.VoiceSwitch('a', 'b')
    assert level_of(s.feed('a', tone(5000), 0.0)) > 4900
    s.feed('b', tone(3000), 0.02)        # the voice coming back from the other loudspeaker
    assert level_of(s.feed('b', tone(3000), 0.04)) < 3000 * calls.DUCK * 1.1
    assert level_of(s.feed('a', tone(5000), 0.06)) > 4900


def test_after_the_hold_the_other_may_speak():
    s = calls.VoiceSwitch('a', 'b')
    s.feed('a', tone(5000), 0.0)
    s.feed('a', tone(10), 0.1)
    s.feed('b', tone(3000), 0.5)
    assert s.talker == 'b'
    assert level_of(s.feed('b', tone(3000), 0.52)) > 2900


def test_a_side_with_its_own_canceller_is_never_turned_down():
    s = calls.VoiceSwitch('a', 'b', cancels=['b'])
    s.feed('a', tone(5000), 0.0)
    assert level_of(s.feed('b', tone(3000), 0.02)) > 2900


def test_the_rooms_noise_is_no_voice():
    s = calls.VoiceSwitch('a', 'b')
    for n in range(40):
        s.feed('a', tone(200), n * 0.02)
    assert s.talker is None


def test_a_screen_without_the_feature_gets_no_call_tile():
    tiles = [{'entity': 'light.a'}, {'entity': calls.TILE}]
    assert calls.unsupported(tiles, ['doorbell'])          # a released firmware, or a board without the feature: not sent
    assert not calls.unsupported(tiles, ['call'])
    assert not calls.unsupported(tiles, None)              # a screen that said nothing yet
    assert not calls.unsupported([{'entity': 'light.a'}], ['doorbell'])
    source = (pathlib.Path(__file__).resolve().parent.parent / 'screen_manager/app/server.py').read_text()
    assert "screen['call_tiles'] = calls.FEATURE in (getattr(manager.page_senders.get(screen['id']), 'features', None) or ())" in source


def test_with_no_call_up_the_app_only_waits():
    source = (pathlib.Path(__file__).resolve().parent.parent / 'screen_manager/app/server.py').read_text()
    assert 'asyncio.wait_for(self.ha.call_events.get(), 1 if self.calls.calls else None)' in source
