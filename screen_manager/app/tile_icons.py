"""Curated Material Design Icons for tiles, shared by the editor and both firmware boards.

This is the only list. `python3 tools/generate_icons.py` writes these glyphs into
the three icon fonts of both board profiles and builds the editor font
`static/tile-icons.woff`; `--check` verifies names and codepoints against
fonts/materialdesignicons-webfont.ttf. Firmware 0.2.18+ carries every glyph here.
"""

import re

from i18n import t

# (group, ((MDI name, codepoint, label), ...)) in picker order. The labels in English, as the Claude skill writes them; the
# editor's picker gets them in its language (editor(), app 0.2.90).
GROUPS = (
    ('Lighting', (
        ('lightbulb', 'F0335', 'Light bulb'),
        ('lightbulb-group', 'F1253', 'Lights'),
        ('ceiling-light', 'F0769', 'Ceiling light'),
        ('chandelier', 'F1793', 'Chandelier'),
        ('lamp', 'F06B5', 'Table lamp'),
        ('floor-lamp', 'F08DD', 'Floor lamp'),
        ('desk-lamp', 'F095F', 'Desk lamp'),
        ('wall-sconce-flat', 'F091D', 'Wall light'),
        ('light-recessed', 'F179B', 'Recessed light'),
        ('spotlight-beam', 'F04C9', 'Spotlight'),
        ('led-strip-variant', 'F1051', 'LED strip'),
        ('outdoor-lamp', 'F1054', 'Outdoor light'),
    )),
    ('Rooms', (
        ('home', 'F02DC', 'House'),
        ('sofa', 'F04B9', 'Living room'),
        ('bed', 'F02E3', 'Bedroom'),
        ('silverware-fork-knife', 'F0A70', 'Dining room'),
        ('chef-hat', 'F0B7C', 'Kitchen'),
        ('shower', 'F09A0', 'Shower'),
        ('bathtub', 'F1818', 'Bathroom'),
        ('toilet', 'F09AB', 'Toilet'),
        ('desk', 'F1239', 'Office'),
        ('garage', 'F06D9', 'Garage'),
        ('fireplace', 'F0E2E', 'Fireplace'),
    )),
    ('Climate', (
        ('thermometer', 'F050F', 'Temperature'),
        ('thermostat', 'F0393', 'Thermostat'),
        ('air-conditioner', 'F001B', 'AC'),
        ('radiator', 'F0438', 'Radiator'),
        ('heat-pump', 'F1A43', 'Heat pump'),
        ('fire', 'F0238', 'Heating'),
        ('snowflake', 'F0717', 'Cooling'),
        ('water-percent', 'F058E', 'Humidity'),
        ('fan', 'F0210', 'Fan'),
        ('ceiling-fan', 'F1797', 'Ceiling fan'),
        ('air-purifier', 'F0D44', 'Air purifier'),
        ('molecule-co2', 'F07E4', 'CO₂'),
    )),
    ('Weather', (
        ('weather-sunny', 'F0599', 'Sun'),
        ('weather-partly-cloudy', 'F0595', 'Partly cloudy'),
        ('weather-cloudy', 'F0590', 'Cloudy'),
        ('weather-rainy', 'F0597', 'Rain'),
        ('weather-snowy', 'F0598', 'Snow'),
        ('weather-windy', 'F059D', 'Wind'),
        ('weather-night', 'F0594', 'Night'),
        ('weather-sunset-up', 'F059C', 'Sunrise'),
    )),
    ('Media and music', (
        ('music-note', 'F0387', 'Music'),
        ('music', 'F075A', 'Music notes'),
        ('playlist-music', 'F0CB8', 'Playlist'),
        ('album', 'F0025', 'Album'),
        ('record-player', 'F099A', 'Record player'),
        ('spotify', 'F04C7', 'Spotify'),
        ('radio', 'F0439', 'Radio'),
        ('podcast', 'F0994', 'Podcast'),
        ('speaker', 'F04C3', 'Speaker'),
        ('speaker-multiple', 'F0D38', 'Speakers'),
        ('soundbar', 'F17DB', 'Soundbar'),
        ('headphones', 'F02CB', 'Headphones'),
        ('piano', 'F067D', 'Piano'),
        ('guitar-acoustic', 'F0771', 'Guitar'),
        ('television', 'F0502', 'TV'),
        ('projector', 'F042E', 'Projector'),
        ('movie-open', 'F0FCE', 'Movie'),
        ('cast', 'F0118', 'Cast'),
        ('gamepad-variant', 'F0297', 'Game console'),
        ('remote-tv', 'F0EC5', 'Remote control'),
    )),
    ('Security', (
        ('lock', 'F033E', 'Lock'),
        ('lock-open-variant', 'F0FC6', 'Lock open'),
        ('shield-home', 'F068A', 'Alarm'),
        ('alarm-light', 'F078F', 'Alarm light'),
        ('bell', 'F009A', 'Bell'),
        ('doorbell', 'F12E6', 'Doorbell'),
        ('cctv', 'F07AE', 'Camera'),
        ('motion-sensor', 'F0D91', 'Motion sensor'),
        ('door-closed', 'F081B', 'Door'),
        ('door-open', 'F081C', 'Door open'),
        ('window-closed-variant', 'F11DB', 'Window'),
        ('smoke-detector', 'F0392', 'Smoke detector'),
        ('water-alert', 'F1502', 'Water leak'),
    )),
    ('Appliances', (
        ('washing-machine', 'F072A', 'Washing machine'),
        ('tumble-dryer', 'F0917', 'Dryer'),
        ('dishwasher', 'F0AAC', 'Dishwasher'),
        ('fridge', 'F0290', 'Fridge'),
        ('stove', 'F04DE', 'Stove'),
        ('microwave', 'F0C99', 'Microwave'),
        ('toaster-oven', 'F0CD3', 'Oven'),
        ('coffee-maker', 'F109F', 'Coffee'),
        ('kettle', 'F05FA', 'Kettle'),
        ('robot-vacuum', 'F070D', 'Robot vacuum'),
        ('robot-mower', 'F11F7', 'Robot mower'),
        ('printer-3d', 'F042B', '3D printer'),
        ('power-plug', 'F06A5', 'Plug'),
        ('power-socket-eu', 'F07E7', 'Socket'),
        ('laptop', 'F0322', 'Laptop'),
        ('router-wireless', 'F0469', 'Router'),
    )),
    ('Energy', (
        ('flash', 'F0241', 'Power'),
        ('solar-power', 'F0A72', 'Solar power'),
        ('solar-panel', 'F0D9B', 'Solar panels'),
        ('home-battery', 'F1901', 'Home battery'),
        ('battery-high', 'F12A3', 'Battery'),
        ('ev-station', 'F05F1', 'Charging station'),
        ('car-electric', 'F0B6C', 'Electric car'),
        ('meter-electric', 'F1A57', 'Power meter'),
        ('meter-gas', 'F1A59', 'Gas meter'),
        ('water', 'F058C', 'Water'),
        ('water-boiler', 'F0F92', 'Boiler'),
        ('gauge', 'F029A', 'Meter'),
    )),
    ('Window coverings', (
        ('window-shutter', 'F111C', 'Shutter'),
        ('window-shutter-open', 'F111E', 'Shutter open'),
        ('blinds', 'F00AC', 'Blinds'),
        ('blinds-open', 'F1011', 'Blinds open'),
        ('roller-shade-closed', 'F1A6C', 'Roller blind'),
        ('curtains', 'F1846', 'Curtains'),
        ('curtains-closed', 'F1847', 'Curtains closed'),
        ('awning-outline', 'F1B88', 'Awning'),
    )),
    ('Garden and pets', (
        ('flower', 'F024A', 'Flower'),
        ('tree', 'F0531', 'Tree'),
        ('sprout', 'F0E66', 'Plant'),
        ('grass', 'F1510', 'Lawn'),
        ('sprinkler', 'F105F', 'Sprinkler'),
        ('pool', 'F0606', 'Pool'),
        ('grill', 'F0E45', 'Barbecue'),
        ('mailbox', 'F06EE', 'Mailbox'),
        ('trash-can', 'F0A79', 'Trash'),
        ('recycle', 'F044C', 'Recycling'),
        ('dog', 'F0A43', 'Dog'),
        ('cat', 'F011B', 'Cat'),
    )),
    ('People and travel', (
        ('account', 'F0004', 'Person'),
        ('account-group', 'F0849', 'Family'),
        ('account-child', 'F0A89', 'Child'),
        ('home-account', 'F0826', 'Home'),
        ('sleep', 'F04B2', 'Sleeping'),
        ('run', 'F070E', 'Exercising'),
        ('briefcase', 'F00D6', 'Work'),
        ('car', 'F010B', 'Car'),
        ('bike', 'F00A3', 'Bike'),
        ('airplane', 'F001D', 'Vacation'),
        ('map-marker', 'F034E', 'Location'),
    )),
    ('Other', (
        ('power', 'F0425', 'On/off'),
        ('toggle-switch', 'F0521', 'Switch'),
        ('gesture-tap-button', 'F12A8', 'Button'),
        ('play', 'F040A', 'Start'),
        ('script-text', 'F0BC2', 'Script'),
        ('palette', 'F03D8', 'Scene'),
        ('alarm', 'F0020', 'Alarm clock'),
        ('clock-outline', 'F0150', 'Clock'),
        ('timer-outline', 'F051B', 'Timer'),
        ('calendar', 'F00ED', 'Calendar'),
        ('bell-ring', 'F009E', 'Notification'),
        ('heart', 'F02D1', 'Favorite'),
        ('alert-outline', 'F002A', 'Warning'),
        ('cog', 'F0493', 'Settings'),
        ('broom', 'F00E2', 'Cleaning'),
        ('diabetes', 'F1126', 'Diabetes'),
    )),
)

