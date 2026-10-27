"""Render the daily plan for the Frame's Art Mode (3840x2160 JPEG).

Blurred, darkened background (normally the artwork the plan replaces) with calm
panels: date + month + to-dos, today, weather + tomorrow. No clock or news on
purpose: the image is static for hours and should never surprise anyone.
Fonts are Inter and Noto Color Emoji (both OFL, bundled in fonts/).
"""
import calendar
import datetime
import os
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 3840, 2160
M = 180
CREAM = (255, 249, 238)
SOFT = (214, 210, 200)
DIM = (165, 162, 155)
ORANGE = (242, 150, 60)
COLORS = {'green': (120, 200, 170), 'orange': ORANGE, 'blue': (120, 160, 220), 'red': (232, 112, 112), 'grey': (170, 170, 170),
          'teal': (90, 190, 195), 'purple': (175, 140, 220), 'pink': (235, 140, 190), 'yellow': (238, 205, 100),
          'brown': (190, 150, 110)}
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, 'fonts')
EMOJI = os.path.join(FONTS, 'NotoColorEmoji.ttf')  # colour bitmaps, only usable at size 109
LABELS = {
    'de': {'weekdays': ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'],
           'months': ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September',
                      'Oktober', 'November', 'Dezember'],
           'initials': 'MDMDFSS', 'today': 'Heute', 'tomorrow': 'Morgen', 'todos': 'Zu erledigen',
           'no_todos': 'Nichts zu erledigen', 'no_events': 'Keine Termine', 'more': '… und weitere',
           'past': 'vorbei', 'night': 'bis {}° in der Nacht', 'now': 'jetzt {}°', 'day_sky': 'Heute: {}', 'high_low': 'Höchst {}° · Tiefst {}°', 'all_day': 'Ganztägig',
           'more_todos': '… und {} weitere', 'radar': 'Radar {}', 'rain_chance': '{} % Regen',
           'weekdays_short': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
           'date': '{day}. {month}'},
    'en': {'weekdays': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
           'months': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
                      'October', 'November', 'December'],
           'initials': 'MTWTFSS', 'today': 'Today', 'tomorrow': 'Tomorrow', 'todos': 'To do',
           'no_todos': 'Nothing to do', 'no_events': 'No events', 'more': '… and more',
           'past': 'done', 'night': 'down to {}° tonight', 'now': 'now {}°', 'day_sky': '{} today', 'high_low': 'High {}° · Low {}°', 'all_day': 'All day',
           'more_todos': '… and {} more', 'date': '{month} {day}', 'radar': 'Radar {}', 'rain_chance': '{}% rain',
           'weekdays_short': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']},
}
LABELS['en_US'] = {**LABELS['en'], 'initials': 'SMTWTFS', 'first_weekday': calendar.SUNDAY}  # US weeks start on Sunday
# Next to the weather, today's events and tomorrow's right under them share one panel, in the
# largest type (1 down to 0.55) that fits them all.
SCALES = [round(1 - 0.05 * i, 2) for i in range(10)]
CENTER_HEAD = 175  # where the events start below the panel title
TOMORROW_HEAD = 160  # the line and "Tomorrow" between the two days (scaled with the events)
TODO_ROW = 125  # one to-do line at full size; longer lists shrink like the events
RADAR_TOP = 1320  # the radar map fills the bottom of the right column
RADAR_SIZE = (W - M - 2570, H - M - RADAR_TOP)

L = LABELS['de']  # set per render
TWELVE_HOUR = False  # set per render


_fonts = {}


def font(size, weight='Regular'):
    # Inter runs a little wider than the Avenir the layout was drawn with.
    key = (round(size * 0.94), weight)
    if key not in _fonts:
        name = {'Bold': 'Bold', 'DemiBold': 'SemiBold', 'Medium': 'Medium', 'Regular': 'Regular'}[weight]
        _fonts[key] = ImageFont.truetype(os.path.join(FONTS, f'Inter-{name}.ttf'), key[0])
    return _fonts[key]


def wrap(d, text, f, max_w, max_lines=2):
    lines, line = [], ''
    for word in text.split(' '):  # split on plain spaces only: no-break spaces keep "16 Uhr" together
        if not word:
            continue
        trial = (line + ' ' + word).strip()
        if d.textlength(trial, font=f) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines[:max_lines]


