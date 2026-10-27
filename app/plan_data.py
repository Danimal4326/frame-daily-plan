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

import radar
import render
import stations

OUTLOOK_DAYS = 3

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
           'hint_cool': 'Pulli oder Jacke mitnehmen', 'hint_hot': 'Viel trinken und Sonnencreme',
           'raining_now': 'Es regnet gerade'},
    'en': {'all_day': 'All day', 'holiday': 'Holiday', 'changeable': 'Changeable', 'rain': 'rain',
           'hint_rain': 'Bring a rain jacket', 'hint_cold': 'Wear a warm coat',
           'hint_cool': 'Bring a jumper or jacket', 'hint_hot': 'Drink plenty, wear sunscreen',
           'raining_now': 'Raining now'},
}


WORDS['en_US'] = {**WORDS['en'], 'hint_cool': 'Bring a sweater or jacket'}


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
    lang, known = cfg.get('plan_lang', 'en'), getattr(cal, 'supported_languages', ()) or ()
    pick = lang if lang in known else next((code for code in known if code.split('_')[0] == lang.split('_')[0]), None)
    # "Unofficial" days such as Halloween or Valentine's Day, where the country's data has them.
    extra = h.get('observances', True) and 'unofficial' in (getattr(cal, 'supported_categories', ()) or ())
    if not pick and not extra:
        return cal
    return holidays.country_holidays(h['country'], subdiv=subdiv, years=year, language=pick,
                                     categories=('public', 'unofficial') if extra else ('public',))


# A clue for each holiday in the month calendar, from words in its English or German name; first match wins.
HOLIDAY_EMOJI = [
    (('halloween',), '🎃'), (('thanksgiving',), '🦃'), (('christmas', 'weihnacht', 'boxing'), '🎄'),
    (('new year', 'neujahr'), '🎆'), (('independence day',), '🎆'), (('juneteenth',), '✊'),
    (('valentine',), '❤️'), (('patrick',), '☘️'), (('easter', 'oster'), '🐣'), (('good friday', 'karfreitag'), '✝️'),
    (('whit', 'pfingst', 'pentecost'), '🕊️'), (('ascension', 'himmelfahrt', 'corpus christi', 'fronleichnam',
                                                 'assumption', 'mariä', 'reformation'), '⛪'),
    (('epiphany', 'drei könige'), '👑'), (('all saints', 'allerheiligen'), '🕯️'),
    (('veterans', 'memorial', 'remembrance'), '🎖️'), (('labor', 'labour', 'may day', 'erster mai', 'arbeit'), '🛠️'),
    (('mother', 'mutter'), '💐'), (('father', 'vater'), '👔'), (('election',), '🗳️'), (('columbus', 'indigenous'), '⛵'),
    (('martin luther king',), '🕊️'), (('washington', 'lincoln', 'president'), '🎩'), (('groundhog',), '🦫'),
    (('unity', 'einheit'), '🎉'), (('bank holiday',), '🏖️'),
]


def holiday_emoji(name):
    name = name.lower()
    return next((icon for words, icon in HOLIDAY_EMOJI if any(w in name for w in words)), '⭐')


def holiday_entries(cfg, day, w):
    cal = holiday_calendar(cfg, day.year)
    if day not in cal:
        return []
    return [{'sort': '00:00', 'start': w['holiday'], 'end': None, 'end_dt': None, 'title': n.strip(), 'color': 'red'}
            for n in cal.get(day).split(';')]


# After dark the sky "now" gets night icons and words: no sun, "clear" instead of "sunny".
NIGHT = {'☀️': ('🌙', 'Klar', 'Clear'), '🌤️': ('🌙', 'Überwiegend klar', 'Mostly clear'),
         '⛅': ('☁️', None, None), '🌥️': ('☁️', None, None), '🌦️': ('🌧️', None, None)}


def at_night(sky):
    icon, de, en = NIGHT.get(sky['icon'], (sky['icon'], None, None))
    return dict(sky, icon=icon, text=(de or sky['text'][0], en or sky['text'][1]))