# Glyphs the firmware draws itself (weather conditions, sun, checkmark, direct controls) that the picker does not offer.
FIXED = (
    ('alert-circle-outline', 'F05D6'),
    # A remote's keypad (firmware 0.22.0): the ring's arrows up and down beside chevron-left/-right, Back, Home,
    # Play/Pause and the volume keys.
    ('chevron-up', 'F0143'),
    ('chevron-down', 'F0140'),
    ('arrow-u-left-top', 'F17B3'),
    ('play-pause', 'F040E'),
    ('volume-plus', 'F075D'),
    ('volume-minus', 'F075E'),
    ('volume-mute', 'F075F'),
    ('check', 'F012C'),
    # Direct controls on wide cards (firmware 0.2.19+).
    ('pause', 'F03E4'),
    ('stop', 'F04DB'),
    ('skip-next', 'F04AD'),
    ('skip-previous', 'F04AE'),
    ('volume-high', 'F057E'),
    ('volume-off', 'F0581'),
    ('arrow-up', 'F005D'),
    ('arrow-down', 'F0045'),
    ('arrow-expand-horizontal', 'F084E'),
    ('arrow-collapse-horizontal', 'F084C'),
    ('home-map-marker', 'F05F8'),
    ('plus', 'F0415'),
    ('minus', 'F0374'),
    # A player's input key: Home Assistant's icon for `source` (more-info-media_player, mdiLoginVariant), drawn the same
    # by exit-to-app in this font.
    ('exit-to-app', 'F0206'),
    # A player's power key (firmware 0.39.0): Home Assistant's icon for turn_on and turn_off (computeMediaControls).
    ('power-standby', 'F0906'),
    ('chevron-left', 'F0141'),
    ('chevron-right', 'F0142'),
    ('close', 'F0156'),
    # Back button of every overlay (firmware 0.2.37+).
    ('arrow-left', 'F004D'),
    ('sun-snowflake-variant', 'F1A79'),
    ('thermostat-auto', 'F1B17'),
    ('weather-fog', 'F0591'),
    ('weather-hail', 'F0592'),
    ('weather-lightning', 'F0593'),
    ('weather-lightning-rainy', 'F067E'),
    ('weather-pouring', 'F0596'),
    ('weather-snowy-rainy', 'F067F'),
    ('weather-sunset-down', 'F059B'),
    # "More" key on the CYD climate card: fan and swing (firmware 0.2.39+).
    ('dots-horizontal', 'F01D8'),
    # Swing row on the Guition climate card, Home Assistant's icon for swing modes (firmware 0.2.40+).
    ('arrow-oscillating', 'F1C91'),
    # The settings page on the screen itself (firmware 0.2.44+): its menu and the restart row.
    ('monitor', 'F0379'),
    ('information-outline', 'F02FD'),
    ('restart', 'F0709'),
    # Calibrate touch, beside it on a resistive panel (firmware 0.2.96+): the crosses the wizard draws.
    ('crosshairs', 'F01A3'),
    # A light that is off, as Home Assistant shows one without an icon of its own (firmware 0.2.53+).
    ('lightbulb-off', 'F0E4F'),
    # A media player's card and library (firmware 0.24.0+): shuffle and repeat, and an artist and a folder without a
    # picture of their own (media_library.CLASS_ICONS).
    ('shuffle-variant', 'F049F'),
    ('repeat', 'F0456'),
    ('repeat-once', 'F0458'),
    ('account-music', 'F0803'),
    ('folder', 'F024B'),
)