def clock(text):
    """'19:30' as '7:30 PM' on 12-hour plans; anything else ('All day', 'Holiday') unchanged."""
    if not TWELVE_HOUR or not re.fullmatch(r'\d\d:\d\d', text or ''):
        return text
    h, m = map(int, text.split(':'))
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def default_background():
    """A calm, generated backdrop (soft dusk gradient), so the project ships no third-party photo."""
    small = Image.new('RGB', (64, 36))
    corners = [(58, 74, 98), (92, 84, 110), (34, 52, 66), (70, 58, 72)]  # tl, tr, bl, br
    px = small.load()
    for y in range(36):
        v = y / 35
        for x in range(64):
            u = x / 63
            px[x, y] = tuple(round((corners[0][k] * (1 - u) + corners[1][k] * u) * (1 - v)
                                   + (corners[2][k] * (1 - u) + corners[3][k] * u) * v) for k in range(3))
    return small.resize((W, H), Image.BICUBIC)


def background(path):
    if not path:
        return Image.blend(default_background(), Image.new('RGB', (W, H), (12, 16, 22)), 0.25)
    im = Image.open(path).convert('RGB')
    w, h = im.size
    if w / h > W / H:
        nw = round(h * W / H); im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = round(w * H / W); im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14))
    return Image.blend(im, Image.new('RGB', (W, H), (12, 16, 22)), 0.45)


def panel(layer, box, title=None):
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=48, fill=(14, 18, 26, 150))
    if title:
        d.text((box[0] + 70, box[1] + 50), title, font=font(86, 'DemiBold'), fill=CREAM)


def event_heights(d, items, w, scale=1.0):
    s = lambda v: round(v * scale)  # noqa: E731
    tf = font(s(74), 'DemiBold')
    return [s(80) + len(wrap(d, ev['title'], tf, w - 60)) * s(92) + s(50) for ev in items]


def events(d, items, x, y, w, bottom, scale=1.0):
    s = lambda v: round(v * scale)  # noqa: E731
    if not items:
        d.text((x, y), L['no_events'], font=font(s(70), 'Medium'), fill=DIM)
        return y + s(110)
    tf = font(s(74), 'DemiBold')
    more_h = s(80)  # room kept for "… and more" unless this is the last event
    for i, (ev, need) in enumerate(zip(items, event_heights(d, items, w, scale))):
        lines = wrap(d, ev['title'], tf, w - 60)
        if y + need > (bottom if i == len(items) - 1 else bottom - more_h):
            d.text((x, y), L['more'], font=font(s(64), 'Medium'), fill=DIM)
            return y + more_h
        past = ev.get('past')
        color = COLORS['grey'] if past else COLORS.get(ev.get('color', 'green'), COLORS['green'])
        d.rounded_rectangle([x, y + 8, x + 14, y + need - s(50)], radius=7, fill=color)
        times = clock(ev.get('start', L['all_day'])) + (f" – {clock(ev['end'])}" if ev.get('end') else '')
        d.text((x + 50, y), times + (f"  ·  {L['past']}" if past else ''), font=font(s(62), 'Medium'), fill=DIM if past else SOFT)
        for n, line in enumerate(lines):
            d.text((x + 50, y + s(80) + n * s(92)), line, font=tf, fill=DIM if past else CREAM)
        y += need
    return y


def emoji(text, size):
    """A colour emoji as an RGBA image (the font only has bitmaps at size 109)."""
    icon = Image.new('RGBA', (140, 140), (0, 0, 0, 0))
    ImageDraw.Draw(icon).text((0, 0), text, font=ImageFont.truetype(EMOJI, 109), embedded_color=True)
    return icon.resize((size, size), Image.LANCZOS)


