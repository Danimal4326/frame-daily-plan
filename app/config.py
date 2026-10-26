"""Settings, stored as JSON in the data volume and edited through the web UI."""
import copy
import json
import os

DATA = os.environ.get('FRAME_PLAN_DATA', '/data')
CONFIG_FILE = os.path.join(DATA, 'config.json')

DEFAULTS = {
    'tv_ip': '',
    'timezone': os.environ.get('TZ') or 'UTC',
    'ui_lang': 'en',
    'plan_lang': 'en',
    # role "events" shows entries as appointments, "todos" puts every entry on the to-do list
    'calendars': [],
    # forecast from "open_meteo" (no key) or "pirateweather" (free key from pirateweather.net)
    'weather': {'enabled': True, 'name': '', 'lat': None, 'lon': None, 'radar': True, 'source': 'open_meteo',
                'pirateweather_key': '', 'main': 'high'},  # main: the big number, "high" (today's) or "now"
    'holidays': {'country': '', 'subdiv': ''},
    # time windows for the plan, e.g. a morning one every day and an evening one on weekdays
    'schedules': [{'name': 'Morning', 'enabled': True, 'start': '07:00', 'end': '10:00', 'days': [0, 1, 2, 3, 4, 5, 6]}],
    'dim_past_events': True,
    'background': 'artwork',  # "artwork": the picture the plan replaces, "default": bundled background
    'units': {'temperature': 'C', 'rain': 'mm'},
    'time_format': '24h',  # or "12h"
    # current conditions from a weather station, on top of the Open-Meteo forecast
    'station': {
        'source': 'none',  # none, home_assistant, mqtt, ambient, wunderground
        'home_assistant': {'url': '', 'token': '', 'temp_entity': '', 'rain_rate_entity': '', 'rain_today_entity': ''},
        'mqtt': {'host': '', 'port': 1883, 'username': '', 'password': '', 'temp_topic': '', 'rain_rate_topic': '',
                 'rain_today_topic': '', 'json_key': '', 'temp_unit': 'C', 'rain_unit': 'mm'},
        'ambient': {'api_key': '', 'application_key': '', 'mac': ''},
        'wunderground': {'station_id': '', 'api_key': ''},
    },
}

COLORS = ['green', 'blue', 'teal', 'purple', 'pink', 'orange', 'yellow', 'red', 'brown', 'grey']


def merge(base, stored):
    """Stored settings over the defaults, nested dicts key by key (new settings keep their default)."""
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def load():
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        if 'schedule' in stored and 'schedules' not in stored:  # one schedule, before there could be several
            stored['schedules'] = [{'name': 'Morning', **stored.pop('schedule')}]
        merge(cfg, stored)
    return cfg


def save(cfg):
    os.makedirs(DATA, exist_ok=True)
    tmp = CONFIG_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)
    os.chmod(tmp, 0o600)  # calendar links are secrets
    os.replace(tmp, CONFIG_FILE)