# Home Assistant's own default icons for the domains a tile or the top bar shows (frontend/get_icons, `entity_component`,
# Home Assistant 2026.9), with their state, range and device class variants and the few its frontend picks in code: a
# closed blind, a playing speaker, a battery at 40 %, a phone's tracker on the router (app 0.2.67). The firmware fonts carry them, so a tile shows the icon Home Assistant shows; a name missing here, such as
# one a later Home Assistant adds, keeps the screen's own default. Not pickable in the editor.
HA_DEFAULTS = (
    ('account-arrow-right', 'F0B53'),
    ('air-filter', 'F0D43'),
    ('air-humidifier', 'F1099'),
    ('air-humidifier-off', 'F1466'),
    ('alert-circle', 'F0028'),
    ('angle-acute', 'F0937'),
    ('arrow-bottom-left', 'F0042'),
    ('arrow-bottom-right', 'F0043'),
    ('arrow-down-box', 'F06C0'),
    ('arrow-left-right', 'F0E73'),
    ('arrow-right', 'F0054'),
    ('arrow-split-vertical', 'F093C'),
    ('arrow-top-left', 'F005B'),
    ('arrow-top-right', 'F005C'),
    ('arrow-up-box', 'F06C3'),
    ('audio-video', 'F093D'),
    ('audio-video-off', 'F11B6'),
    ('battery', 'F0079'),
    ('battery-10', 'F007A'),
    ('battery-20', 'F007B'),
    ('battery-30', 'F007C'),
    ('battery-40', 'F007D'),
    ('battery-50', 'F007E'),
    ('battery-60', 'F007F'),
    ('battery-70', 'F0080'),
    ('battery-80', 'F0081'),
    ('battery-90', 'F0082'),
    ('battery-alert', 'F0083'),
    ('battery-charging', 'F0084'),
    ('battery-outline', 'F008E'),
    ('battery-unknown', 'F0091'),
    ('blinds-horizontal', 'F1A2B'),
    ('blinds-horizontal-closed', 'F1A2C'),
    ('bluetooth', 'F00AF'),
    ('bluetooth-connect', 'F00B1'),
    ('brightness-5', 'F00DE'),
    ('brightness-7', 'F00E0'),
    ('button-pointer', 'F1B50'),
    ('car-battery', 'F010C'),
    ('car-coolant-level', 'F1019'),
    ('cash', 'F0114'),
    ('cast-connected', 'F0119'),
    ('cast-off', 'F078A'),
    ('check-circle', 'F05E0'),
    ('check-circle-outline', 'F05E1'),
    ('check-network-outline', 'F0C54'),
    ('checkbox-marked-circle', 'F0133'),
    ('circle-slice-8', 'F0AA5'),
    ('clock', 'F0954'),
    ('clock-start', 'F0155'),
    ('close-circle-outline', 'F015A'),
    ('close-network-outline', 'F0C5F'),
    ('compass-rose', 'F1382'),
    ('crop-portrait', 'F01A1'),
    ('crosshairs-question', 'F1136'),
    ('current-ac', 'F1480'),
    ('database', 'F01BC'),
    ('ear-hearing', 'F07C5'),
    ('eye', 'F0208'),
    ('eye-check', 'F0D04'),
    ('fan-off', 'F081D'),
    ('format-list-bulleted', 'F0279'),
    ('garage-open', 'F06DA'),
    ('gate', 'F0299'),
    ('gate-open', 'F116A'),
    ('home-outline', 'F06A1'),
    ('lan-connect', 'F0318'),
    ('lan-disconnect', 'F0319'),
    ('lightning-bolt', 'F140B'),
    ('lock-alert', 'F08EE'),
    ('lock-clock', 'F097F'),
    ('lock-open', 'F033F'),
    ('molecule', 'F0BAC'),
    ('molecule-co', 'F12FE'),
    ('motion-sensor-off', 'F1435'),
    ('music-note-off', 'F038A'),
    ('octagon', 'F03C3'),
    ('package', 'F03D3'),
    ('package-up', 'F03D5'),
    ('ph', 'F17C5'),
    ('pipe-valve', 'F184D'),
    ('power-plug-off', 'F06A6'),
    ('progress-clock', 'F0996'),
    ('projector-off', 'F1A23'),
    ('radioactive', 'F043C'),
    ('ray-vertex', 'F0445'),
    ('roller-shade', 'F1A6B'),
    # An automation (firmware 0.7.0+), as Home Assistant draws it on, off and unavailable.
    ('robot', 'F06A9'),
    ('robot-confused', 'F169F'),
    ('robot-off', 'F16A7'),
    # A remote (firmware 0.22.0+), as Home Assistant draws it on and off (remote/icons.json).
    ('remote', 'F0454'),
    ('remote-off', 'F0EC4'),
    ('script-text-play', 'F1727'),
    ('security', 'F0483'),
    ('shield', 'F0498'),
    ('shield-airplane', 'F06BB'),
    ('shield-lock', 'F099D'),
    ('shield-moon', 'F1828'),
    ('shield-off', 'F099E'),
    ('shield-outline', 'F0499'),
    ('sine-wave', 'F095B'),
    ('smoke-detector-alert', 'F192E'),
    ('smoke-detector-variant', 'F180B'),
    ('smoke-detector-variant-alert', 'F1930'),
    ('speaker-off', 'F04C4'),
    ('speaker-pause', 'F1B73'),
    ('speaker-play', 'F1B72'),
    ('speedometer', 'F04C5'),
    # A light's effects page (firmware 0.2.70+): Home Assistant's icons for an effect and WLED's palette, preset,
    # playlist and intensity; the speedometer above serves its speed.
    ('creation', 'F0674'),
    ('palette-outline', 'F0E0C'),
    ('playlist-play', 'F0411'),
    ('play-speed', 'F08FF'),
    ('brightness-6', 'F00DF'),
    ('spoon-sugar', 'F1429'),
    ('sprout-outline', 'F0E67'),
    ('square', 'F0764'),
    ('square-outline', 'F0763'),
    ('storage-tank', 'F1A75'),
    ('sun-wireless', 'F17FE'),
    ('television-off', 'F083B'),
    ('television-pause', 'F0F89'),
    ('television-play', 'F0ECF'),
    ('texture-box', 'F0FE6'),
    ('thermometer-lines', 'F0510'),
    ('toggle-switch-variant', 'F1A25'),
    ('toggle-switch-variant-off', 'F1A26'),
    ('transmission-tower', 'F0D3E'),
    ('vibrate', 'F0566'),
    ('water-boiler-off', 'F11B4'),
    ('water-off', 'F058D'),
    ('water-opacity', 'F1855'),
    ('weight', 'F05A1'),
    ('wifi', 'F05A9'),
    ('window-closed', 'F05AE'),
    ('window-open', 'F05B1'),
    # A humidifier's modes (firmware 0.42.0+), as Home Assistant draws them (humidifier/icons.json); a mode of the
    # integration's own takes Home Assistant's default, circle-medium.
    ('baby-carriage', 'F068F'),
    ('circle-medium', 'F09DE'),
    ('leaf', 'F032A'),
    ('power-sleep', 'F0904'),
    ('refresh-auto', 'F18F2'),
    ('rocket-launch', 'F14DE'),
)