def outlook(im, d, days, box):
    """The next days side by side: weekday, icon, high and low, chance of rain if it is likely."""
    x0, top, x1, bottom = box
    cw = (x1 - x0 - 100) / len(days)
    y = top + max(40, (bottom - top - 360) // 2)
    for i, o in enumerate(days):
        cx = round(x0 + 50 + cw * i + cw / 2)
        day = datetime.date.fromisoformat(o['date'])
        d.text((cx, y), L['weekdays_short'][day.weekday()], font=font(58, 'DemiBold'), fill=SOFT, anchor='mt')
        im.alpha_composite(emoji(o['icon'], 130), (cx - 65, y + 85))
        high, low = f"{o['max']}°", f"  {o['min']}°"
        hf, lf = font(60, 'DemiBold'), font(60, 'Medium')
        left = cx - (d.textlength(high, font=hf) + d.textlength(low, font=lf)) / 2
        d.text((left, y + 240), high, font=hf, fill=CREAM)
        d.text((left + d.textlength(high, font=hf), y + 240), low, font=lf, fill=SOFT)
        if o.get('rain', 0) >= 30:
            d.text((cx, y + 320), L['rain_chance'].format(o['rain']), font=font(48, 'Medium'), fill=COLORS['blue'], anchor='mt')


def radar_map(im, radar, box):
    """The radar picture with rounded corners, a dot for home, its time and the map credits."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    pic = radar['image'].crop((0, 0, w, h))
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=48, fill=255)
    im.paste(pic, (x0, y0), mask)
    overlay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(overlay)
    cx, cy = x0 + w // 2, y0 + h // 2
    o.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=ORANGE + (255,), outline=CREAM + (255,), width=6)
    label = L['radar'].format(clock(radar['time']))
    lf = font(50, 'DemiBold')
    o.rounded_rectangle([x0 + 30, y1 - 110, x0 + 90 + o.textlength(label, font=lf), y1 - 30], radius=24, fill=(14, 18, 26, 190))
    o.text((x0 + 60, y1 - 70), label, font=lf, fill=CREAM + (255,), anchor='lm')
    o.text((x1 - 40, y1 - 30), radar['credit'], font=font(28, 'Medium'), fill=SOFT + (255,), anchor='rs')
    im.alpha_composite(overlay)


def month(im, d, date, x, y, w, holiday_marks=None):
    d.text((x, y), L['months'][date.month - 1], font=font(72, 'DemiBold'), fill=CREAM)
    cw = w / 7
    y += 110
    for i, wd in enumerate(L['initials']):
        d.text((x + cw * i + cw / 2, y), wd, font=font(52, 'Medium'), fill=DIM, anchor='mt')
    y += 80
    first = L.get('first_weekday', calendar.MONDAY)
    for week in calendar.Calendar(first).monthdayscalendar(date.year, date.month):
        for i, day in enumerate(week):
            weekend = (first + i) % 7 >= 5
            if not day:
                continue
            cx, cy = x + cw * i + cw / 2, y + 34
            if day == date.day:
                d.ellipse([cx - 46, cy - 46, cx + 46, cy + 46], fill=ORANGE)
            d.text((cx, cy), str(day), font=font(58, 'DemiBold' if day == date.day else 'Medium'),
                   fill=SOFT if weekend and day != date.day else CREAM, anchor='mm')
            if (holiday_marks or {}).get(day):  # a holiday: its emoji as a badge at the number's top right
                im.alpha_composite(emoji(holiday_marks[day], 60), (round(cx + 28), round(cy - 58)))
        y += 86


def temperatures(wx):
    """The big number and the lines under it. Normally today's high, with the temperature now (if
    known) and the night's low below. With the temperature now as the big number (chosen, or no
    forecast): the day's sky ("Sunny today") and its high and low below."""
    now = wx.get('now')
    if now is not None and (wx.get('main') == 'now' or wx.get('max') is None):
        small = [L['day_sky'].format(wx['day_text'])] if wx.get('day_text') else []
        if wx.get('max') is not None and wx.get('min') is not None:
            small.append(L['high_low'].format(wx['max'], wx['min']))
        return now, small
    small = [L['now'].format(now)] if now is not None else []
    return wx['max'], small + ([L['night'].format(wx['min'])] if wx.get('min') is not None else [])


def list_height(d, items, w, scale):
    return sum(event_heights(d, items, w, scale)) if items else round(110 * scale)


def day_scale(d, today, tomorrow, w, room):
    """The largest type in which today, the "Tomorrow" heading and tomorrow all fit."""
    for scale in SCALES:
        if list_height(d, today, w, scale) + round(TOMORROW_HEAD * scale) + list_height(d, tomorrow, w, scale) <= room:
            return scale
    return SCALES[-1]


