"""Collect today's plan: calendar entries, to-dos, public holidays and weather."""
import datetime
import json
import sys
import urllib.parse
import urllib.request
import zoneinfo

import holidays
import icalendar
import recurring_ical_events

TODO_PREFIXES = ('to-do:', 'todo:', 'task:', 'aufgabe:')

# WMO weather code → emoji, German text, English text
WEATHER_CODES = {
    0: ('☀️', 'Sonnig', 'Sunny'), 1: ('🌤️', 'Überwiegend sonnig', 'Mostly sunny'),
    2: ('⛅', 'Teilweise bewölkt', 'Partly cloudy'), 3: ('☁️', 'Bewölkt', 'Cloudy'),
    45: ('🌫️', 'Neblig', 'Foggy'), 48: ('🌫️', 'Neblig', 'Foggy'),
    51: ('🌦️', 'Leichter Nieselregen', 'Light drizzle'), 53: ('🌦️', 'Nieselregen', 'Drizzle'),
    55: ('🌧️', 'Starker Nieselregen', 'Heavy drizzle'), 61: ('🌦️', 'Leichter Regen', 'Light rain'),
    63: ('🌧️', 'Regen', 'Rain'), 65: ('🌧️', 'Starker Regen', 'Heavy rain'),
    71: ('🌨️', 'Leichter Schnee', 'Light snow'), 73: ('🌨️', 'Schnee', 'Snow'), 75: ('❄️', 'Starker Schnee', 'Heavy snow'),
    80: ('🌦️', 'Regenschauer', 'Showers'), 81: ('🌧️', 'Regenschauer', 'Showers'), 82: ('🌧️', 'Starke Regenschauer', 'Heavy showers'),
    95: ('⛈️', 'Gewitter', 'Thunderstorm'), 96: ('⛈️', 'Gewitter mit Hagel', 'Thunderstorm with hail'),
    99: ('⛈️', 'Gewitter mit Hagel', 'Thunderstorm with hail'),
}
WORDS = {
    'de': {'all_day': 'Ganztägig', 'holiday': 'Feiertag', 'changeable': 'Wechselhaft', 'rain': 'Regen',
           'hint_rain': 'Regenjacke mitnehmen', 'hint_cold': 'Warme Jacke anziehen',
           'hint_cool': 'Pulli oder Jacke mitnehmen', 'hint_hot': 'Viel trinken und Sonnencreme'},
    'en': {'all_day': 'All day', 'holiday': 'Holiday', 'changeable': 'Changeable', 'rain': 'rain',
           'hint_rain': 'Bring a rain jacket', 'hint_cold': 'Wear a warm coat',
           'hint_cool': 'Bring a jumper or jacket', 'hint_hot': 'Drink plenty, wear sunscreen'},
}


def words(cfg):
    return WORDS.get(cfg.get('plan_lang', 'en'), WORDS['en'])


def nice_title(title):
    return ' '.join(title.split())


def fetch_calendar(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'frame-daily-plan'})
    return icalendar.Calendar.from_ical(urllib.request.urlopen(req, timeout=30).read())


def calendar_entries(cal, color, day, tz, w, todo_calendar=False):
    events, todos = [], []
    for ev in recurring_ical_events.of(cal).at(day):
        title = nice_title(str(ev.get('SUMMARY', '')))
        if not title:
            continue
        is_todo_prefix = title.lower().startswith(TODO_PREFIXES)
        if is_todo_prefix:
            title = title.split(':', 1)[1].strip()
        if todo_calendar or is_todo_prefix:
            todos.append(title)
            continue
        start = ev['DTSTART'].dt
        end = ev['DTEND'].dt if ev.get('DTEND') else None
        if isinstance(start, datetime.datetime):
            start = start.astimezone(tz)
            end = end.astimezone(tz) if end else None
            events.append({'sort': start.strftime('%H:%M'), 'start': start.strftime('%H:%M'),
                           'end': end.strftime('%H:%M') if end and end != start else None,
                           'end_dt': end or start, 'title': title, 'color': color})
        else:
            events.append({'sort': '00:00', 'start': w['all_day'], 'end': None, 'end_dt': None,
                           'title': title, 'color': color})
    return events, todos