# Pickable icons by name, and every glyph the firmware fonts contain.
ICONS = {name: (codepoint, label) for _, icons in GROUPS for name, codepoint, label in icons}
GLYPHS = {**{name: codepoint for name, (codepoint, _) in ICONS.items()}, **dict(FIXED), **dict(HA_DEFAULTS)}

# Mirrors runtime_tiles::icon_for() so the editor mockup shows what the screen draws.
DEFAULTS = {'light': 'lightbulb', 'climate': 'air-conditioner', 'humidifier': 'air-humidifier', 'vacuum': 'robot-vacuum', 'fan': 'fan',
            'cover': 'window-shutter', 'scene': 'sofa', 'script': 'sofa', 'automation': 'robot', 'remote': 'remote', 'sensor': 'gauge', 'binary_sensor': 'gauge',
            'timer': 'timer-outline', 'person': 'account', 'camera': 'cctv', 'image': 'cctv', 'screen': 'clock-outline'}
# The cards the screen brings itself: one icon per entity, not per domain.
BUILTIN_TILES = {'screen.clock': 'clock-outline', 'screen.settings': 'cog', 'screen.map': 'map-marker', **{f'screen.page_{n}': 'arrow-right' for n in range(1, 9)}}
FALLBACK = 'power'
# The large icon font of a card that takes the whole page (firmware 0.2.62+): what the screen draws on its own for a
# domain, a state or a built-in card, at 64 px on the Guition and 40 px on the CYD. Kept to these so the CYD's flash
# stays free; a chosen icon outside this set shows at its usual size in the big circle.
BIG_GLYPHS = tuple(dict.fromkeys(list(DEFAULTS.values()) + list(BUILTIN_TILES.values()) + ['lightbulb-off', 'robot-off', 'remote-off', 'air-humidifier-off', FALLBACK] +
                                 ['weather-sunny', 'weather-night', 'weather-cloudy', 'weather-partly-cloudy', 'weather-rainy',
                                  'weather-pouring', 'weather-snowy', 'weather-snowy-rainy', 'weather-fog', 'weather-hail',
                                  'weather-lightning', 'weather-lightning-rainy', 'weather-windy', 'alert-circle-outline',
                                  'weather-sunset-up', 'weather-sunset-down']))