def today_and_tomorrow(d, today, tomorrow, x, top, w, bottom):
    """Today's events, then tomorrow's right under them. If even the smallest type is too big,
    today is cut short ("… and more") so that two of tomorrow's events always show."""
    scale = day_scale(d, today, tomorrow, w, bottom - top)
    s = lambda v: round(v * scale)  # noqa: E731
    keep = list_height(d, tomorrow[:2], w, scale) + (s(80) if len(tomorrow) > 2 else 0)
    y = events(d, today, x, top, w, bottom - s(TOMORROW_HEAD) - keep, scale)
    d.line([x, y + s(10), x + w, y + s(10)], fill=DIM, width=3)
    d.text((x, y + s(35)), L['tomorrow'], font=font(s(80), 'DemiBold'), fill=CREAM)
    events(d, tomorrow, x, y + s(TOMORROW_HEAD), w, bottom, scale)
    return scale


def todo_scale(n, room):
    """The largest scale at which n to-do lines fit, and how many fit at it."""
    for scale in SCALES:
        if n * TODO_ROW * scale <= room:
            return scale, n
    return SCALES[-1], int(room // (TODO_ROW * SCALES[-1]))


def render(day, out, background_path=None):
    global L, TWELVE_HOUR
    L = LABELS.get(day.get('lang', 'de'), LABELS['de'])
    TWELVE_HOUR = day.get('time_format') == '12h'
    date = datetime.date.fromisoformat(day['date'])
    bg = background(background_path).convert('RGBA')
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))

    c1, c2, c3 = (M, 1230), (1310, 2490), (2570, W - M)
    # Without a quote the panels use the strip at the bottom too.
    top, bottom = 560, 1880 if day.get('quote') else H - M
    wx, radar = day.get('weather'), day.get('radar')
    # With weather, the right column is weather, outlook and radar, and today and tomorrow share the
    # middle panel. Without any, tomorrow keeps the right column to itself.
    side = bool(wx or radar)
    today, tomorrow = day.get('today', []), day.get('tomorrow', [])
    ew = c2[1] - c2[0] - 140
    # The month takes 4 to 6 week rows; the ones it doesn't need go to the to-dos below it.
    weeks = len(calendar.Calendar(L.get('first_weekday', calendar.MONDAY)).monthdayscalendar(date.year, date.month))
    month_bottom = 1300 - 86 * (6 - weeks)
    panel(layer, (c1[0], top, c1[1], month_bottom))
    panel(layer, (c1[0], month_bottom + 50, c1[1], bottom), day.get('todo_title', L['todos']))
    if side:
        panel(layer, (c2[0], M, c2[1], bottom), day.get('today_title', L['today']))
        panel(layer, (c3[0], M, c3[1], 820))
        days = (wx or {}).get('outlook') or []
        outlook_box = (c3[0], 870, c3[1], RADAR_TOP - 50 if radar else bottom)
        if days:
            panel(layer, outlook_box)
    else:
        panel(layer, (c2[0], M, c2[1], bottom), day.get('today_title', L['today']))
        panel(layer, (c3[0], M, c3[1], 820))
        panel(layer, (c3[0], 870, c3[1], bottom), L['tomorrow'])
    im = Image.alpha_composite(bg, layer)
    d = ImageDraw.Draw(im)

    # Date, top left.
    d.text((c1[0] + 10, M - 20), L['weekdays'][date.weekday()], font=font(190, 'Bold'), fill=CREAM)
    d.text((c1[0] + 14, M + 220), L['date'].format(day=date.day, month=L['months'][date.month - 1]), font=font(96, 'Medium'), fill=SOFT)
    month(im, d, date, c1[0] + 70, top + 50, c1[1] - c1[0] - 140, day.get('holiday_marks'))

    # To-dos with empty boxes.
    y = month_bottom + 205
    if not day.get('todos'):
        d.text((c1[0] + 70, y), L['no_todos'], font=font(70, 'Medium'), fill=DIM)
    todos = day.get('todos', [])
    scale, fits = todo_scale(len(todos), bottom - 40 - y)
    if len(todos) > fits:
        todos = todos[:fits - 1] + [L['more_todos'].format(len(todos) - fits + 1)]
    row, box = round(TODO_ROW * scale), round(85 * scale)
    # One size for the whole list, shrunk until the longest item fits inside the panel.
    text_x = c1[0] + 70 + box + round(40 * scale)
    size, max_w = round(80 * scale), c1[1] - text_x - 50
    while size > round(52 * scale) and any(d.textlength(t, font=font(size, 'Medium')) > max_w for t in todos):
        size -= 2
    for todo in todos:
        top_y = y + round(10 * scale)
        d.rounded_rectangle([c1[0] + 70, top_y, c1[0] + 70 + box, top_y + box], radius=round(18 * scale), outline=ORANGE,
                            width=max(5, round(9 * scale)))
        d.text((text_x, top_y + box // 2), todo, font=font(size, 'Medium'), fill=CREAM, anchor='lm')
        y += row

    if side:
        today_and_tomorrow(d, today, tomorrow, c2[0] + 70, M + CENTER_HEAD, ew, bottom - 30)
    else:
        events(d, today, c2[0] + 70, M + 200, ew, bottom - 40)
        events(d, tomorrow, c3[0] + 70, 1070, c3[1] - c3[0] - 140, bottom - 40, scale=0.82)

    # Weather: icon, temperatures, one concrete hint.
    if wx:
        im.alpha_composite(emoji(wx['icon'], 230), (c3[0] + 70, M + 70))
        big, small = temperatures(wx)
        d.text((c3[0] + 340, M + 70), f'{big}°', font=font(150, 'DemiBold'), fill=CREAM)
        two = len(small) == 2  # two lines push the text below down a little
        room = c3[1] - 70 - (c3[0] + 340)
        for i, line in enumerate(small):
            size = 54 if two else 58
            while size > 40 and d.textlength(line, font=font(size, 'Medium')) > room:  # e.g. "Thunderstorm with hail today"
                size -= 2
            d.text((c3[0] + 340, M + (235 if two else 250) + i * 65), line, font=font(size, 'Medium'), fill=SOFT)
        shift = 30 if two else 0
        d.text((c3[0] + 70, M + 380 + shift), wx['text'], font=font(66, 'Medium'), fill=CREAM)
        if wx.get('hint'):
            d.text((c3[0] + 70, M + 480 + shift), wx['hint'], font=font(66, 'DemiBold'), fill=ORANGE)
    if side and days:
        outlook(im, d, days, outlook_box)
    if side and radar:
        radar_map(im, radar, (c3[0], RADAR_TOP, c3[1], bottom))

    # Quote along the bottom.
    if day.get('quote'):
        d.text((W // 2, 2010), day['quote'], font=font(92, 'Medium'), fill=CREAM, anchor='mm')

    im.convert('RGB').save(out, quality=90)


def fit_artwork(src, out, mode='crop'):
    """Bring any picture to the Frame's 3840x2160.

    crop: fill the screen, trimming the overflow evenly (best for photos close to 16:9).
    fit:  show the whole picture, on a blurred, darkened copy of itself (portraits, panoramas).
    """
    from PIL import ImageOps
    im = ImageOps.exif_transpose(Image.open(src)).convert('RGB')  # phone photos carry their rotation in EXIF
    if mode == 'crop':
        im = ImageOps.fit(im, (W, H), Image.LANCZOS)
    else:
        bg = ImageOps.fit(im, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
        bg = Image.blend(bg, Image.new('RGB', (W, H), (12, 16, 22)), 0.35)
        scale = min(W / im.width, H / im.height)  # up or down, so small pictures fill the height too
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        bg.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
        im = bg
    im.save(out, quality=92)


TEXT_THEMES = {'dark': ((24, 28, 36), CREAM), 'light': ((244, 239, 228), (38, 44, 56))}


def render_text(text, out, theme='dark'):
    """A message on a plain, calm background: large, centred, nothing else."""
    bg, ink = TEXT_THEMES.get(theme, TEXT_THEMES['dark'])
    im = Image.new('RGB', (W, H), bg)
    d = ImageDraw.Draw(im)
    # Never break between a number and its unit ("16 Uhr", "5 €"), or after a lone word like "um".
    text = re.sub(r'(\d+)\s+(Uhr|€|Euro|Minuten|min)\b', '\\1\u00a0\\2', text)
    paragraphs = [p.strip() for p in text.strip().splitlines()]
    max_w, max_h = W - 2 * 400, H - 2 * 300
    size = 260
    while size > 80:
        f = font(size, 'DemiBold')
        lines = []
        for p in paragraphs:
            lines += wrap(d, p, f, max_w, max_lines=20) if p else ['']
        line_h = round(size * 1.3)
        if len(lines) * line_h <= max_h and all(d.textlength(l, font=f) <= max_w for l in lines):
            break
        size -= 10
    y = (H - len(lines) * line_h) // 2 + line_h // 2
    for line in lines:
        d.text((W // 2, y), line, font=f, fill=ink, anchor='mm')
        y += line_h
    im.save(out, quality=92)
