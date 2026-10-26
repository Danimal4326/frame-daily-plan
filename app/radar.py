"""A small rain radar map around home: RainViewer's latest radar over a dark map.

RainViewer's free tiles go up to zoom 7. Its 512-pixel tiles at that zoom are as sharp as
256-pixel tiles at zoom 8, a region of a few hundred kilometres around home on the plan.
The map underneath is OpenStreetMap's (zoom 8, which lines up with those), darkened to suit
the plan. Map tiles are kept for a month, as OpenStreetMap's tile policy asks.
"""
import concurrent.futures
import datetime
import io
import json
import math
import os
import time
import urllib.request

from PIL import Image, ImageOps

import config

ZOOM, TILE = 7, 512  # radar; the map uses zoom 8 with 256-pixel tiles, the same pixels
INDEX = 'https://api.rainviewer.com/public/weather-maps.json'
MAP = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
MAP_CACHE = os.path.join(config.DATA, 'map-tiles')
MAP_MAX_AGE = 30 * 24 * 3600
CREDIT = '© OpenStreetMap contributors · RainViewer'
USER_AGENT = 'frame-daily-plan (+https://github.com/JustifyTechExpenses/frame-daily-plan)'


def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    return urllib.request.urlopen(req, timeout=15).read()


def map_tile(x, y):
    """One OpenStreetMap tile at zoom 8, from the cache when it is recent."""
    path = os.path.join(MAP_CACHE, f'8-{x}-{y}.png')
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < MAP_MAX_AGE:
        with open(path, 'rb') as f:
            return f.read()
    data = _get(MAP.format(z=8, x=x, y=y))
    os.makedirs(MAP_CACHE, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return data


def night(im):
    """The bright OpenStreetMap style turned dark and calm: inverted grey, tinted blue."""
    grey = ImageOps.invert(ImageOps.grayscale(im))
    return ImageOps.colorize(grey, black=(14, 18, 26), white=(150, 160, 178)).convert('RGBA')


def world_pixel(lat, lon):
    """Web Mercator pixel of lat/lon at ZOOM, with TILE-pixel tiles."""
    n = TILE * 2 ** ZOOM
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def fetch(lat, lon, size, tz):
    """The map (RGBA, `size`), centred on lat/lon, and the local time of the radar picture."""
    index = json.loads(_get(INDEX))
    frame = index['radar']['past'][-1]  # the newest; RainViewer no longer offers a forecast
    w, h = size
    cx, cy = world_pixel(lat, lon)
    x0, y0 = round(cx - w / 2), round(cy - h / 2)
    tiles = [(tx, ty) for tx in range(x0 // TILE, (x0 + w - 1) // TILE + 1)
             for ty in range(y0 // TILE, (y0 + h - 1) // TILE + 1)]
    wrap = 2 ** ZOOM  # across the date line

    def both(t):
        tx, ty = t
        rain = _get(f"{index['host']}{frame['path']}/{TILE}/{ZOOM}/{tx % wrap}/{ty}/2/1_1.png")
        base = Image.new('RGB', (TILE, TILE))
        for dx in (0, 1):  # four map tiles under one radar tile
            for dy in (0, 1):
                tile = map_tile((2 * tx + dx) % (2 * wrap), 2 * ty + dy)
                base.paste(Image.open(io.BytesIO(tile)).convert('RGB'), (dx * 256, dy * 256))
        return t, base, rain

    canvas = Image.new('RGBA', size, (14, 18, 26, 255))
    rain_layer = Image.new('RGBA', size, (0, 0, 0, 0))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for (tx, ty), base, rain in pool.map(both, tiles):
            pos = (tx * TILE - x0, ty * TILE - y0)
            canvas.paste(night(base), pos)
            rain_layer.paste(Image.open(io.BytesIO(rain)).convert('RGBA'), pos)
    canvas.alpha_composite(rain_layer)
    return canvas, datetime.datetime.fromtimestamp(frame['time'], tz)
