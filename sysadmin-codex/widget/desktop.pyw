"""Grafica desktop Windows: alpha per pixel, antialiasing e click-through."""
import calendar
import ctypes
import datetime as dt
import json
import math
import sys
import threading
import time
from pathlib import Path
from ctypes import wintypes as wt
sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from PIL import Image, ImageDraw
import model
import providers
import credentials
import google_oauth
import displays

HERE = model.HERE
DATA, SESSIONS = HERE / 'progressi.json', HERE / 'sessioni.json'
WIDTH, HEIGHT, SCALE = 2650, 450, 3
u = ctypes.WinDLL('user32', use_last_error=True)
g = ctypes.WinDLL('gdi32', use_last_error=True)
k = ctypes.WinDLL('kernel32', use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [('style', wt.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int), ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON),
                ('hCursor', wt.HANDLE), ('hbrBackground', wt.HBRUSH), ('lpszMenuName', wt.LPCWSTR),
                ('lpszClassName', wt.LPCWSTR)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG),
                ('biPlanes', wt.WORD), ('biBitCount', wt.WORD), ('biCompression', wt.DWORD),
                ('biSizeImage', wt.DWORD), ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG),
                ('biClrUsed', wt.DWORD), ('biClrImportant', wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wt.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [('BlendOp', wt.BYTE), ('BlendFlags', wt.BYTE),
                ('SourceConstantAlpha', wt.BYTE), ('AlphaFormat', wt.BYTE)]


def signature(lib, name, restype, args):
    f = getattr(lib, name)
    f.restype, f.argtypes = restype, args
    return f


signature(k, 'GetModuleHandleW', wt.HMODULE, [wt.LPCWSTR])
signature(k, 'CreateMutexW', wt.HANDLE, [wt.LPVOID, wt.BOOL, wt.LPCWSTR])
signature(u, 'RegisterClassW', wt.ATOM, [ctypes.POINTER(WNDCLASS)])
signature(u, 'CreateWindowExW', wt.HWND, [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
          ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID])
signature(u, 'DefWindowProcW', LRESULT, [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM])
signature(u, 'FindWindowW', wt.HWND, [wt.LPCWSTR, wt.LPCWSTR])
signature(u, 'GetWindow', wt.HWND, [wt.HWND, wt.UINT])
signature(u, 'IsWindowVisible', wt.BOOL, [wt.HWND])
signature(u, 'GetDC', wt.HDC, [wt.HWND])
signature(u, 'ReleaseDC', ctypes.c_int, [wt.HWND, wt.HDC])
signature(u, 'SetWindowPos', wt.BOOL, [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT])
signature(u, 'UpdateLayeredWindow', wt.BOOL, [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT),
          ctypes.POINTER(wt.SIZE), wt.HDC, ctypes.POINTER(wt.POINT), wt.COLORREF,
          ctypes.POINTER(BLENDFUNCTION), wt.DWORD])
signature(u, 'SetTimer', ctypes.c_size_t, [wt.HWND, ctypes.c_size_t, wt.UINT, wt.LPVOID])
signature(u, 'ShowWindow', wt.BOOL, [wt.HWND, ctypes.c_int])
signature(u, 'DestroyWindow', wt.BOOL, [wt.HWND])
signature(u, 'PostQuitMessage', None, [ctypes.c_int])
signature(u, 'MessageBoxW', ctypes.c_int, [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT])
signature(u, 'GetMessageW', wt.BOOL, [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT])
signature(u, 'TranslateMessage', wt.BOOL, [ctypes.POINTER(wt.MSG)])
signature(u, 'DispatchMessageW', LRESULT, [ctypes.POINTER(wt.MSG)])
signature(g, 'CreateCompatibleDC', wt.HDC, [wt.HDC])
signature(g, 'CreateDIBSection', wt.HBITMAP, [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
          ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD])
signature(g, 'SelectObject', wt.HANDLE, [wt.HDC, wt.HANDLE])
signature(g, 'DeleteObject', wt.BOOL, [wt.HANDLE])
signature(g, 'DeleteDC', wt.BOOL, [wt.HDC])


