"""A screen in Home Assistant without a step there (app 0.4.73).

A screen made with New screen has to be in Home Assistant's ESPHome integration, and that integration has to allow it
to perform actions, or a tap on a tile does nothing. Home Assistant leaves both to a person: it lists a device it finds
under Discovered, asks for its key, and keeps "Allow the device to perform Home Assistant actions" off for every new
ESPHome device. This app now takes those steps itself, through the same config flows and options flows Home
Assistant's own dialogs use, and keeps looking until they are done instead of trying once:

- A screen this app made that Home Assistant does not have yet: its discovery is answered with the key the app wrote
  into the screen's YAML. Without a discovery (Home Assistant missed it, or someone dismissed or ignored it), Home
  Assistant is asked to look the screen up by its name on the network, as Add integration -> ESPHome does. A key the
  screen does not take yet (an older firmware still runs on it) is offered again a little later.
- A screen Home Assistant has but cannot open any more, because New screen gave it new keys: the key Home Assistant
  asks for again is given back.
- A board that takes over the name of an earlier one (a replacement flashed from the same profile): Home Assistant's
  own "migrate" keeps the screen's entities and history.
- Actions: on for a screen as soon as it is in Home Assistant, checked once per start for every screen this app made,
  and turned on at once when Home Assistant reports that it ignored a tap of a screen.

Only screens this app made are added, each with its own key. Nothing goes around Home Assistant: whatever it asks that
this app cannot answer stays there, and the editor offers the way by hand only then.
"""
import base64
import binascii
import logging
import re
import time

LOG = logging.getLogger('screen_manager')

# How often the app looks: a person is usually watching the screen start.
INTERVAL = 5
# A discovery Home Assistant still holds after an answer it did not take (a key the screen does not have yet) is
# answered again this much later.
AGAIN = 30
# Looking a screen up by its name when Home Assistant did not discover it: soon at first, then less often, never stopping
# while the profile waits (a profile can wait days for its firmware).
LOOK_UP = (20, 30, 60, 120, 300)
# How long a screen may stay found but not added before the editor offers the way by hand.
HELP_AFTER = 180
# How often the repairs are read without being told (Home Assistant also announces a new one).
ISSUES = 60
# An integration this young was added just now, by this app or by someone in Home Assistant's own dialog.
FRESH_ENTRY = 15 * 60
# Flows a person started, or that repair another integration, are never this app's.
NOT_DISCOVERY = {'user', 'reauth', 'reconfigure', 'ignore'}
# What a finished flow can say when the screen is in Home Assistant with the right key after all.
PAIRED = {'already_configured', 'already_configured_updates', 'already_configured_detailed', 'reauth_successful',
          'name_conflict_migrated'}
ACTIONS_ISSUE = 'service_calls_not_enabled-'


def discovered_node(flow):
    """The node an ESPHome device Home Assistant discovered is called, or None for any other flow. Home Assistant titles
    the device "<friendly name> (<node>)", or the node alone when the two are the same (the esphome integration's
    `_async_get_human_readable_name`), so a node is never compared with that title as a whole."""
    if not isinstance(flow, dict) or flow.get('handler') != 'esphome':
        return None
    context = flow.get('context') if isinstance(flow.get('context'), dict) else {}
    if context.get('source') in NOT_DISCOVERY:
        return None
    name = (context.get('title_placeholders') or {}).get('name')
    if not isinstance(name, str) or not name.strip():
        return None
    found = re.fullmatch(r'.*\(([a-z0-9_-]+)\)', name.strip())
    return found.group(1) if found else name.strip().lower()


def usable_key(key):
    """Whether a profile's API key is one Home Assistant can take: 32 bytes in base64, as New screen writes it. A
    `!secret` reference or a placeholder is not, and is never offered to a device."""
    try:
        return isinstance(key, str) and len(base64.b64decode(key, validate=True)) == 32
    except (binascii.Error, ValueError):
        return False


def answered(step):
    """Home Assistant's answer to a step in a few words, for the log: what it still asks, or why it stopped."""
    if not isinstance(step, dict):
        return 'no answer'
    kind = step.get('type')
    if kind == 'form':
        errors = step.get('errors') or {}
        return f"asks for {step.get('step_id')}" + (f" ({', '.join(map(str, errors.values()))})" if errors else '')
    if kind == 'menu':
        return f"asks to choose ({step.get('step_id')})"
    if kind == 'abort':
        return f"stopped: {step.get('reason')}"
    return str(kind)