def holiday_calendar(cfg, year):
    h = cfg.get('holidays') or {}
    if not h.get('country'):
        return {}
    subdiv = h.get('subdiv') or None
    cal = holidays.country_holidays(h['country'], subdiv=subdiv, years=year)
    # Use the plan language if the country's holiday data has it, otherwise its default names.
    lang = cfg.get('plan_lang', 'en')
    pick = next((code for code in (getattr(cal, 'supported_languages', ()) or ()) if code.split('_')[0] == lang), None)
    return holidays.country_holidays(h['country'], subdiv=subdiv, years=year, language=pick) if pick else cal


def holiday_entries(cfg, day, w):
    cal = holiday_calendar(cfg, day.year)
    if day not in cal:
        return []
    return [{'sort': '00:00', 'start': w['holiday'], 'end': None, 'end_dt': None, 'title': n.strip(), 'color': 'red'}
            for n in cal.get(day).split(';')]


def weather(cfg, day, w):
    loc = cfg['weather']
    url = 'https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode({
        'latitude': loc['lat'], 'longitude': loc['lon'], 'timezone': cfg['timezone'],
        'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
        'start_date': day.isoformat(), 'end_date': day.isoformat()})
    d = json.load(urllib.request.urlopen(url, timeout=20))['daily']
    code, tmax, tmin = d['weather_code'][0], d['temperature_2m_max'][0], d['temperature_2m_min'][0]
    rain = d['precipitation_probability_max'][0] or 0
    entry = WEATHER_CODES.get(code)
    icon, text = (entry[0], entry[1 if cfg.get('plan_lang') == 'de' else 2]) if entry else ('⛅', w['changeable'])
    if rain >= 50:
        hint = w['hint_rain']
    elif tmax < 12:
        hint = w['hint_cold']
    elif tmax < 18 or tmin < 12:
        hint = w['hint_cool']
    elif tmax >= 28:
        hint = w['hint_hot']
    else:
        hint = None
    if 30 <= rain < 50:
        text += f", {rain} % {w['rain']}"
    return {'icon': icon, 'max': round(tmax), 'min': round(tmin), 'text': text, 'hint': hint}


def build(cfg, now):
    tz = zoneinfo.ZoneInfo(cfg['timezone'])
    w = words(cfg)
    today = now.date()
    tomorrow = today + datetime.timedelta(days=1)
    errors = []
    try:
        events, events_tomorrow = holiday_entries(cfg, today, w), holiday_entries(cfg, tomorrow, w)
    except Exception as e:  # noqa: BLE001  e.g. an unknown country code
        events, events_tomorrow = [], []
        errors.append(f'Holidays: {e}')
    todos = []
    for c in cfg['calendars']:
        if not c.get('url'):
            continue
        try:
            cal = fetch_calendar(c['url'])
        except Exception as e:  # noqa: BLE001  one broken calendar must not hide the others
            errors.append(f"Calendar {c.get('name')}: {e}")
            continue
        is_todo = c.get('role') == 'todos'
        e1, t1 = calendar_entries(cal, c.get('color', 'green'), today, tz, w, is_todo)
        e2, _ = calendar_entries(cal, c.get('color', 'green'), tomorrow, tz, w, is_todo)
        events += e1
        todos += t1
        events_tomorrow += e2
    events.sort(key=lambda e: e['sort'])
    events_tomorrow.sort(key=lambda e: e['sort'])
    for e in events:
        e['past'] = bool(cfg.get('dim_past_events')) and e['end_dt'] is not None and e['end_dt'] <= now
    data = {'date': today.isoformat(), 'lang': cfg.get('plan_lang', 'en'), 'today': events,
            'tomorrow': events_tomorrow, 'todos': sorted(set(todos)), 'weather': None, 'errors': errors}
    loc = cfg.get('weather') or {}
    if loc.get('enabled') and loc.get('lat') is not None and loc.get('lon') is not None:
        try:
            data['weather'] = weather(cfg, today, w)
        except Exception as e:  # noqa: BLE001  the plan must still appear without weather
            errors.append(f'Weather: {e}')
    for e in data['today'] + data['tomorrow']:
        e.pop('end_dt', None)
        e.pop('sort', None)
    if errors:
        print('plan warnings:', errors, file=sys.stderr)
    return data