def open_meteo_days(cfg, day):
    """Today and the outlook days from Open-Meteo: date, icon, (German, English) text, °C high and low, % rain.
    Also the sky and temperature now."""
    loc = cfg['weather']
    url = 'https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode({
        'latitude': loc['lat'], 'longitude': loc['lon'], 'timezone': cfg['timezone'],
        'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
        'current': 'weather_code,is_day,temperature_2m',
        'start_date': day.isoformat(), 'end_date': (day + datetime.timedelta(days=OUTLOOK_DAYS)).isoformat()})
    data = json.load(urllib.request.urlopen(url, timeout=20))
    d, c = data['daily'], data.get('current') or {}
    days = [{'date': d['time'][i], 'icon': WEATHER_CODES.get(d['weather_code'][i], ('⛅',))[0],
             'text': WEATHER_CODES.get(d['weather_code'][i], (None, None, None))[1:],
             'max': d['temperature_2m_max'][i], 'min': d['temperature_2m_min'][i],
             'rain': d['precipitation_probability_max'][i] or 0} for i in range(len(d['time']))]
    now = None
    if c.get('weather_code') is not None:
        code = WEATHER_CODES.get(c['weather_code'], ('⛅', None, None))
        now = {'icon': code[0], 'text': code[1:], 'temp': c.get('temperature_2m')}
        now = now if c.get('is_day', 1) else at_night(now)
    return days, now


# Pirate Weather icon names (its extended "pirate" set) → emoji and short texts, first match wins
PIRATE_ICONS = [
    ('thunder', '⛈️', 'Gewitter', 'Thunderstorm'), ('hail', '⛈️', 'Hagel', 'Hail'),
    ('heavy-rain', '🌧️', 'Starker Regen', 'Heavy rain'), ('drizzle', '🌦️', 'Nieselregen', 'Drizzle'),
    ('light-rain', '🌦️', 'Leichter Regen', 'Light rain'), ('rain', '🌧️', 'Regen', 'Rain'),
    ('sleet', '🌨️', 'Schneeregen', 'Sleet'), ('mixed', '🌨️', 'Schneeregen', 'Rain and snow'),
    ('heavy-snow', '❄️', 'Starker Schnee', 'Heavy snow'), ('snow', '🌨️', 'Schnee', 'Snow'),
    ('flurries', '🌨️', 'Schneeschauer', 'Flurries'), ('fog', '🌫️', 'Neblig', 'Foggy'), ('mist', '🌫️', 'Dunstig', 'Misty'),
    ('haze', '🌫️', 'Dunstig', 'Hazy'), ('smoke', '🌫️', 'Rauchig', 'Smoky'), ('wind', '💨', 'Windig', 'Windy'),
    ('breezy', '💨', 'Windig', 'Breezy'), ('mostly-clear', '🌤️', 'Überwiegend sonnig', 'Mostly sunny'),
    ('clear', '☀️', 'Sonnig', 'Sunny'), ('mostly-cloudy', '🌥️', 'Überwiegend bewölkt', 'Mostly cloudy'),
    ('partly-cloudy', '⛅', 'Teilweise bewölkt', 'Partly cloudy'), ('cloudy', '☁️', 'Bewölkt', 'Cloudy'),
]


def pirate_weather_days(cfg, day):
    """The same days from Pirate Weather (needs a free API key from pirateweather.net)."""
    loc = cfg['weather']
    url = (f"https://api.pirateweather.net/forecast/{urllib.parse.quote(loc['pirateweather_key'])}/{loc['lat']},{loc['lon']}?"
           + urllib.parse.urlencode({'units': 'si', 'icon': 'pirate', 'exclude': 'minutely,hourly,alerts'}))
    data = json.load(urllib.request.urlopen(url, timeout=20))
    tz, days = zoneinfo.ZoneInfo(cfg['timezone']), []

    def sky(icon):
        match = next((m for m in PIRATE_ICONS if m[0] in icon), ('', '⛅', None, None))
        return {'icon': match[1], 'text': match[2:]}
    for d in data['daily']['data']:
        date = datetime.datetime.fromtimestamp(d['time'], tz).date()
        if day <= date <= day + datetime.timedelta(days=OUTLOOK_DAYS):
            days.append({'date': date.isoformat(), **sky(d.get('icon', '')), 'max': d['temperatureHigh'],
                         'min': d['temperatureLow'], 'rain': round((d.get('precipProbability') or 0) * 100)})
    if not days:
        raise RuntimeError('Pirate Weather sent no forecast for today')
    c, now = data.get('currently') or {}, None
    if c.get('icon'):
        now = dict(sky(c['icon']), temp=c.get('temperature'))
        now = at_night(now) if 'night' in c['icon'] else now
    return days, now