CONTROL_GLYPHS = ('play', 'pause', 'stop', 'skip-next', 'skip-previous', 'volume-high', 'volume-off', 'arrow-up', 'arrow-down',
                  'blinds', 'blinds-open', 'arrow-expand-horizontal', 'arrow-collapse-horizontal', 'home-map-marker', 'plus', 'minus', 'chevron-left',
                  'chevron-right', 'close', 'power', 'fire', 'snowflake', 'sun-snowflake-variant', 'thermostat-auto', 'water-percent', 'fan',
                  'dots-horizontal')
WEATHER = {'sunny': 'weather-sunny', 'clear-night': 'weather-night', 'cloudy': 'weather-cloudy',
           'partlycloudy': 'weather-partly-cloudy', 'rainy': 'weather-rainy', 'pouring': 'weather-pouring',
           'snowy': 'weather-snowy', 'snowy-rainy': 'weather-snowy-rainy', 'fog': 'weather-fog', 'hail': 'weather-hail',
           'lightning': 'weather-lightning', 'lightning-rainy': 'weather-lightning-rainy', 'windy': 'weather-windy',
           'windy-variant': 'weather-windy', 'exceptional': 'alert-circle-outline'}

# Domains whose icon the screen draws from the state itself: a weather condition, the sun above or below the horizon.
OWN_ICON_DOMAINS = frozenset(('weather', 'sun', 'screen'))
# Home Assistant's icon resources ({'entity_component': ..., 'entity': ...}), set by the app when it reads them; empty keeps
# the tables of earlier releases.
HA_ICONS = {}

