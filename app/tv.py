"""Talking to the Frame's Art Mode.

Frames differ by model year: 2017/2018 ones (art API 1.x) take an upload as one binary
WebSocket message and send thumbnails inline; newer ones (2.x, 4.x and up, e.g. 2024) use a
separate transfer socket, which is TLS on recent models. samsungframetv picks the right way
from the art API version, so this module only adds timeouts and logging around it.
"""
import collections
import concurrent.futures
import ipaddress
import os
import socket

import requests
from samsungframetv import SamsungTVWS

import config

NAME = 'Frame Daily Plan'
WAIT = 30  # seconds for any one reply from the TV, so a stuck TV fails instead of hanging


def _tv(ip, timeout):
    return SamsungTVWS(host=ip, port=8002, token_file=os.path.join(config.DATA, 'tv-token.txt'),
                       name=NAME, timeout=timeout)


def _bounded_transfers(a):
    """The library opens the thumbnail/upload socket without a read timeout; give it one."""
    open_socket = a._open_d2d_socket

    def opened(conn_info, secured=None):
        s = open_socket(conn_info, secured)
        s.settimeout(WAIT)
        return s
    a._open_d2d_socket = opened
    return a


def connect(ip):
    # The TV only asks "allow this device?" on the remote-control channel; an unapproved
    # client on the art channel just gets disconnected. Opening it first triggers the
    # prompt for a new device (and waits long enough for someone to press "Allow").
    auth = _tv(ip, 120)
    auth.open()
    auth.close()
    a = _bounded_transfers(_tv(ip, WAIT).art(timeout=WAIT))
    a.api_version = a.get_api_version()
    return a


def send_image(a, data, matte='none'):
    cid = a.upload(data, file_type='JPEG', matte=matte, portrait_matte=matte)
    if not cid:
        raise RuntimeError(f'the TV did not confirm the upload within {WAIT} s')
    return cid


def get_thumbnail(a, content_id):
    data = a.get_thumbnail(content_id)
    if isinstance(data, dict):
        data = next(iter(data.values()), None)
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        raise RuntimeError(f'no thumbnail received for {content_id}')
    return bytes(data)


def status(ip):
    a = connect(ip)
    return {'art_mode': a.get_artmode(), 'current': (a.get_current() or {}).get('content_id')}


def diagnose(ip):
    """Step by step, to see where a connection fails."""
    import time
    steps = []
    tv = _tv(ip, 120)
    for name, fn in (('rest', lambda: '{modelName} {PowerState}'.format_map(
                         collections.defaultdict(str, tv.rest_device_info()['device']))),
                     ('remote', lambda: (tv.open(), tv.close(), 'ok')[2]),
                     ('art', lambda: tv.art(timeout=WAIT).get_artmode()),
                     ('api', lambda: tv.art(timeout=WAIT).get_api_version())):
        t = time.time()
        try:
            steps.append((name, 'ok', str(fn())[:80], round(time.time() - t, 1)))
        except Exception as e:  # noqa: BLE001
            steps.append((name, 'FAIL', f'{type(e).__name__}: {e}'[:200], round(time.time() - t, 1)))
            break
    return steps


def _local_networks():
    """The /24 networks this machine is on (inside Docker this needs host networking)."""
    nets = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('192.0.2.1', 9))  # no packet is sent; this just picks the outgoing interface
        nets.add(ipaddress.ip_network(s.getsockname()[0] + '/24', strict=False))
        s.close()
    except OSError:
        pass
    return [n for n in nets if n.is_private]


def _probe(ip):
    try:
        info = requests.get(f'http://{ip}:8001/api/v2/', timeout=1.5).json().get('device', {})
    except Exception:  # noqa: BLE001
        return None
    if info.get('FrameTVSupport') != 'true':
        return None
    return {'ip': str(ip), 'name': info.get('name', '').replace('[TV]', '').strip() or 'Frame',
            'model': info.get('modelName', '')}


def discover():
    """Find Frames on the local network by asking every address for Samsung's device info."""
    hosts = [ip for net in _local_networks() for ip in net.hosts()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        return [r for r in pool.map(_probe, hosts) if r]
