import datetime
import os
import time
import zoneinfo

import icalendar
from PIL import Image, ImageDraw

import jobs
import plan_data
import render

HERE = os.path.dirname(__file__)
TZ = zoneinfo.ZoneInfo('Europe/London')
CFG = {'timezone': 'Europe/London', 'plan_lang': 'en', 'calendars': [], 'dim_past_events': True,
       'weather': {'enabled': False}, 'holidays': {'country': '', 'subdiv': ''}, 'background': 'default',
       'tv_ip': '192.168.1.50',
       'schedules': [{'name': 'Morning', 'enabled': True, 'start': '07:00', 'end': '10:00', 'days': [0, 1, 2, 3, 4]}]}


def cal():
    with open(os.path.join(HERE, 'sample.ics'), 'rb') as f:
        return icalendar.Calendar.from_ical(f.read())


def test_calendar_entries():
    events, todos = plan_data.calendar_entries(cal(), 'green', datetime.date(2026, 10, 27), TZ, plan_data.WORDS['en'])
    titles = [(e['start'], e['title']) for e in sorted(events, key=lambda e: e['sort'])]
    assert ('All day', 'Project week') in titles
    assert ('07:15', 'Breakfast together') in titles  # whitespace collapsed
    assert ('16:00', 'Piano lesson') in titles      # weekly recurrence expanded
    assert todos == ['Tidy up your room']           # "To-do:" prefix moves it to the list


def test_todo_calendar_takes_every_entry():
    _, todos = plan_data.calendar_entries(cal(), 'orange', datetime.date(2026, 10, 27), TZ, plan_data.WORDS['en'], True)
    assert len(todos) == 4


def test_holidays_in_plan_language():
    cfg = dict(CFG, holidays={'country': 'DE', 'subdiv': 'BY'})
    xmas = datetime.date(2026, 12, 25)
    en = plan_data.holiday_entries(dict(cfg, plan_lang='en'), xmas, plan_data.WORDS['en'])
    de = plan_data.holiday_entries(dict(cfg, plan_lang='de'), xmas, plan_data.WORDS['de'])
    assert en[0]['start'] == 'Holiday' and 'Christmas' in en[0]['title']
    assert de[0]['start'] == 'Feiertag' and 'Weihnacht' in de[0]['title']


def test_schedule_rules():
    d = lambda h, m=0, day=27: datetime.datetime(2026, 10, day, h, m, tzinfo=TZ)  # 27th = Tuesday
    today = '2026-10-27 07:00'  # the window the plan was shown in
    assert jobs._due(CFG, {}, d(6, 59)) is None
    assert jobs._due(CFG, {}, d(7)) == 'show'
    assert jobs._due(CFG, {'shown_on': today, 'restore_due': True}, d(8)) is None
    assert jobs._due(CFG, {'shown_on': today, 'restore_due': True}, d(10)) == 'restore'
    assert jobs._due(CFG, {'shown_on': today, 'restore_due': False}, d(15)) is None  # manual message stays
    assert jobs._due(CFG, {'restore_due': True}, d(6, day=28)) == 'restore'           # TV was off at 10
    assert jobs._due(CFG, {}, d(8, day=25)) is None                                   # Sunday not scheduled
    assert jobs._due(dict(CFG, tv_ip=''), {}, d(8)) is None                          # not set up yet


def test_render_both_languages(tmp_path):
    now = datetime.datetime(2026, 10, 27, 8, 0, tzinfo=TZ)
    for lang in ('en', 'de', 'en_US'):
        out = tmp_path / f'demo-{lang}.jpg'
        render.render(plan_data.demo(CFG, now, lang), str(out))
        assert Image.open(out).size == (3840, 2160)


def test_text_and_fit(tmp_path):
    render.render_text('Grandma picks you up at 4 pm today', str(tmp_path / 't.jpg'))
    Image.new('RGB', (600, 1200), (200, 100, 50)).save(tmp_path / 'tall.jpg')
    for mode in ('crop', 'fit'):
        render.fit_artwork(str(tmp_path / 'tall.jpg'), str(tmp_path / f'{mode}.jpg'), mode)
        assert Image.open(tmp_path / f'{mode}.jpg').size == (3840, 2160)


