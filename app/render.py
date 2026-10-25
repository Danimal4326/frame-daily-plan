"""Render the daily plan for the Frame's Art Mode (3840x2160 JPEG).

Blurred, darkened background (normally the artwork the plan replaces) with calm
panels: date + month + to-dos, today, weather + tomorrow. No clock or news on
purpose: the image is static for hours and should never surprise anyone.
Fonts are Inter and Noto Color Emoji (both OFL, bundled in fonts/).
"""
import calendar
import datetime
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 3840, 2160
M = 180
CREAM = (255, 249, 238)
SOFT = (214, 210, 200)
DIM = (165, 162, 155)
ORANGE = (242, 150, 60)
COLORS = {'green': (120, 200, 170), 'orange': ORANGE, 'blue': (120, 160, 220), 'red': (232, 112, 112), 'grey': (170, 170, 170)}
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, 'fonts')
EMOJI = os.path.join(FONTS, 'NotoColorEmoji.ttf')  # colour bitmaps, only usable at size 109
LABELS = {
    'de': {'weekdays': ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'],
           'months': ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September',
                      'Oktober', 'November', 'Dezember'],
           'initials': 'MDMDFSS', 'today': 'Heute', 'tomorrow': 'Morgen', 'todos': 'Zu erledigen',
           'no_todos': 'Nichts zu erledigen', 'no_events': 'Keine Termine', 'more': '… und weitere',
           'past': 'vorbei', 'night': 'bis {}° in der Nacht', 'all_day': 'Ganztägig',
           'date': '{day}. {month}'},
    'en': {'weekdays': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
           'months': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
                      'October', 'November', 'December'],
           'initials': 'MTWTFSS', 'today': 'Today', 'tomorrow': 'Tomorrow', 'todos': 'To do',
           'no_todos': 'Nothing to do', 'no_events': 'No events', 'more': '… and more',
           'past': 'done', 'night': 'down to {}° tonight', 'all_day': 'All day',
           'date': '{month} {day}'},
}
L = LABELS['de']  # set per render


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


def events(d, items, x, y, w, bottom, scale=1.0):
    if not items:
        d.text((x, y), L['no_events'], font=font(70, 'Medium'), fill=DIM)
        return
    s = lambda v: round(v * scale)  # noqa: E731
    tf = font(s(74), 'DemiBold')
    for ev in items:
        lines = wrap(d, ev['title'], tf, w - 60)
        need = s(80) + len(lines) * s(92) + s(50)
        if y + need > bottom:
            d.text((x, y), L['more'], font=font(64, 'Medium'), fill=DIM)
            return
        past = ev.get('past')
        color = COLORS['grey'] if past else COLORS.get(ev.get('color', 'green'), COLORS['green'])
        d.rounded_rectangle([x, y + 8, x + 14, y + need - s(50)], radius=7, fill=color)
        times = ev.get('start', L['all_day']) + (f" – {ev['end']}" if ev.get('end') else '')
        d.text((x + 50, y), times + (f"  ·  {L['past']}" if past else ''), font=font(s(62), 'Medium'), fill=DIM if past else SOFT)
        for i, line in enumerate(lines):
            d.text((x + 50, y + s(80) + i * s(92)), line, font=tf, fill=DIM if past else CREAM)
        y += need


def month(d, date, x, y, w):
    d.text((x, y), L['months'][date.month - 1], font=font(72, 'DemiBold'), fill=CREAM)
    cw = w / 7
    y += 110
    for i, wd in enumerate(L['initials']):
        d.text((x + cw * i + cw / 2, y), wd, font=font(52, 'Medium'), fill=DIM, anchor='mt')
    y += 80
    for week in calendar.Calendar().monthdayscalendar(date.year, date.month):
        for i, day in enumerate(week):
            if not day:
                continue
            cx, cy = x + cw * i + cw / 2, y + 34
            if day == date.day:
                d.ellipse([cx - 46, cy - 46, cx + 46, cy + 46], fill=ORANGE)
            d.text((cx, cy), str(day), font=font(58, 'DemiBold' if day == date.day else 'Medium'),
                   fill=CREAM if day == date.day or i < 5 else SOFT, anchor='mm')
        y += 86


