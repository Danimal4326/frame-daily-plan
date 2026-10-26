import config
import web


def client():
    return web.app.test_client()


def test_fresh_install_shows_setup():
    html = client().get('/').get_data(as_text=True)
    assert 'Getting started' in html and 'Search the network' in html


def test_language_toggle():
    c = client()
    c.get('/lang/de')
    assert 'Erste Schritte' in c.get('/').get_data(as_text=True)
    c.get('/lang/en')
    assert config.load()['ui_lang'] == 'en'


def test_set_place_fills_location_timezone_and_holidays():
    r = client().post('/set-place', data={'label': 'Munich, Bavaria, Germany', 'lat': '48.137', 'lon': '11.575',
                                         'timezone': 'Europe/Berlin', 'country_code': 'DE'})
    assert r.status_code == 302
    cfg = config.load()
    assert cfg['weather']['lat'] == 48.137 and cfg['timezone'] == 'Europe/Berlin' and cfg['holidays']['country'] == 'DE'


def test_regions_and_health():
    assert 'BY' in client().get('/regions/de').get_json()['regions']
    assert client().get('/health').get_json() == {'ok': True}


def test_bad_timezone_is_ignored():
    c = client()
    c.post('/set-place', data={'label': 'X', 'lat': '1', 'lon': '2', 'timezone': 'Not/AZone', 'country_code': ''})
    assert config.load()['timezone'] != 'Not/AZone'


def test_nested_defaults_survive_old_config():
    cfg = config.merge(config.load(), {'station': {'source': 'mqtt', 'mqtt': {'host': 'b'}}})
    assert cfg['station']['mqtt']['host'] == 'b' and cfg['station']['mqtt']['port'] == 1883
    assert cfg['station']['home_assistant']['url'] == ''


def test_settings_round_trip_units_time_and_station():
    form = {'tv_ip': '192.168.1.50', 'timezone': 'America/Chicago', 'plan_lang': 'en', 'start': '07:00', 'end': '10:00',
            'time_format': '12h', 'unit_temperature': 'F', 'unit_rain': 'in', 'cal_count': '0',
            'station_source': 'home_assistant', 'st_home_assistant_url': 'http://ha:8123', 'st_home_assistant_token': 'abc',
            'st_home_assistant_temp_entity': 'sensor.outside_weather_temperature', 'st_mqtt_port': '1884'}
    assert client().post('/settings', data=form).status_code == 302
    cfg = config.load()
    assert cfg['time_format'] == '12h' and cfg['units'] == {'temperature': 'F', 'rain': 'in'}
    assert cfg['station']['source'] == 'home_assistant' and cfg['station']['home_assistant']['token'] == 'abc'
    assert cfg['station']['mqtt']['port'] == 1884
    html = client().get('/').get_data(as_text=True)
    assert 'Current conditions' in html and 'Add calendar' in html and 'sensor.outside_weather_temperature' in html


def test_us_place_defaults_to_fahrenheit_once():
    cfg = config.load()
    cfg.pop('units_chosen', None)
    cfg['units'] = {'temperature': 'C', 'rain': 'mm'}
    config.save(cfg)
    client().post('/set-place', data={'label': 'Austin', 'lat': '30.27', 'lon': '-97.74', 'timezone': 'America/Chicago',
                                      'country_code': 'US'})
    assert config.load()['units']['temperature'] == 'F' and config.load()['time_format'] == '12h'


def test_station_test_reports_errors_as_json():
    cfg = config.load()
    cfg['station']['source'] = 'home_assistant'
    cfg['station']['home_assistant'].update(url='', temp_entity='sensor.t')  # no address: fails without the network
    config.save(cfg)
    d = client().get('/station-test').get_json()
    assert d['ok'] is False and d['error']


def test_any_number_of_calendars_in_one_save():
    form = {'tv_ip': '', 'timezone': 'Europe/London', 'plan_lang': 'en', 'start': '07:00', 'end': '10:00'}
    for i in (0, 1, 2, 3, 7):  # rows added on the page get the next free numbers, gaps are fine
        form.update({f'cal_name{i}': f'Cal {i}', f'cal_url{i}': f'https://example.com/{i}.ics', f'cal_color{i}': 'teal'})
    form['cal_url5'] = ''  # an added row left empty is ignored
    client().post('/settings', data=form)
    assert [c['name'] for c in config.load()['calendars']] == ['Cal 0', 'Cal 1', 'Cal 2', 'Cal 3', 'Cal 7']