def test_twelve_hour_clock():
    render.TWELVE_HOUR = True
    try:
        assert render.clock('07:15') == '7:15 AM'
        assert render.clock('12:00') == '12:00 PM'
        assert render.clock('00:30') == '12:30 AM'
        assert render.clock('19:45') == '7:45 PM'
        assert render.clock('All day') == 'All day'
    finally:
        render.TWELVE_HOUR = False
    assert render.clock('19:45') == '19:45'


def test_render_12h_fahrenheit_with_station(tmp_path):
    cfg = dict(CFG, time_format='12h', units={'temperature': 'F', 'rain': 'in'})
    data = plan_data.demo(cfg, datetime.datetime(2026, 10, 27, 8, 0, tzinfo=TZ), 'en')
    assert data['weather']['max'] == 66  # 19 °C
    data['weather']['now'] = 59
    out = tmp_path / 'us.jpg'
    render.render(data, str(out))
    assert Image.open(out).size == (3840, 2160)


def test_every_colour_has_a_tone_and_names():
    import config
    import i18n
    for c in config.COLORS:
        assert c in render.COLORS
        assert all(c in i18n.TEXT[lang]['colors'] for lang in i18n.TEXT)


def test_morning_and_evening_windows():
    evening = {'name': 'Evening', 'enabled': True, 'start': '18:00', 'end': '21:00', 'days': [0, 1, 2, 3, 4]}
    weekend = {'name': 'Weekend', 'enabled': True, 'start': '09:00', 'end': '11:00', 'days': [5, 6]}
    cfg = dict(CFG, schedules=CFG['schedules'] + [evening, weekend])
    d = lambda h, day=27: datetime.datetime(2026, 10, day, h, tzinfo=TZ)  # 27th = Tuesday, 31st = Saturday
    morning_shown = {'shown_on': '2026-10-27 07:00', 'restore_due': True}
    assert jobs._due(cfg, morning_shown, d(8)) is None
    assert jobs._due(cfg, morning_shown, d(12)) == 'restore'
    assert jobs._due(cfg, {'shown_on': '2026-10-27 07:00', 'restore_due': False}, d(18)) == 'show'  # fresh evening plan
    assert jobs._due(cfg, {'shown_on': '2026-10-27 18:00'}, d(19)) is None
    assert jobs._due(cfg, {}, d(7, day=31)) is None and jobs._due(cfg, {}, d(9, day=31)) == 'show'
    assert jobs.active_schedule(cfg, d(9, day=31))['name'] == 'Weekend'
    assert jobs._due(dict(cfg, schedules=[dict(evening, enabled=False)]), {}, d(18)) is None


def test_us_english_plan():
    assert plan_data.words({'plan_lang': 'en_US'})['hint_cool'] == 'Bring a sweater or jacket'
    assert render.LABELS['en_US']['initials'] == 'SMTWTFS'
    us = plan_data.holiday_entries(dict(CFG, plan_lang='en_US', holidays={'country': 'US', 'subdiv': ''}),
                                   datetime.date(2026, 11, 26), plan_data.WORDS['en_US'])
    assert 'Thanksgiving' in us[0]['title']
    assert 'Practice math' in plan_data.demo(CFG, datetime.datetime(2026, 10, 27, 8, tzinfo=TZ), 'en_US')['todos']


def test_layout_with_outlook_and_radar(tmp_path):
    now = datetime.datetime(2026, 10, 27, 8, 0, tzinfo=TZ)
    data = plan_data.demo(dict(CFG, units={'temperature': 'F'}), now, 'en')
    assert [o['max'] for o in data['weather']['outlook']] == [63, 70, 68]  # °C demo values in °F
    data['radar'] = {'image': Image.new('RGBA', render.RADAR_SIZE, (30, 60, 90, 255)), 'time': '07:05', 'credit': 'x'}
    for d in (data, dict(data, weather=None, radar=None)):  # without weather: tomorrow keeps the right column
        out = tmp_path / 'layout.jpg'
        render.render(d, str(out))
        assert Image.open(out).size == (3840, 2160)