def render(day, out, background_path=None):
    global L
    L = LABELS.get(day.get('lang', 'de'), LABELS['de'])
    date = datetime.date.fromisoformat(day['date'])
    bg = background(background_path).convert('RGBA')
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))

    c1, c2, c3 = (M, 1230), (1310, 2490), (2570, W - M)
    # Without a quote the panels use the strip at the bottom too.
    top, bottom = 560, 1880 if day.get('quote') else H - M
    panel(layer, (c1[0], top, c1[1], 1300))
    panel(layer, (c1[0], 1350, c1[1], bottom), day.get('todo_title', L['todos']))
    panel(layer, (c2[0], M, c2[1], bottom), day.get('today_title', L['today']))
    panel(layer, (c3[0], M, c3[1], 820))
    panel(layer, (c3[0], 870, c3[1], bottom), L['tomorrow'])
    im = Image.alpha_composite(bg, layer)
    d = ImageDraw.Draw(im)

    # Date, top left.
    d.text((c1[0] + 10, M - 20), L['weekdays'][date.weekday()], font=font(190, 'Bold'), fill=CREAM)
    d.text((c1[0] + 14, M + 220), L['date'].format(day=date.day, month=L['months'][date.month - 1]), font=font(96, 'Medium'), fill=SOFT)
    month(d, date, c1[0] + 70, top + 50, c1[1] - c1[0] - 140)

    # To-dos with empty boxes.
    y = 1505
    if not day.get('todos'):
        d.text((c1[0] + 70, y), L['no_todos'], font=font(70, 'Medium'), fill=DIM)
    todos = day.get('todos', [])
    fits = (bottom - 40 - y) // 125
    if len(todos) > fits:
        todos = todos[:fits - 1] + [f'… und {len(todos) - fits + 1} weitere']
    # One size for the whole list, shrunk until the longest item fits inside the panel.
    size, max_w = 80, c1[1] - (c1[0] + 195) - 50
    while size > 52 and any(d.textlength(t, font=font(size, 'Medium')) > max_w for t in todos):
        size -= 2
    for todo in todos:
        d.rounded_rectangle([c1[0] + 70, y + 10, c1[0] + 155, y + 95], radius=18, outline=ORANGE, width=9)
        d.text((c1[0] + 195, y + (80 - size) // 2), todo, font=font(size, 'Medium'), fill=CREAM)
        y += 125

    events(d, day.get('today', []), c2[0] + 70, M + 200, c2[1] - c2[0] - 140, bottom - 40)

    # Weather: icon, temperatures, one concrete hint.
    wx = day.get('weather')
    if wx:
        ef = ImageFont.truetype(EMOJI, 109)
        icon = Image.new('RGBA', (140, 140), (0, 0, 0, 0))
        ImageDraw.Draw(icon).text((0, 0), wx['icon'], font=ef, embedded_color=True)
        icon = icon.resize((230, 230), Image.LANCZOS)
        im.alpha_composite(icon, (c3[0] + 70, M + 70))
        d.text((c3[0] + 340, M + 70), f"{wx['max']}°", font=font(150, 'DemiBold'), fill=CREAM)
        d.text((c3[0] + 340, M + 250), L['night'].format(wx['min']), font=font(58, 'Medium'), fill=SOFT)
        d.text((c3[0] + 70, M + 380), wx['text'], font=font(66, 'Medium'), fill=CREAM)
        if wx.get('hint'):
            d.text((c3[0] + 70, M + 480), wx['hint'], font=font(66, 'DemiBold'), fill=ORANGE)

    events(d, day.get('tomorrow', []), c3[0] + 70, 1070, c3[1] - c3[0] - 140, bottom - 40, scale=0.82)

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
    import re
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