def use_ha_icons(resources):
    """The icon resources Home Assistant answered frontend/get_icons with, for every icon lookup of this app."""
    global HA_ICONS
    HA_ICONS = resources if isinstance(resources, dict) else {}

# A number as JavaScript's Number() reads a state: Home Assistant's frontend picks a range icon by it.
JS_NUMBER = re.compile(r'[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|[+-]?Infinity')

def js_number(text):
    """The number JavaScript's Number() reads from a state or a range key, None where it reads NaN (a blank text is 0)."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return 0.0
    return float(text.replace('Infinity', 'inf')) if JS_NUMBER.fullmatch(text) else None

def icon_for_state(state, spec):
    """Home Assistant's getIconFromTranslations: the icon for this state, else the range's icon for a number at or above its
    lowest step (the highest step not above it), else the default."""
    if not isinstance(spec, dict):
        return None
    states, ranges = spec.get('state'), spec.get('range')
    if state and isinstance(states, dict) and states.get(state):
        return states[state]
    value = js_number(state) if isinstance(ranges, dict) else None
    if value is not None:
        steps = sorted(step for step in map(js_number, ranges) if step is not None)
        below = [step for step in steps if step <= value]
        if below:
            step = below[-1]
            icon = ranges.get(str(int(step)) if step.is_integer() else repr(step))
            if icon:
                return icon
    return spec.get('default')

def state_icon(domain, state, attributes):
    """Home Assistant's stateIcon: the icons its frontend picks in code, before those of the integration."""
    if domain == 'update':
        return 'mdi:package-down' if attributes.get('in_progress') else 'mdi:package-up' if state == 'on' else 'mdi:package'
    if domain == 'device_tracker':
        source = attributes.get('source_type')
        if source == 'router':
            return 'mdi:lan-connect' if state == 'home' else 'mdi:lan-disconnect'
        if source in ('bluetooth', 'bluetooth_le'):
            return 'mdi:bluetooth-connect' if state == 'home' else 'mdi:bluetooth'
        return 'mdi:account-arrow-right' if state == 'not_home' else 'mdi:account'
    if domain == 'sun':
        return 'mdi:white-balance-sunny' if state == 'above_horizon' else 'mdi:weather-night'
    if domain == 'input_datetime':
        if not attributes.get('has_date'):
            return 'mdi:clock'
        if not attributes.get('has_time'):
            return 'mdi:calendar'
    return None

