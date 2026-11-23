"""Notifications in Home Assistant (its persistent_notification), the one way this app leaves one: for whoever does not
have the editor open. Each has an id of its own, so a new one replaces the one before and the app takes it away when
what it said is over. Telling Home Assistant never fails what asked for it."""
import logging

LOG = logging.getLogger('screen_manager')
TITLE = 'Tessera'


async def show(ha, notification_id, message):
    """Show (or replace) the notification `notification_id` with `message`."""
    await _call(ha, 'create', {'notification_id': notification_id, 'title': TITLE, 'message': message})


async def dismiss(ha, notification_id):
    """Take the notification `notification_id` away, if it is there."""
    await _call(ha, 'dismiss', {'notification_id': notification_id})


async def _call(ha, service, data):
    if ha is None or not hasattr(ha, 'request'):
        return
    try:
        await ha.request('call_service', domain='persistent_notification', service=service, service_data=data)
    except Exception as error:
        LOG.warning('Telling Home Assistant failed (%s, %s)', service, type(error).__name__)