def totals(cfg=None):
    cfg = cfg or model.config()
    goal = model.selected_goal(cfg)
    target = int(goal['weekly_target']) * (60 if goal['kind'] == 'timer' else 1)
    return model.values(goal['id']), max(target, 1)


def input_signature():
    """Rileva anche creazione, rimozione e sostituzione atomica dei file."""
    signatures = []
    sources = [model.HERE / f'cache-{service}.json' for service in providers.SERVICES]
    for path in (DATA, SESSIONS, model.CONFIG, model.ENTRIES, model.TRAINING_ACTIVE, providers.CACHE, *sources):
        try:
            stat = path.stat()
            signatures.append((stat.st_mtime_ns, stat.st_size, stat.st_ino))
        except FileNotFoundError:
            signatures.append(None)
    cfg = model.config()
    active = model.active(model.selected_goal(cfg)['id'])
    return (dt.date.today(), int(time.time() // 30) if active else None, *signatures)


class RefreshController:
    def __init__(self):
        self.rendered = None

    def refresh(self, draw):
        before = input_signature()
        if before == self.rendered:
            return False
        draw()
        # Se un file è cambiato durante il disegno, riprovare al prossimo ciclo.
        after = input_signature()
        self.rendered = before if before == after else None
        return True


def shade(seconds, kind='timer'):
    if kind == 'check':
        seconds = 3600 if seconds else 0
    if seconds <= 0:
        return (43, 57, 73, 82)
    if seconds < 1800:
        return (177, 100, 83, 98)
    if seconds < 3600:
        return (222, 125, 93, 108)
    if seconds < 7200:
        return (255, 164, 119, 120)
    return (255, 210, 170, 132)


def create_image(today=None, config_override=None):
    today = today or dt.date.today()
    cfg = config_override or model.config()
    goal = model.selected_goal(cfg)
    kind = goal['kind']
    source = cfg.get('annual_source', cfg.get('github', {}).get('year_mode', 'personal'))
    external = (providers.external_cached(source, today.year, cfg.get('integrations', {}).get(source, {}))
                if source in providers.SERVICES else None)
    values, goal = totals(cfg)
    monday = today - dt.timedelta(days=today.weekday())
    weekly = sum(values.get((monday + dt.timedelta(days=i)).isoformat(), 0) for i in range(7))
    progress = min(weekly / max(goal, 1), 1)
    first, last = dt.date(today.year, 1, 1), dt.date(today.year, 12, 31)
    origin = first - dt.timedelta(days=first.weekday())
    result = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    # L'antialias 3x viene calcolato a strisce con un margine per il filtro:
    # stessa immagine, senza allocare un'intera tela 3x in memoria.
    strip_width, margin = 530, 4
    for left in range(0, WIDTH, strip_width):
        right = min(WIDTH, left + strip_width)
        source_left, source_right = max(0, left - margin), min(WIDTH, right + margin)
        image = Image.new('RGBA', ((source_right-source_left)*SCALE, HEIGHT*SCALE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        def box(b):
            return tuple(round((n - source_left if index % 2 == 0 else n)*SCALE)
                         for index, n in enumerate(b))

        def tile(x, y, color):
            if x + 27 < source_left or x > source_right:
                return
            draw.rounded_rectangle(box((x, y, x+27, y+27)), radius=round(27*.23*SCALE), fill=color)

        if source_left <= 350 and source_right >= 30:
            draw.arc(box((30, 65, 350, 385)), 0, 359.9, fill=(70, 88, 105, 88), width=22*SCALE)
            if progress > 0:
                start, end = -90, -90 + 359.9*progress
                steps = max(2, round(progress*360))
                points = []
                for step in range(steps + 1):
                    angle = math.radians(start + (end-start)*step/steps)
                    points.append((round((190+149*math.cos(angle)-source_left)*SCALE),
                                   round((225+149*math.sin(angle))*SCALE)))
                draw.line(points, fill=(255, 174, 133, 125), width=22*SCALE, joint='curve')
                for x, y in (points[0], points[-1]):
                    radius = 11*SCALE
                    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(255, 174, 133, 125))
        for row, week in enumerate(calendar.Calendar(0).monthdatescalendar(today.year, today.month)):
            for col, day in enumerate(week):
                if day.month == today.month:
                    tile(415 + col*36, 116 + row*36, shade(values.get(day.isoformat(), 0), kind))
        git = cfg.get('github', {})
        cache = providers.github_cached(git.get('username', ''), today.year) if git.get('enabled') and source == 'github' else None
        git_values = cache['levels'] if cache else None
        day = first
        while day <= last:
            value = values.get(day.isoformat(), 0)
            if source == 'github':
                # Livelli GitHub distinti dai secondi degli obiettivi personali.
                level = git_values.get(day.isoformat(), 0) if git_values is not None else 0
                value = (0, 900, 2700, 5400, 9000)[level]
            elif source in providers.SERVICES:
                count = external['counts'].get(day.isoformat(), 0) if external else 0
                value = 0 if count == 0 else 900 if count == 1 else 2700 if count <= 3 else 5400 if count <= 6 else 9000
            tile(710 + ((day-origin).days // 7)*36, 116 + day.weekday()*36,
                 shade(value, 'timer' if source != 'personal' else kind))
            day += dt.timedelta(days=1)
        resized = image.resize((source_right-source_left, HEIGHT), Image.Resampling.LANCZOS)
        result.paste(resized.crop((left-source_left, 0, right-source_left, HEIGHT)), (left, 0))
    ap = cfg.get('appearance', {})
    accent = ap.get('accent', '#ffae85')
    if accent.lower() != '#ffae85':
        rgb = tuple(int(accent[i:i+2], 16) for i in (1, 3, 5))
        # Ricolora solo gli elementi caldi; lo sfondo neutro rimane riconoscibile.
        pixels = result.load()
        for yy in range(HEIGHT):
            for xx in range(WIDTH):
                r, g_, b, a = pixels[xx, yy]
                if a and r > g_ * 1.10 and r > b * 1.10:
                    ratio = r / 255
                    pixels[xx, yy] = (int(rgb[0]*ratio), int(rgb[1]*ratio), int(rgb[2]*ratio), a)
    opacity = max(20, min(150, int(ap.get('opacity_percent', 100)))) / 100
    if opacity != 1:
        result.putalpha(result.getchannel('A').point(lambda a: min(255, round(a*opacity))))
    percent = max(50, min(140, int(ap.get('scale_percent', 100))))
    if percent != 100:
        result = result.resize((round(WIDTH*percent/100), round(HEIGHT*percent/100)), Image.Resampling.LANCZOS)
    angle = max(-180, min(180, int(ap.get('rotation_degrees', 0))))
    if angle:
        result = result.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    return result


def layout(image_size, monitor_rect, appearance):
    """Centro nel monitor scelto, poi traslazione e rotazione del pulsante."""
    left, top, right, bottom = monitor_rect
    width, height = image_size
    x = left + (right-left-width)//2 + int(appearance.get('offset_x', 0))
    y = top + (bottom-top-height)//2 + int(appearance.get('offset_y', 0))
    ratio = max(50, min(140, int(appearance.get('scale_percent', 100)))) / 100
    angle = math.radians(max(-180, min(180, int(appearance.get('rotation_degrees', 0)))))
    dx, dy = (190-WIDTH/2)*ratio, (225-HEIGHT/2)*ratio
    center_x = x + width/2 + math.cos(angle)*dx - math.sin(angle)*dy
    center_y = y + height/2 + math.sin(angle)*dx + math.cos(angle)*dy
    size = max(30, round(100*ratio))
    return x, y, round(center_x-size/2), round(center_y-size/2), size


def button_enabled(appearance, goal):
    return appearance.get('manual_timer_enabled', True) or goal['kind'] == 'check'


def paint_image(hwnd, image, x, y):
    # UpdateLayeredWindow richiede BGRA premoltiplicato, con alpha per ogni pixel.
    width, height = image.size
    premul = image.convert('RGBa').tobytes('raw', 'BGRa')
    screen = u.GetDC(None)
    memdc = g.CreateCompatibleDC(screen)
    info = BITMAPINFO()
    info.bmiHeader = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    bitmap = g.CreateDIBSection(screen, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
    if not bitmap or not memdc:
        raise ctypes.WinError(ctypes.get_last_error())
    previous = g.SelectObject(memdc, bitmap)
    try:
        ctypes.memmove(bits, premul, len(premul))
        dest, size, src = wt.POINT(x, y), wt.SIZE(width, height), wt.POINT(0, 0)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        if not u.UpdateLayeredWindow(hwnd, screen, ctypes.byref(dest), ctypes.byref(size), memdc,
                                     ctypes.byref(src), 0, ctypes.byref(blend), 2):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        g.SelectObject(memdc, previous)
        g.DeleteObject(bitmap)
        g.DeleteDC(memdc)
        u.ReleaseDC(None, screen)


def github_worker():
    while True:
        try:
            settings = model.config()
            cfg = settings.get('github', {})
            if cfg.get('enabled') and cfg.get('username'):
                cache = providers.github_cached(cfg['username'])
                fetched = dt.datetime.fromisoformat(cache['fetched_at']).timestamp() if cache else 0
                if time.time() - fetched >= 3600:
                    providers.github_fetch(cfg['username'])
        except Exception:
            import traceback
            traceback.print_exc()
        for service, options in settings.get('integrations', {}).items() if 'settings' in locals() else ():
            try:
                if service not in providers.SERVICES:
                    continue
                cache = providers.external_cached(service, options=options)
                fetched = dt.datetime.fromisoformat(cache['fetched_at']).timestamp() if cache else 0
                if time.time() - fetched >= 3600:
                    token = (google_oauth.access_token() if service == 'google' and credentials.get('google_oauth')
                             else credentials.get(service))
                    if token:
                        providers.external_fetch(service, token, options)
            except Exception as error:
                print(f'{service}: {error}', flush=True)
        time.sleep(300)


def button_image(size, goal, active):
    scale = 3
    image = Image.new('RGBA', (size*scale, size*scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size*scale
    draw.ellipse((s*.10, s*.10, s*.90, s*.90), fill=(41, 52, 65, 110),
                 outline=(255, 190, 155, 135), width=max(2, round(s*.025)))
    ink = (255, 208, 178, 205)
    if goal['kind'] == 'check':
        done = bool(model.values(goal['id']).get(dt.date.today().isoformat(), 0))
        if done:
            draw.line([(s*.30, s*.50), (s*.44, s*.64), (s*.70, s*.35)], fill=ink,
                      width=max(3, round(s*.07)), joint='curve')
        else:
            draw.ellipse((s*.35, s*.35, s*.65, s*.65), outline=ink, width=max(3, round(s*.045)))
    elif active:
        draw.rounded_rectangle((s*.34, s*.30, s*.66, s*.70), radius=s*.04, fill=ink)
    else:
        draw.polygon([(s*.38, s*.28), (s*.38, s*.72), (s*.70, s*.50)], fill=ink)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    mutex = k.CreateMutexW(None, False, 'Local\\TrainingDesktopProgressWidget')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    refresh = RefreshController()
    windows = {'main': None, 'button': None, 'visible': True}

    def redraw():
        cfg = model.config()
        goal = model.selected_goal(cfg)
        appearance = cfg.get('appearance', {})
        image = create_image()
        monitor = displays.choose(displays.all_monitors(), appearance.get('monitor', ''))
        x, y, bx, by, size = layout(image.size, monitor['rect'], appearance)
        paint_image(windows['main'], image, x, y)
        enabled = button_enabled(appearance, goal) and windows['visible']
        if enabled:
            paint_image(windows['button'], button_image(size, goal, bool(model.active(goal['id']))), bx, by)
            u.ShowWindow(windows['button'], 4)  # SW_SHOWNOACTIVATE
            # Il pulsante resta sopra la grafica ma sotto le finestre delle app.
            preceding = u.GetWindow(windows['main'], 3)
            while preceding and (preceding == windows['button'] or not u.IsWindowVisible(preceding)):
                preceding = u.GetWindow(preceding, 3)
            if preceding:
                u.SetWindowPos(windows['button'], preceding, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        else:
            u.ShowWindow(windows['button'], 0)  # SW_HIDE

    def activate_goal():
        try:
            cfg = model.config()
            if not cfg.get('appearance', {}).get('manual_timer_enabled', True) and model.selected_goal(cfg)['kind'] == 'timer':
                return
            model.activate_selected()
            refresh.rendered = None
            refresh.refresh(redraw)
        except BaseException as error:
            u.MessageBoxW(None, str(error), 'Progressi', 0x10)

    @WNDPROC
    def wndproc(hwnd, msg, wp, lp):
        if hwnd == windows['button']:
            if msg == 0x0021:  # WM_MOUSEACTIVATE
                return 3      # MA_NOACTIVATE
            if msg == 0x0202:  # WM_LBUTTONUP
                activate_goal()
                return 0
            return u.DefWindowProcW(hwnd, msg, wp, lp)
        if msg == 0x0084:  # WM_NCHITTEST: passa i clic al desktop
            return -1
        if msg == 0x0010:  # WM_CLOSE: anche il processo nativo deve terminare
            if windows['button']:
                u.DestroyWindow(windows['button'])
            u.DestroyWindow(hwnd)
            u.PostQuitMessage(0)
            return 0
        if msg == 0x800F:  # mostra/nascondi dal menu dell'area di notifica
            windows['visible'] = not windows['visible']
            u.ShowWindow(hwnd, 4 if windows['visible'] else 0)
            if windows['visible']:
                refresh.rendered = None
                refresh.refresh(redraw)
            else:
                u.ShowWindow(windows['button'], 0)
            return 0
        if msg in (0x0113, 0x800E, 0x007E):  # timer, applica, cambio monitor
            try:
                if msg != 0x0113:
                    refresh.rendered = None
                refresh.refresh(redraw)
            except Exception:
                import traceback
                traceback.print_exc()
            return 0
        return u.DefWindowProcW(hwnd, msg, wp, lp)

    instance = k.GetModuleHandleW(None)
    name = 'TrainingProgressDesktopV2'
    klass = WNDCLASS(0, wndproc, 0, 0, instance, None, None, None, None, name)
    if not u.RegisterClassW(ctypes.byref(klass)):
        raise ctypes.WinError(ctypes.get_last_error())
    hwnd = u.CreateWindowExW(0x00080000 | 0x00000020 | 0x00000080 | 0x08000000,
                             name, 'Training Desktop Graphic', 0x80000000,
                             0, 0, WIDTH, HEIGHT, None, None, instance, None)
    if not hwnd:
        raise ctypes.WinError(ctypes.get_last_error())
    windows['main'] = hwnd
    button = u.CreateWindowExW(0x00080000 | 0x00000080 | 0x08000000,
                               name, 'Training Progress Button', 0x80000000,
                               0, 0, 100, 100, None, None, instance, None)
    if not button:
        raise ctypes.WinError(ctypes.get_last_error())
    windows['button'] = button
    refresh.refresh(redraw)
    desktop = u.FindWindowW('Progman', None)
    if not desktop:
        raise OSError('Desktop di Windows non trovato')
    preceding = u.GetWindow(desktop, 3)
    while preceding and (preceding == hwnd or not u.IsWindowVisible(preceding)):
        preceding = u.GetWindow(preceding, 3)
    u.SetWindowPos(hwnd, preceding or wt.HWND(1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)
    preceding_button = u.GetWindow(hwnd, 3)
    while preceding_button and (preceding_button == button or not u.IsWindowVisible(preceding_button)):
        preceding_button = u.GetWindow(preceding_button, 3)
    if preceding_button:
        u.SetWindowPos(button, preceding_button, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
    else:
        u.SetWindowPos(button, wt.HWND(0), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
    u.SetTimer(hwnd, 1, 30000, None)
    threading.Thread(target=github_worker, daemon=True).start()
    msg = wt.MSG()
    while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u.TranslateMessage(ctypes.byref(msg))
        u.DispatchMessageW(ctypes.byref(msg))


if __name__ == '__main__':
    main()