async def finish(ha, step, key):
    """Take a flow of one screen to its end, the way a person in Home Assistant's dialog would with the screen's key:
    the key where it is asked, "migrate" where a board takes over the screen's name. Returns (entry id or True when the
    screen is in Home Assistant, None otherwise; the last answer). A form asked a second time means Home Assistant did
    not take the answer, and the flow stays where it is."""
    asked = set()
    for _ in range(4):
        kind, step_id, flow_id = step.get('type'), step.get('step_id'), step.get('flow_id')
        if kind == 'create_entry':
            return (step.get('result') or {}).get('entry_id') or True, step
        if kind == 'abort':
            return (True if step.get('reason') in PAIRED else None), step
        if step_id in asked or not flow_id:
            return None, step
        asked.add(step_id)
        if kind == 'form' and step_id in ('encryption_key', 'reauth_confirm') and not step.get('errors'):
            step = await ha.flow('post', f'flow/{flow_id}', {'noise_psk': key})
        elif kind == 'form' and step_id == 'discovery_confirm':
            step = await ha.flow('post', f'flow/{flow_id}', {})
        elif kind == 'menu' and 'name_conflict_migrate' in (step.get('menu_options') or []):
            step = await ha.flow('post', f'flow/{flow_id}', {'next_step_id': 'name_conflict_migrate'})
        else:
            return None, step
    return None, step


async def actions_allowed(ha, entry_id, allow=True):
    """Whether one ESPHome integration lets its device perform Home Assistant actions, read from its Configure dialog
    (the options flow, whose form starts at the current value); with `allow` the switch is turned on when it is off.
    Only that switch changes: Home Assistant keeps every other option, and reloads the integration only when something
    did change. A dialog left unanswered is closed again. Returns 'on' when it already was, 'turned_on', or False."""
    form = await ha.flow('post', 'options/flow', {'handler': entry_id})
    flow_id = form.get('flow_id')
    field = next((f for f in form.get('data_schema') or [] if isinstance(f, dict) and f.get('name') == 'allow_service_calls'), None)
    if form.get('type') != 'form' or field is None:
        if flow_id:
            await ha.flow('delete', f'options/flow/{flow_id}')
        LOG.warning('Home Assistant offers no "perform actions" switch for integration %s (%s)', entry_id, answered(form))
        return False
    if field.get('default') is True:
        await ha.flow('delete', f'options/flow/{flow_id}')
        return 'on'
    if not allow:
        await ha.flow('delete', f'options/flow/{flow_id}')
        return False
    done = await ha.flow('post', f'options/flow/{flow_id}', {'allow_service_calls': True})
    return 'turned_on' if done.get('type') == 'create_entry' else False


async def allow_actions(ha, entry_id):
    """Turn on "Allow the device to perform Home Assistant actions" for one integration; whether it is on now."""
    return bool(await actions_allowed(ha, entry_id))