def geocode(name, lang='en'):
    """Place search for the settings page (Open-Meteo geocoding, no key needed)."""
    url = 'https://geocoding-api.open-meteo.com/v1/search?' + urllib.parse.urlencode(
        {'name': name, 'count': 6, 'language': lang, 'format': 'json'})
    results = json.load(urllib.request.urlopen(url, timeout=15)).get('results') or []
    return [{'label': ', '.join(x for x in (r.get('name'), r.get('admin1'), r.get('country')) if x),
             'lat': round(r['latitude'], 4), 'lon': round(r['longitude'], 4), 'timezone': r.get('timezone'),
             'country_code': r.get('country_code')} for r in results]


DEMO = {
    'de': {
        'today': [('Ganztägig', None, 'Projektwoche in der Schule', 'blue'),
                  ('07:15', '07:45', 'Frühstück zusammen', 'green'),
                  ('08:15', '14:00', 'Schule', 'blue'),
                  ('15:30', '16:30', 'Schwimmkurs', 'green'),
                  ('18:00', None, 'Abendessen bei Oma', 'green'),
                  ('19:30', '19:45', 'Rucksack für morgen packen', 'green')],
        'tomorrow': [('08:15', '14:00', 'Schule', 'blue'),
                     ('16:00', '17:00', 'Klavierunterricht', 'green'),
                     ('19:00', None, 'Spieleabend', 'green')],
        'todos': ['Englisch-Vokabeln lernen', 'Mathe üben', 'Zimmer aufräumen'],
        'weather': {'icon': '⛅', 'max': 19, 'min': 12, 'text': 'Teilweise bewölkt', 'hint': 'Pulli oder Jacke mitnehmen'},
    },
    'en': {
        'today': [('All day', None, 'Project week at school', 'blue'),
                  ('07:15', '07:45', 'Breakfast together', 'green'),
                  ('08:15', '14:00', 'School', 'blue'),
                  ('15:30', '16:30', 'Swimming lesson', 'green'),
                  ('18:00', None, "Dinner at Grandma's", 'green'),
                  ('19:30', '19:45', 'Pack the school bag', 'green')],
        'tomorrow': [('08:15', '14:00', 'School', 'blue'),
                     ('16:00', '17:00', 'Piano lesson', 'green'),
                     ('19:00', None, 'Board game night', 'green')],
        'todos': ['Learn English vocabulary', 'Practise maths', 'Tidy up your room'],
        'weather': {'icon': '⛅', 'max': 19, 'min': 12, 'text': 'Partly cloudy', 'hint': 'Bring a jumper or jacket'},
    },
}


def demo(cfg, now, lang='en'):
    """Made-up plan for screenshots and videos: no real names, appointments or location."""
    d = DEMO[lang]

    def entries(rows, past_check):
        out = []
        for start, end, title, color in rows:
            past = False
            if past_check and start[0].isdigit():
                h, m = map(int, (end or start).split(':'))
                past = bool(cfg.get('dim_past_events')) and (now.hour, now.minute) >= (h, m)
            out.append({'start': start, 'end': end, 'title': title, 'color': color, 'past': past})
        return out
    return {'date': now.date().isoformat(), 'lang': lang, 'today': entries(d['today'], True),
            'tomorrow': entries(d['tomorrow'], False), 'todos': d['todos'], 'weather': dict(d['weather']),
            'errors': []}
