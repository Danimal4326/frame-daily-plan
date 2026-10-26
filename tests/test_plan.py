import datetime
import os
import zoneinfo

import icalendar
from PIL import Image

import jobs
import plan_data
import render

HERE = os.path.dirname(__file__)
TZ = zoneinfo.ZoneInfo('Europe/London')
CFG = {'timezone': 'Europe/London', 'plan_lang': 'en', 'calendars': [], 'dim_past_events': True,
       'weather': {'enabled': False}, 'holidays': {'country': '', 'subdiv': ''}, 'background': 'default',
       'tv_ip': '192.168.1.50', 'schedule': {'enabled': True, 'start': '07:00', 'end': '10:00', 'days': [0, 1, 2, 3, 4]}}


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
    today = '2026-10-27'
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
    for lang in ('en', 'de'):
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