class Pairing:
    """What this app does about the screens Home Assistant does not have yet, or that may not perform actions: one look
    every few seconds (`run`), each step again until it holds. `state` tells the editor per waiting screen: `adding` once
    Home Assistant found it, `failed` when it stayed found but not added (HELP_AFTER) or asked what only a person can
    answer."""

    def __init__(self):
        self.flow_due = {}      # flow id -> monotonic time it may be answered again
        self.look_ups = {}      # node -> (attempts, monotonic time of the next look-up)
        self.found_at = {}      # node -> when Home Assistant first found it, while it waits
        self.stuck = set()      # nodes whose flow asked what only a person can answer
        self.checked = set()    # entry ids whose actions were looked at this run
        self.retry_actions = {}  # entry id -> monotonic time the switch may be tried again
        # The repairs are read again when Home Assistant announces one (Manager.pairing_loop sets this), and every
        # ISSUES seconds without.
        self.issues_due, self.issues_read = True, 0.0
        self.state = {}

    async def run(self, ha, ours, screens):
        """One look. `ours` is {node: {'api_key', 'friendly'}} for every screen this app made with a usable key, `screens`
        the screens Home Assistant has (with their node and device)."""
        now = time.monotonic()
        entries = await ha.esphome_entries()
        devices = {d.get('id'): d for d in getattr(ha, 'devices', None) or [] if isinstance(d, dict)}
        entry_of = {}
        for screen in screens:
            mine = [entries[e] for e in (devices.get(screen.get('device_id')) or {}).get('config_entries') or [] if e in entries]
            if len(mine) == 1 and screen.get('node'):
                entry_of[screen['node']] = mine[0]
        waiting = [node for node in ours if node not in entry_of]
        # A screen whose key changed keeps its integration loaded while Home Assistant asks for the key (a reauth flow
        # of that entry), so every screen of ours counts, whatever its state.
        known = {entry_of[node]['entry_id']: node for node in ours if node in entry_of}
        for node in list(self.found_at):
            if node not in waiting:
                self.found_at.pop(node)
                self.stuck.discard(node)
        # Every look, not only while a screen waits: a board that replaces a paired one under its name is discovered
        # while the old one still counts as paired.
        if ours:
            await self.answer_flows(ha, ours, waiting, known, now)
        self.state = {node: ('failed' if node in self.stuck or now - self.found_at[node] >= HELP_AFTER else 'adding')
                      for node in waiting if node in self.found_at}
        await self.check_actions(ha, ours, screens, entry_of, now)

    async def answer_flows(self, ha, ours, waiting, known, now):
        """Home Assistant's own flows for these screens first: a discovered device, a key it asks again. A waiting screen
        it has no flow for is looked up by its name."""
        flowing, flows = set(), await ha.flows()
        # Forget the answers to flows Home Assistant no longer holds.
        current = {flow.get('flow_id') for flow in flows}
        self.flow_due = {flow_id: due for flow_id, due in self.flow_due.items() if flow_id in current}
        for flow in flows:
            source = (flow.get('context') or {}).get('source')
            node = known.get((flow.get('context') or {}).get('entry_id')) if source == 'reauth' else discovered_node(flow)
            if node not in ours or flow.get('handler') != 'esphome':
                continue
            flowing.add(node)
            if source != 'reauth':
                self.found_at.setdefault(node, now)
            flow_id = flow.get('flow_id')
            if not flow_id or now < self.flow_due.get(flow_id, 0):
                continue
            self.flow_due[flow_id] = now + AGAIN
            await self.attempt(ha, node, ours[node], flow_id, flow.get('step_id'))
        for node in waiting:
            if node in flowing:
                continue
            attempts, due = self.look_ups.get(node, (0, now + LOOK_UP[0]))
            if node not in self.look_ups:
                self.look_ups[node] = (attempts, due)
            if now < due:
                continue
            self.look_ups[node] = (attempts + 1, now + LOOK_UP[min(attempts + 1, len(LOOK_UP) - 1)])
            await self.look_up(ha, node, ours[node])

    async def attempt(self, ha, node, profile, flow_id, step_id):
        """Answer one flow Home Assistant holds for a screen, from the step it is at."""
        name = profile.get('friendly') or node
        start = {'type': 'form', 'flow_id': flow_id, 'step_id': step_id}
        try:
            entry, last = await finish(ha, start, profile['api_key'])
        except Exception as error:  # noqa: BLE001 - Home Assistant keeps the flow; the next look tries again
            LOG.info('%s is not in Home Assistant yet (%s); trying again', name, type(error).__name__)
            return
        if entry:
            self.done(node)
            LOG.info('%s is in Home Assistant', name)
            if isinstance(entry, str):
                await self.allow(ha, entry, name)
            return
        if last.get('type') == 'form' and last.get('step_id') == 'authenticate':
            self.stuck.add(node)
        LOG.info('%s is not in Home Assistant yet: it %s; trying again', name, answered(last))

    async def look_up(self, ha, node, profile):
        """Ask Home Assistant to find a screen by its name on the network, as Add integration -> ESPHome does with a
        host name: for a screen it did not discover, or whose discovery someone dismissed or ignored. A flow that does
        not end in Home Assistant is closed again, so nothing of this app's is left in its list."""
        try:
            form = await ha.flow('post', 'flow', {'handler': 'esphome'})
            if form.get('type') != 'form' or form.get('step_id') != 'user':
                return
            step = await ha.flow('post', f"flow/{form['flow_id']}", {'host': f'{node}.local', 'port': 6053})
            entry, last = await finish(ha, step, profile['api_key'])
            if not entry and last.get('flow_id') and last.get('type') in ('form', 'menu'):
                await ha.flow('delete', f"flow/{last['flow_id']}")
        except Exception as error:  # noqa: BLE001 - the screen may simply not be on the network yet
            LOG.debug('Looking up %s: %s', node, type(error).__name__)
            return
        if entry:
            self.done(node)
            LOG.info('%s is in Home Assistant (found by its name on the network)', profile.get('friendly') or node)
            if isinstance(entry, str):
                await self.allow(ha, entry, profile.get('friendly') or node)

    def done(self, node):
        self.look_ups.pop(node, None)
        self.found_at.pop(node, None)
        self.stuck.discard(node)

    async def check_actions(self, ha, ours, screens, entry_of, now):
        """Every screen in Home Assistant may perform actions: a new one and one this app made are looked at once per
        start, and one Home Assistant reports for an ignored tap at once (its repair issue)."""
        names = {node: screen.get('name') or node for screen in screens if (node := screen.get('node'))}
        for node, entry in entry_of.items():
            entry_id = entry.get('entry_id')
            if entry_id in self.checked or entry.get('state') != 'loaded':
                continue
            if node in ours or time.time() - float(entry.get('created_at') or 0) < FRESH_ENTRY:
                await self.allow(ha, entry_id, names.get(node, node))
        if self.issues_due or now - self.issues_read > ISSUES:
            self.issues_due, self.issues_read = False, now
            blocked = await ha.actions_blocked()
            for node, entry in entry_of.items():
                device = next((s.get('device_id') for s in screens if s.get('node') == node), None)
                if device in blocked and now >= self.retry_actions.get(entry['entry_id'], 0):
                    self.retry_actions[entry['entry_id']] = now + ISSUES
                    await self.allow(ha, entry['entry_id'], names.get(node, node))

    async def allow(self, ha, entry_id, name):
        self.checked.add(entry_id)
        try:
            if await actions_allowed(ha, entry_id) == 'turned_on':
                LOG.info('%s may perform Home Assistant actions', name)
        except Exception as error:  # noqa: BLE001 - the editor's notice then offers the switch
            LOG.warning('%s may not perform Home Assistant actions yet (%s)', name, type(error).__name__)
