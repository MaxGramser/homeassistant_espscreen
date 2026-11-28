"""What a troubleshooting report leaves out (reports.py, app 0.4.91): the rules Home Assistant's own diagnostics follow
(`async_redact_data`: values under a sensitive key become **REDACTED**), and what a log line needs on top of that, since
a log carries addresses and names as free text: IPv4 and IPv6 addresses, MACs in both forms, Wi-Fi names, passwords
and keys after their word, coordinates, and the screen's own names, which become `<screen>` so the lines stay readable
and can still be followed from one file to the next. Entity ids are left alone: they are what a tile's trouble is about,
and the report only holds the ones of this screen's own pages when its owner asked for the fuller report."""
import re

REDACTED = '**REDACTED**'
# Keys whose value never leaves, at any depth of a JSON document (Home Assistant's own list for the ESPHome integration,
# plus what its config entry and storage carry in the open: the host, the MAC as unique_id, coordinates).
SENSITIVE_KEYS = frozenset({
    'noise_psk', 'password', 'mac_address', 'bluetooth_mac_address', 'host', 'unique_id', 'address', 'ip', 'ip_address',
    'api_key', 'encryption_key', 'key', 'token', 'access_token', 'refresh_token', 'ssid', 'bssid', 'psk', 'secret',
    'latitude', 'longitude', 'elevation', 'external_url', 'internal_url', 'wifi_password', 'wifi_ssid', 'ota_password',
    'zwave_home_id', 'serial', 'serial_number',
})

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
# A word that names a secret, then its value to the end of the token: `password: x`, `key=x`, `"noise_psk": "x"`,
# `ssid: 'Home'`. `key` alone is kept narrow (api key, encryption key, `key:` of a YAML `encryption:` block), so a tile's
# `key` in a layout is left as it is.
SECRET_WORDS = re.compile(
    r'(?i)\b((?:wifi_|ota_|api_|noise_|encryption[ _])?(?:password|psk|ssid|bssid|secret|token|access_token|api_key)'
    r'|encryption:\s*key|(?<=\n)\s*key|(?<=\s)key)("?\s*[:=]\s*"?)(?!\[redacted\])([^\s"\',}\]]+)')
IPV4 = re.compile(r'(?<![\w.])(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}(?![\w.])')
# Six pairs with : or - between them (a time has three groups, a version has dots), or twelve hex letters in a row.
MAC = re.compile(r'(?i)(?<![\w:-])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![\w:-])|(?<![0-9a-f])[0-9a-f]{12}(?![0-9a-f])')
# Candidate IPv6: groups of hex with colons; accepted only with `::` or a letter in it, so a clock time stays.
IPV6 = re.compile(r'(?i)(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])')
COORDINATE = re.compile(r'(?i)\b(latitude|longitude)(\s*[:=]\s*"?)-?\d+(?:\.\d+)?')


def redact_text(text, names=(), values=()):
    """A log, a YAML or any text with its secrets, addresses and the screen's names taken out. `names` are the screen's
    own names (device, friendly, node, entry title), `values` extra secret values known to the app."""
    if not isinstance(text, str):
        text = str(text)
    text = ANSI.sub('', text)
    for value in sorted({v for v in values if isinstance(v, str) and len(v) >= 3}, key=len, reverse=True):
        text = text.replace(value, '[redacted]')
    text = SECRET_WORDS.sub(lambda m: f'{m.group(1)}{m.group(2)}[redacted]', text)
    text = COORDINATE.sub(lambda m: f'{m.group(1)}{m.group(2)}[redacted]', text)
    text = MAC.sub('[mac]', text)
    text = IPV6.sub(lambda m: '[ip]' if ('::' in m.group(0) or re.search(r'[a-f]', m.group(0), re.I)) else m.group(0), text)
    text = IPV4.sub(lambda m: m.group(0) if _looks_like_version(m, text) else '[ip]', text)
    for name in sorted({n for n in names if isinstance(n, str) and len(n) >= 3}, key=len, reverse=True):
        text = re.sub(re.escape(name), '<screen>', text, flags=re.IGNORECASE)
    return text


def _looks_like_version(match, text):
    """`1.2.3.4` right after a `v` or a word that says version is a version, not an address (a plugin's, ESP-IDF's)."""
    before = text[max(0, match.start() - 12):match.start()].lower()
    return before.endswith(('v', 'version ', 'version: ', 'idf ')) or '127.0.0.1' == match.group(0)


def redact_data(data, keys=SENSITIVE_KEYS, names=(), values=()):
    """A JSON document the way Home Assistant's diagnostics redact one, then every string in it through redact_text."""
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if str(key).lower() in keys and value not in (None, '', [], {}):
                out[key] = REDACTED
            else:
                out[key] = redact_data(value, keys, names, values)
        return out
    if isinstance(data, list):
        return [redact_data(item, keys, names, values) for item in data]
    if isinstance(data, str):
        return redact_text(data, names, values)
    return data
