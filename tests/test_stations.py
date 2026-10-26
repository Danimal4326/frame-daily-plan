import time

import pytest

import config
import plan_data
import stations


class Response:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def station_cfg(source, **fields):
    cfg = config.load()
    cfg['station']['source'] = source
    if source in cfg['station']:
        cfg['station'][source].update(fields)
    return cfg


def test_home_assistant_converts_by_unit(monkeypatch):
    states = {'sensor.t': ('59.0', '°F'), 'sensor.rate': ('0.1', 'in'), 'sensor.day': ('2.0', 'mm')}
    monkeypatch.setattr(stations.requests, 'get', lambda url, **kw: Response(
        {'state': states[url.rsplit('/', 1)[1]][0], 'attributes': {'unit_of_measurement': states[url.rsplit('/', 1)[1]][1]}}))
    r = stations.read(station_cfg('home_assistant', url='http://ha:8123/', token='x', temp_entity='sensor.t',
                                  rain_rate_entity='sensor.rate', rain_today_entity='sensor.day'))
    assert r == pytest.approx({'temp_c': 15.0, 'rain_rate_mm_h': 2.54, 'rain_today_mm': 2.0})


def test_home_assistant_unavailable_is_an_error(monkeypatch):
    monkeypatch.setattr(stations.requests, 'get', lambda url, **kw: Response({'state': 'unavailable', 'attributes': {}}))
    with pytest.raises(RuntimeError, match='unavailable'):
        stations.read(station_cfg('home_assistant', url='http://ha', token='x', temp_entity='sensor.t'))


def test_ambient_and_wunderground(monkeypatch):
    monkeypatch.setattr(stations.requests, 'get', lambda url, **kw: Response(
        [{'macAddress': 'AA:BB', 'lastData': {'tempf': 50, 'hourlyrainin': 0, 'dailyrainin': 1}}]))
    r = stations.read(station_cfg('ambient', api_key='k', application_key='a', mac='aa:bb'))
    assert r == pytest.approx({'temp_c': 10.0, 'rain_rate_mm_h': 0.0, 'rain_today_mm': 25.4})
    monkeypatch.setattr(stations.requests, 'get', lambda url, **kw: Response(
        {'observations': [{'metric': {'temp': 12.5, 'precipRate': 0.4, 'precipTotal': 3.1}}]}))
    r = stations.read(station_cfg('wunderground', station_id='KX1', api_key='k'))
    assert r == {'temp_c': 12.5, 'rain_rate_mm_h': 0.4, 'rain_today_mm': 3.1}


def test_mqtt_reads_cached_values_and_ignores_stale_ones(monkeypatch):
    monkeypatch.setattr(stations, 'mqtt_sync', lambda cfg: None)  # no broker in tests
    cfg = station_cfg('mqtt', host='broker', temp_topic='w/temp', rain_rate_topic='w/rate', temp_unit='F', rain_unit='in')
    monkeypatch.setitem(stations._mqtt, 'values', {'w/temp': ('68', time.time()), 'w/rate': ('0', time.time())})
    assert stations.read(cfg) == pytest.approx({'temp_c': 20.0, 'rain_rate_mm_h': 0.0, 'rain_today_mm': None})
    monkeypatch.setitem(stations._mqtt, 'values', {'w/temp': ('68', time.time() - 3600), 'w/rate': ('0', time.time())})
    with pytest.raises(RuntimeError, match='no message'):
        stations.read(cfg)


def test_station_over_forecast_and_units():
    w = plan_data.WORDS['en']
    forecast = {'icon': '⛅', 'max': 19.4, 'min': 11.6, 'text': 'Partly cloudy', 'hint': None}
    wx = plan_data.with_station(forecast, {'temp_c': 15.0, 'rain_rate_mm_h': 1.2}, w)
    assert wx['now'] == 15.0 and wx['text'] == 'Raining now' and wx['hint'] == w['hint_rain']
    assert plan_data.in_units(wx, {'units': {'temperature': 'F'}})[('max')] == 67
    assert plan_data.in_units(wx, {'units': {'temperature': 'F'}})['now'] == 59
    assert plan_data.in_units(wx, {'units': {'temperature': 'C'}})['max'] == 19
    dry = plan_data.with_station(forecast, {'temp_c': 15.0, 'rain_rate_mm_h': 0}, w)
    assert dry['text'] == 'Partly cloudy'
    assert plan_data.with_station(None, {'temp_c': 15.0, 'rain_rate_mm_h': None}, w)['max'] == 15.0  # station only