def ha_default_icon(entity_id, state, attributes, entry, icons):
    """The icon Home Assistant's frontend shows for an entity without one of its own (frontend/get_icons, app 0.2.67), in
    its order: the integration's icon for the entity's translation key, then the icon its frontend picks in code, then the
    domain's icon for the state's device class or else the domain's. The MDI name, or None when Home Assistant has none;
    `state` None is an entity without a state, which gets the defaults."""
    if not isinstance(icons, dict):
        return None
    domain = entity_id.split('.', 1)[0]
    entry = entry if isinstance(entry, dict) else {}
    attributes = attributes if isinstance(attributes, dict) else None
    icon = None
    if entry.get('platform') and entry.get('translation_key'):
        platform = ((icons.get('entity') or {}).get(entry['platform']) or {}).get(domain) or {}
        icon = icon_for_state(state, platform.get(entry['translation_key']))
    if not icon and attributes is not None and state is not None:
        icon = state_icon(domain, state, attributes)
    if not icon:
        component = (icons.get('entity_component') or {}).get(domain) or {}
        device_class = (attributes or {}).get('device_class')
        icon = icon_for_state(state, (isinstance(device_class, str) and component.get(device_class)) or component.get('_'))
    return icon[4:] if isinstance(icon, str) and icon.startswith('mdi:') else None

def default_glyph(entity_id, state, attributes, entry=None, icons=None):
    """Codepoint of Home Assistant's default icon when the firmware fonts carry it; None keeps the screen's own icon."""
    if entity_id.split('.', 1)[0] in OWN_ICON_DOMAINS:
        return None
    name = ha_default_icon(entity_id, state, attributes, entry, HA_ICONS if icons is None else icons)
    return GLYPHS.get(name) if name else None

def ha_icon(attributes):
    """Codepoint of Home Assistant's own `mdi:` icon when the firmware carries it, else None."""
    icon = attributes.get('icon') if isinstance(attributes, dict) else None
    return GLYPHS.get(icon[4:]) if isinstance(icon, str) and icon.startswith('mdi:') else None

def label_key(name):
    """The translation key of an icon's label ('ceiling-light'), or of a group's ('Media and music')."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

def editor():
    """Picker groups plus what the mockup needs to predict the screen's own icons; the labels in the editor's language."""
    return {'groups': [{'label': t(f'addon.icons.groups.{label_key(group)}'),
                        'icons': [{'name': name, 'cp': codepoint, 'label': t(f'addon.icons.names.{label_key(name)}')}
                                  for name, codepoint, _ in icons]}
                       for group, icons in GROUPS],
            'defaults': {domain: GLYPHS[name] for domain, name in DEFAULTS.items()}, 'fallback': GLYPHS[FALLBACK],
            'builtin': {entity: GLYPHS[name] for entity, name in BUILTIN_TILES.items()},
            'weather': {state: GLYPHS[name] for state, name in WEATHER.items()},
            'sun': {'above_horizon': GLYPHS['weather-sunset-down'], 'below_horizon': GLYPHS['weather-sunset-up']},
            # Glyphs of the direct controls on wide cards, so the mockup previews them.
            'controls': {name: GLYPHS[name] for name in CONTROL_GLYPHS}}