def test_today_and_tomorrow_type_shrinks_to_fit():
    d = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    ev = lambda n: [{'start': '08:00', 'title': f'Event {i}'} for i in range(n)]  # noqa: E731
    render.L = render.LABELS['en']
    room = render.H - 2 * render.M - render.CENTER_HEAD - 30
    assert render.day_scale(d, ev(3), ev(2), 1040, room) == 1.0  # a quiet day keeps the big type
    busy = render.day_scale(d, ev(5), ev(3), 1040, room)
    assert render.SCALES[-1] < busy < 1.0
    assert render.day_scale(d, ev(40), ev(10), 1040, room) == render.SCALES[-1]
    # Too many even for the smallest type: today is cut short, two of tomorrow's still fit.
    scale = render.SCALES[-1]
    keep = render.list_height(d, ev(2), 1040, scale) + round(80 * scale)
    assert render.CENTER_HEAD + round(render.TOMORROW_HEAD * scale) + keep < room


def test_radar_map_from_tiles(monkeypatch, tmp_path):
    import io
    import radar

    def png(color, size):
        buf = io.BytesIO()
        Image.new('RGBA', (size, size), color).save(buf, 'PNG')
        return buf.getvalue()
    calls = []

    def get(url):
        calls.append(url)
        if url == radar.INDEX:
            return b'{"host": "https://tiles", "radar": {"past": [{"time": 1793045400, "path": "/v2/radar/x"}]}}'
        return png((0, 0, 255, 128), 512) if 'tiles' in url else png((240, 240, 240, 255), 256)
    monkeypatch.setattr(radar, '_get', get)
    monkeypatch.setattr(radar, 'MAP_CACHE', str(tmp_path))
    image, at = radar.fetch(41.85, -87.65, render.RADAR_SIZE, TZ)
    assert image.size == render.RADAR_SIZE and at.tzinfo is TZ
    map_calls = len([c for c in calls if 'openstreetmap' in c])
    radar.fetch(41.85, -87.65, render.RADAR_SIZE, TZ)
    assert len([c for c in calls if 'openstreetmap' in c]) == map_calls  # map tiles come from the cache


def test_pirate_weather_forecast(monkeypatch):
    import io
    import json
    start = datetime.datetime(2026, 10, 27, tzinfo=TZ)
    days = [{'time': int((start + datetime.timedelta(days=i)).timestamp()), 'icon': icon, 'temperatureHigh': hi,
             'temperatureLow': lo, 'precipProbability': p}
            for i, (icon, hi, lo, p) in enumerate([('light-rain', 14.2, 8.1, 0.62), ('clear-day', 18, 9, 0),
                                                   ('mostly-cloudy-day', 16, 10, 0.1), ('thunderstorm', 20, 12, 0.8),
                                                   ('snow', 1, -3, 0.9)])]
    seen = []

    def urlopen(url, timeout):
        seen.append(url)
        return io.BytesIO(json.dumps({'daily': {'data': days}, 'currently': {
            'icon': 'mostly-cloudy-night', 'temperature': 13.4}}).encode())
    monkeypatch.setattr(plan_data.urllib.request, 'urlopen', urlopen)
    cfg = dict(CFG, weather={'enabled': True, 'lat': 41.85, 'lon': -87.65, 'source': 'pirateweather', 'pirateweather_key': 'k1'})
    wx = plan_data.weather(cfg, datetime.date(2026, 10, 27), plan_data.WORDS['en'])
    assert 'pirateweather.net/forecast/k1/41.85,-87.65' in seen[0] and 'units=si' in seen[0]
    assert (wx['icon'], wx['text'], wx['max'], wx['hint']) == ('🌦️', 'Light rain', 14.2, 'Bring a rain jacket')
    assert [(o['icon'], o['rain']) for o in wx['outlook']] == [('☀️', 0), ('🌥️', 10), ('⛈️', 80)]  # 3 days, not 4
    de = plan_data.weather(dict(cfg, plan_lang='de'), datetime.date(2026, 10, 27), plan_data.WORDS['de'])
    assert de['text'] == 'Leichter Regen'

    # With "now" as the big number, the sky is the one now, in its night version after dark.
    now = plan_data.weather(dict(cfg, weather=dict(cfg['weather'], main='now')), datetime.date(2026, 10, 27),
                            plan_data.WORDS['en'])
    assert (now['icon'], now['text'], now['now'], now['hint']) == ('☁️', 'Mostly cloudy', 13.4, 'Bring a rain jacket')
    assert now['day_text'] == 'Light rain'