FORECASTS = {'open_meteo': open_meteo_days, 'pirateweather': pirate_weather_days}


def weather(cfg, day, w):
    days, now = FORECASTS.get(cfg['weather'].get('source'), open_meteo_days)(cfg, day)
    today = days[0]
    tmax, tmin, rain = today['max'], today['min'], today['rain']
    # With the temperature "now" as the big number, the sky is the one now too; the hint stays the day's.
    sky = now if cfg['weather'].get('main') == 'now' and now else today
    icon, text = sky['icon'], sky['text'][0 if cfg.get('plan_lang') == 'de' else 1] or w['changeable']
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
    # The next days, for the outlook: icon, high, low and chance of rain.
    outlook = [{k: o[k] for k in ('date', 'icon', 'max', 'min', 'rain')} for o in days[1:]]
    wx = {'icon': icon, 'max': tmax, 'min': tmin, 'text': text, 'hint': hint, 'outlook': outlook}
    if sky is now:
        # the day's sky goes under the big number ("Sunny today"), without the chance of rain
        wx['day_text'] = today['text'][0 if cfg.get('plan_lang') == 'de' else 1] or w['changeable']
        if now.get('temp') is not None:
            wx['now'] = now['temp']  # a station's reading, if there is one, replaces this
    return wx


def with_station(wx, reading, w):
    """The station's temperature now, and rain that is falling now, over the forecast."""
    if not reading or (reading.get('temp_c') is None and (not wx or reading.get('rain_rate_mm_h') is None)):
        return wx  # nothing to add (without a forecast, only a temperature makes a panel)
    wx = dict(wx) if wx else {'icon': '🌡️', 'max': None, 'min': None, 'text': '', 'hint': None}  # station only
    if reading.get('temp_c') is not None:
        wx['now'] = reading['temp_c']
    if (reading.get('rain_rate_mm_h') or 0) > 0:
        wx.update(icon='🌧️', text=w['raining_now'], hint=w['hint_rain'])
    return wx


def in_units(wx, cfg):
    """Weather is worked out in °C (the hints' thresholds); only the shown numbers are converted."""
    fahrenheit = (cfg.get('units') or {}).get('temperature') == 'F'
    convert = lambda c: round(stations.c_to_f(c) if fahrenheit else c)  # noqa: E731
    wx = dict(wx)
    for key in ('max', 'min', 'now'):
        if wx.get(key) is not None:
            wx[key] = convert(wx[key])
    wx['outlook'] = [dict(o, max=convert(o['max']), min=convert(o['min'])) for o in wx.get('outlook') or []]
    return wx


def build(cfg, now):
    tz = zoneinfo.ZoneInfo(cfg['timezone'])
    w = words(cfg)
    today = now.date()
    tomorrow = today + datetime.timedelta(days=1)
    errors = []
    try:
        events, events_tomorrow = holiday_entries(cfg, today, w), holiday_entries(cfg, tomorrow, w)
        # today's and the coming holidays this month, each marked with an emoji in the month calendar
        cal = holiday_calendar(cfg, today.year)
        holiday_marks = {d.day: holiday_emoji(cal[d]) for d in cal if d.month == today.month and d >= today}
    except Exception as e:  # noqa: BLE001  e.g. an unknown country code
        events, events_tomorrow, holiday_marks = [], [], {}
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
    data = {'date': today.isoformat(), 'lang': cfg.get('plan_lang', 'en'), 'time_format': cfg.get('time_format', '24h'),
            'today': events, 'tomorrow': events_tomorrow, 'todos': sorted(set(todos)), 'weather': None, 'errors': errors,
            'holiday_marks': holiday_marks}
    loc = cfg.get('weather') or {}
    if loc.get('enabled') and loc.get('lat') is not None and loc.get('lon') is not None:
        try:
            data['weather'] = weather(cfg, today, w)
        except Exception as e:  # noqa: BLE001  the plan must still appear without weather
            errors.append(f'Weather: {e}')
        try:
            data['weather'] = with_station(data['weather'], stations.read(cfg), w)
        except Exception as e:  # noqa: BLE001  nor without the station
            errors.append(f'Weather station: {e}')
        if loc.get('radar', True):
            try:
                image, at = radar.fetch(loc['lat'], loc['lon'], render.RADAR_SIZE, tz)
                data['radar'] = {'image': image, 'time': at.strftime('%H:%M'), 'credit': radar.CREDIT}
            except Exception as e:  # noqa: BLE001
                errors.append(f'Radar: {e}')
    if data['weather']:
        data['weather'] = dict(in_units(data['weather'], cfg), main=loc.get('main', 'high'))
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


