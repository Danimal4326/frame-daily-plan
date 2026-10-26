import datetime
import os
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