def test_big_temperature_choice():
    render.L = render.LABELS['en']
    wx = {'max': 66, 'min': 50, 'now': 58}
    assert render.temperatures(dict(wx, main='high')) == (66, ['now 58°', 'down to 50° tonight'])
    assert render.temperatures(dict(wx, main='now')) == (58, ['High 66° · Low 50°'])
    assert render.temperatures(dict(wx, main='now', day_text='Sunny')) == (58, ['Sunny today', 'High 66° · Low 50°'])
    assert render.temperatures(dict(wx, main='now', now=None)) == (66, ['down to 50° tonight'])  # no reading: the high
    assert render.temperatures({'max': None, 'min': None, 'now': 58}) == (58, [])  # station only


def test_clear_night_is_not_sunny():
    assert plan_data.at_night({'icon': '☀️', 'text': ('Sonnig', 'Sunny')}) == {'icon': '🌙', 'text': ('Klar', 'Clear')}
    assert plan_data.at_night({'icon': '🌧️', 'text': ('Regen', 'Rain')})['icon'] == '🌧️'


def test_observances_and_month_emoji(tmp_path):
    cfg = dict(CFG, plan_lang='en_US', holidays={'country': 'US', 'subdiv': 'IL', 'observances': True})
    halloween = datetime.date(2026, 10, 31)
    assert plan_data.holiday_entries(cfg, halloween, plan_data.WORDS['en_US'])[0]['title'] == 'Halloween'
    off = dict(cfg, holidays=dict(cfg['holidays'], observances=False))
    assert plan_data.holiday_entries(off, halloween, plan_data.WORDS['en_US']) == []
    data = plan_data.build(cfg, datetime.datetime(2026, 10, 12, 8, tzinfo=TZ))  # Columbus Day is today
    assert data['holiday_marks'] == {12: '⛵', 31: '🎃'}
    assert plan_data.holiday_emoji('Thanksgiving Day') == '🦃' and plan_data.holiday_emoji('Erster Weihnachtstag') == '🎄'
    assert plan_data.holiday_emoji('Casimir Pulaski Day') == '⭐'
    render.render(dict(data, background=None), str(tmp_path / 'marks.jpg'))


def test_demo_has_stand_in_holidays_and_radar(monkeypatch):
    now = datetime.datetime(2026, 10, 26, 8, tzinfo=TZ)
    assert plan_data.demo(CFG, now, 'en_US')['holiday_marks'] == {31: '🎃'}
    assert plan_data.demo(CFG, now, 'de')['holiday_marks'] == {}
    import radar
    monkeypatch.setattr(radar, 'fetch', lambda lat, lon, size, tz: (Image.new('RGBA', size), now))
    data = plan_data.demo_radar(plan_data.demo(CFG, now, 'en_US'), CFG, 'en_US')
    assert data['radar']['time'] == '08:00'
    off = dict(CFG, weather={'radar': False})
    assert 'radar' not in plan_data.demo_radar(plan_data.demo(off, now, 'en'), off, 'en')