DEMO['en_US'] = {
    **DEMO['en'],
    'today': [('All day', None, 'Project week at school', 'blue'),
              ('07:15', '07:45', 'Breakfast together', 'green'),
              ('08:15', '14:00', 'School', 'blue'),
              ('15:30', '16:30', 'Swim lesson', 'green'),
              ('18:00', None, "Dinner at Grandma's", 'green'),
              ('19:30', '19:45', 'Pack your backpack', 'green')],
    'todos': ['Study spelling words', 'Practice math', 'Clean your room'],
    'weather': {**DEMO['en']['weather'], 'hint': WORDS['en_US']['hint_cool']},
}


# The demo's stand-in place per language (never the family's own): holidays and radar from here.
DEMO_PLACE = {'de': ('DE', 'BY', 48.137, 11.575), 'en': ('GB', 'ENG', 51.507, -0.128), 'en_US': ('US', 'NY', 40.713, -74.006)}


def demo(cfg, now, lang='en'):
    """Made-up plan for screenshots and videos: no real names, appointments or location."""
    d = DEMO[lang]
    country, subdiv = DEMO_PLACE[lang][:2]
    cal = holiday_calendar(dict(cfg, plan_lang=lang, holidays={'country': country, 'subdiv': subdiv}), now.year)

    def entries(rows, past_check):
        out = []
        for start, end, title, color in rows:
            past = False
            if past_check and start[0].isdigit():
                h, m = map(int, (end or start).split(':'))
                past = bool(cfg.get('dim_past_events')) and (now.hour, now.minute) >= (h, m)
            out.append({'start': start, 'end': end, 'title': title, 'color': color, 'past': past})
        return out
    days = [(now.date() + datetime.timedelta(days=i)).isoformat() for i in range(1, OUTLOOK_DAYS + 1)]
    outlook = [{'date': day, 'icon': icon, 'max': tmax, 'min': tmin, 'rain': rain}
               for day, (icon, tmax, tmin, rain) in zip(days, [('🌦️', 17, 10, 60), ('☀️', 21, 11, 0), ('⛅', 20, 13, 10)])]
    return {'date': now.date().isoformat(), 'lang': lang, 'time_format': cfg.get('time_format', '24h'),
            'today': entries(d['today'], True), 'tomorrow': entries(d['tomorrow'], False), 'todos': d['todos'],
            'weather': in_units(dict(d['weather'], outlook=outlook, main=(cfg.get('weather') or {}).get('main', 'high')), cfg),
            'holiday_marks': {x.day: holiday_emoji(cal[x]) for x in cal if x.month == now.month and x >= now.date()},
            'errors': []}


def demo_radar(data, cfg, lang):
    """Live radar around the demo's stand-in city (needs the internet, so not part of demo() itself)."""
    if not (cfg.get('weather') or {}).get('radar', True):
        return data
    lat, lon = DEMO_PLACE[lang][2:]
    try:
        image, at = radar.fetch(lat, lon, render.RADAR_SIZE, zoneinfo.ZoneInfo(cfg['timezone']))
        return dict(data, radar={'image': image, 'time': at.strftime('%H:%M'), 'credit': radar.CREDIT})
    except Exception as e:  # noqa: BLE001  the demo works without it
        print(f'demo radar: {e}', file=sys.stderr)
        return data
