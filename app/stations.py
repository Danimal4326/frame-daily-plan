"""Current conditions from the family's own weather station, on top of the forecast.

Every source returns the same metric reading, so unit conversion and the plan's rules
live in one place: {'temp_c': …, 'rain_rate_mm_h': …, 'rain_today_mm': …}, None where a
value is not set up. Sources: Home Assistant, MQTT, Ambient Weather and Weather Underground.
"""
import copy
import json
import threading
import time
import uuid

import paho.mqtt.client as mqtt
import requests

import config
import home_assistant as ha

SOURCES = ['none', 'open_meteo', 'home_assistant', 'mqtt', 'ambient', 'wunderground']
MAX_AGE = 15 * 60  # older MQTT values are ignored: the station is probably offline
MM_PER_INCH = 25.4


def f_to_c(f):
    return (f - 32) * 5 / 9


def c_to_f(c):
    return c * 9 / 5 + 32


def to_c(value, unit):
    """°F, F, °C, C or K, as Home Assistant and MQTT settings name them."""
    v, u = float(value), (unit or '').replace('°', '').strip().upper()
    return f_to_c(v) if u == 'F' else v - 273.15 if u == 'K' else v


def to_mm(value, unit):
    """in, in/h, mm, mm/h: amounts and rates convert the same way."""
    v, u = float(value), (unit or '').split('/')[0].strip().lower()
    return v * MM_PER_INCH if u in ('in', 'inch', 'inches', '"') else v


def _opt(value, convert, *args):
    return None if value is None else convert(value, *args)


def open_meteo(cfg):
    """No station: Open-Meteo's current conditions for the plan's place."""
    loc = cfg['weather']
    if loc.get('lat') is None or loc.get('lon') is None:
        raise RuntimeError('no place set for the weather')
    r = requests.get('https://api.open-meteo.com/v1/forecast', timeout=15, params={
        'latitude': loc['lat'], 'longitude': loc['lon'], 'timezone': cfg['timezone'],
        'current': 'temperature_2m,precipitation', 'daily': 'precipitation_sum', 'forecast_days': 1})
    r.raise_for_status()
    d = r.json()
    # "precipitation" is the last 15 minutes; only whether it is raining matters for the plan
    return {'temp_c': d['current']['temperature_2m'], 'rain_rate_mm_h': d['current']['precipitation'] * 4,
            'rain_today_mm': d['daily']['precipitation_sum'][0]}


def home_assistant(cfg):
    """The station's sensors in Home Assistant (its address and token are the app's Home Assistant settings)."""
    s = cfg['station']['home_assistant']

    def value(entity, convert):
        return convert(*ha.state(cfg, entity)) if entity else None
    return {'temp_c': value(s['temp_entity'], to_c), 'rain_rate_mm_h': value(s['rain_rate_entity'], to_mm),
            'rain_today_mm': value(s['rain_today_entity'], to_mm)}


def ambient(s):
    r = requests.get('https://rt.ambientweather.net/v1/devices', timeout=15,
                     params={'apiKey': s['api_key'], 'applicationKey': s['application_key']})
    r.raise_for_status()
    devices = [d for d in r.json() if not s.get('mac') or d.get('macAddress', '').lower() == s['mac'].strip().lower()]
    if not devices:
        raise RuntimeError('no station found for these keys')
    last = devices[0].get('lastData', {})  # Ambient always reports °F and inches
    return {'temp_c': _opt(last.get('tempf'), to_c, 'F'), 'rain_rate_mm_h': _opt(last.get('hourlyrainin'), to_mm, 'in'),
            'rain_today_mm': _opt(last.get('dailyrainin'), to_mm, 'in')}


def wunderground(s):
    r = requests.get('https://api.weather.com/v2/pws/observations/current', timeout=15,
                     params={'stationId': s['station_id'], 'apiKey': s['api_key'], 'format': 'json', 'units': 'm',
                             'numericPrecision': 'decimal'})
    r.raise_for_status()
    if r.status_code == 204:
        raise RuntimeError(f"station {s['station_id']} has no recent observation")
    m = r.json()['observations'][0]['metric']
    return {'temp_c': m.get('temp'), 'rain_rate_mm_h': m.get('precipRate'), 'rain_today_mm': m.get('precipTotal')}


# MQTT stations publish every few seconds to a minute, usually not retained, so a background
# client keeps the latest value of each topic and the plan reads from that.
_mqtt = {'settings': None, 'client': None, 'values': {}}
_mqtt_lock = threading.Lock()


def _topics(s):
    return [t for t in (s.get('temp_topic'), s.get('rain_rate_topic'), s.get('rain_today_topic')) if t]


def mqtt_sync(cfg):
    """(Re)connect when the MQTT settings change, disconnect when another source is chosen."""
    st = cfg['station']
    wanted = st['mqtt'] if st['source'] == 'mqtt' and st['mqtt'].get('host') else None
    with _mqtt_lock:
        if wanted == _mqtt['settings']:
            return
        if _mqtt['client']:
            _mqtt['client'].loop_stop()
            _mqtt['client'].disconnect()
        _mqtt.update(settings=copy.deepcopy(wanted), client=None, values={})
        if not wanted:
            return
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'frame-daily-plan-{uuid.uuid4().hex[:8]}')
        if wanted.get('username'):
            client.username_pw_set(wanted['username'], wanted.get('password') or None)
        values = _mqtt['values']
        client.on_connect = lambda c, userdata, flags, rc, props: [c.subscribe(t) for t in _topics(wanted)]
        client.on_message = lambda c, userdata, msg: values.__setitem__(
            msg.topic, (msg.payload.decode('utf-8', 'replace'), time.time()))
        client.connect_async(wanted['host'], int(wanted.get('port') or 1883))
        client.loop_start()  # reconnects by itself
        _mqtt['client'] = client


def mqtt_reading(s):
    def value(topic, convert, unit):
        if not topic:
            return None
        payload, at = _mqtt['values'].get(topic, (None, 0))
        if payload is None:
            raise RuntimeError(f'no message on {topic} yet')
        if time.time() - at > MAX_AGE:
            raise RuntimeError(f'no message on {topic} for {MAX_AGE // 60} minutes')
        if s.get('json_key'):
            payload = json.loads(payload)[s['json_key']]
        return convert(payload, unit)
    return {'temp_c': value(s['temp_topic'], to_c, s.get('temp_unit')),
            'rain_rate_mm_h': value(s['rain_rate_topic'], to_mm, s.get('rain_unit')),
            'rain_today_mm': value(s['rain_today_topic'], to_mm, s.get('rain_unit'))}


def read(cfg):
    """The station's reading, or None when no station is set up."""
    st = cfg.get('station') or {}
    source = st.get('source', 'none')
    if source == 'mqtt':
        mqtt_sync(cfg)
        return mqtt_reading(st['mqtt'])
    if source in ('open_meteo', 'home_assistant'):
        return {'open_meteo': open_meteo, 'home_assistant': home_assistant}[source](cfg)
    fn = {'ambient': ambient, 'wunderground': wunderground}.get(source)
    return fn(st[source]) if fn else None


def watcher():
    while True:
        try:
            mqtt_sync(config.load())
        except Exception as e:  # noqa: BLE001  e.g. a broker name that does not resolve
            print(f'MQTT: {e}', flush=True)
        time.sleep(30)


def start_watcher():
    threading.Thread(target=watcher, name='mqtt', daemon=True).start()