class FakeFrame:
    """Just enough of the art API for put_temporary and restore."""

    def __init__(self, current, slideshow='off'):
        self.current, self.slideshow, self.calls, self.n = current, slideshow, [], 0

    def get_current(self):
        return {'content_id': self.current}

    def get_artmode(self):
        return 'on'

    def get_slideshow_status(self):
        return {'value': self.slideshow, 'category_id': 'MY-C0004', 'type': 'slideshow'}

    def set_slideshow_status(self, duration=0, type=True, category=2):
        self.slideshow = str(duration) if duration else 'off'
        self.calls.append(('slideshow', self.slideshow))

    def _slideshow_request(self, action, fields):
        self.slideshow = fields['value']
        self.calls.append(('slideshow', fields))

    def get_thumbnail(self, content_id):
        return b'jpeg'

    def upload(self, data, **kw):
        self.n += 1
        return f'MY_F09{self.n:02}'

    def select_image(self, content_id, category=None, show=True):
        self.current = content_id
        self.calls.append(('select', content_id))

    def delete_list(self, ids):
        self.calls.append(('delete', list(ids)))


def frame(monkeypatch, current, slideshow='off'):
    if os.path.exists(jobs.STATE_FILE):
        os.remove(jobs.STATE_FILE)
    tv = FakeFrame(current, slideshow)
    monkeypatch.setattr(jobs, 'connect', lambda cfg: tv)
    return tv


def test_slideshow_pauses_for_the_plan_and_comes_back(monkeypatch):
    tv = frame(monkeypatch, 'MY_F0001', slideshow='15')
    jobs.show_text(CFG, 'Hello')
    state = jobs.load_state()
    assert state['restore_id'] == 'MY_F0001' and tv.slideshow == 'off'
    assert state['slideshow'] == {'value': '15', 'category_id': 'MY-C0004', 'type': 'slideshow'}
    assert os.path.exists(jobs.art_path('MY_F0001'))  # thumbnail for the web page
    jobs.restore(CFG)
    assert tv.calls[-3:] == [('select', 'MY_F0001'), ('delete', ['MY_F0901']),
                             ('slideshow', {'value': '15', 'category_id': 'MY-C0004', 'type': 'slideshow'})]
    assert jobs.load_state()['slideshow'] is None


def test_artwork_picked_during_the_plan_is_kept(monkeypatch):
    tv = frame(monkeypatch, 'MY_F0001')
    jobs.show_text(CFG, 'Hello')
    tv.current = 'MY_F0002'  # someone chose another picture on the TV
    jobs.restore(CFG)
    assert ('select', 'MY_F0001') not in tv.calls and ('delete', ['MY_F0901']) in tv.calls
    assert jobs.load_state()['restore_id'] == 'MY_F0002'
    assert not any(c[0] == 'slideshow' for c in tv.calls)  # it was off, so it stays off


def test_preview_sits_on_the_current_picture(monkeypatch):
    tv = frame(monkeypatch, 'MY_F0005')
    cfg = dict(CFG, background='artwork')
    used = []
    monkeypatch.setattr(render, 'render', lambda data, out, bg=None: used.append(bg))
    jobs.preview(cfg)
    assert used[-1] == jobs.art_path('MY_F0005')  # what the slideshow shows now
    jobs.show_text(cfg, 'Hello')  # a plan is up: the preview uses the artwork it returns to
    jobs.preview(cfg)
    assert tv.current == 'MY_F0901' and used[-1] == jobs.art_path('MY_F0005')
    monkeypatch.setattr(jobs, 'connect', lambda cfg: (_ for _ in ()).throw(OSError('TV asleep')))
    jobs.preview(cfg)
    assert used[-1] == jobs.art_path('MY_F0005')


def test_preview_does_not_wait_for_a_stuck_tv(monkeypatch):
    frame(monkeypatch, 'MY_F0005')
    cfg = dict(CFG, background='artwork')
    jobs.show_text(cfg, 'Hello')  # remembers MY_F0005 and caches its thumbnail
    monkeypatch.setattr(jobs, 'connect', lambda cfg: time.sleep(2))
    monkeypatch.setattr(jobs, 'PREVIEW_WAIT', 0.2)
    used = []
    monkeypatch.setattr(render, 'render', lambda data, out, bg=None: used.append(bg))
    start = time.monotonic()
    jobs.preview(cfg)
    assert time.monotonic() - start < 1.5 and used == [jobs.art_path('MY_F0005')]
    with jobs.lock:  # the stuck TV call finished on its own and let go of the TV
        pass
