"""Where the screens reach this app (docs/PICTURES.md, "In ESP Screen Manager"): the address the links on the camera
port carry (picture_links). SCREEN_CAMERA_URL when it is set; else Home Assistant's own address on the LAN, on the
screen's own network where Home Assistant has several, with the port the Supervisor published for the camera port.
"""
import ipaddress
import logging
import os
import time

import picture_links

LOG = logging.getLogger(__name__)


async def published_port():
    """The host port screens reach this app on (GitHub #84): on Home Assistant OS the owner may publish 8098 under
    another port in the app's network settings, and the app still listens on 8098 inside its container. The
    Supervisor says which (`network` of /addons/self/info); SCREEN_CAMERA_PORT, or no Supervisor, keeps port()."""
    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if 'SCREEN_CAMERA_PORT' in os.environ or not token:
        return picture_links.port()
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get('http://supervisor/addons/self/info', headers={'Authorization': f'Bearer {token}'},
                                   timeout=aiohttp.ClientTimeout(total=10)) as response:
                info = await response.json()
        value = int(((info.get('data') or {}).get('network') or {}).get(f'{picture_links.PORT}/tcp'))
        if 0 < value < 65536:
            return value
    except Exception as error:  # noqa: BLE001
        LOG.info('Reading the published camera port failed (%s)', type(error).__name__)
    return picture_links.port()


async def base_url(request, cache={}, *, near=None):
    """http://<address>:<port> where screens reach this app: SCREEN_CAMERA_URL when set, else Home Assistant's own LAN
    address (the add-on's port is published on the host). `request` is HomeAssistant.request. `near` is the screen's own
    address: a Home Assistant on two networks gives each screen its address on the screen's own network (GitHub #276),
    and the default adapter's to a screen on none of them."""
    override = os.environ.get('SCREEN_CAMERA_URL', '').rstrip('/')
    if override:
        return override
    now = time.monotonic()
    if not (cache.get('url') and now - cache.get('at', 0) < 600):
        await _read_lan(request, cache, now)
    if not cache.get('url'):
        return None
    host = lan_address(cache.get('adapters') or (), near)
    return f'http://{host}:{cache["port"]}' if host else cache['url']


def lan_address(adapters, near):
    """Of Home Assistant's IPv4 addresses [(address, prefix)], the one whose network holds the address `near`, or None."""
    try:
        screen = ipaddress.IPv4Address(near) if near else None
    except ValueError:
        return None
    for address, prefix in adapters if screen else ():
        try:
            if prefix is not None and screen in ipaddress.IPv4Interface(f'{address}/{prefix}').network:
                return address
        except ValueError:
            continue
    return None


async def _read_lan(request, cache, now):
    """Home Assistant's addresses into `cache`: the default adapter's first address (the one link every screen got
    before GitHub #276), and every IPv4 address with its prefix, read again every ten minutes."""
    host, adapters = None, []
    try:
        network = await request('network')
        for adapter in (network or {}).get('adapters', []):
            found = [(item.get('address'), item.get('network_prefix')) for item in adapter.get('ipv4') or [] if item.get('address')]
            adapters += found
            if host is None and adapter.get('default') and found:
                host = found[0][0]
    except Exception as error:  # noqa: BLE001
        LOG.info('Reading the network adapters failed (%s)', type(error).__name__)
    if host is None:
        try:
            from urllib.parse import urlparse
            host = urlparse((await request('network/url') or {}).get('internal') or '').hostname
        except Exception as error:  # noqa: BLE001
            LOG.info('Reading the internal URL failed (%s)', type(error).__name__)
    if not host:
        # Home Assistant did not say this time (busy, restarting): the address it gave before still stands (app 0.4.51).
        # Without it a page's pictures got an answer without a link, and a page of maps then stayed without its maps.
        return
    port = await published_port()
    cache.update(url=f'http://{host}:{port}', port=port, adapters=adapters, at=now)
