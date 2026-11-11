"""Monitor Windows identificati per nome dispositivo, in coordinate fisiche."""
import ctypes
from ctypes import wintypes as wt

user32 = ctypes.WinDLL('user32', use_last_error=True)


class MONITORINFOEX(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('rcMonitor', wt.RECT), ('rcWork', wt.RECT),
                ('dwFlags', wt.DWORD), ('szDevice', wt.WCHAR * 32)]


CALLBACK = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
user32.EnumDisplayMonitors.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), CALLBACK, wt.LPARAM]
user32.EnumDisplayMonitors.restype = wt.BOOL
user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFOEX)]
user32.GetMonitorInfoW.restype = wt.BOOL


def all_monitors():
    result = []

    @CALLBACK
    def add(handle, _dc, _rect, _data):
        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            rect = info.rcMonitor
            result.append({'id': info.szDevice, 'rect': (rect.left, rect.top, rect.right, rect.bottom),
                           'primary': bool(info.dwFlags & 1)})
        return True

    if not user32.EnumDisplayMonitors(None, None, add, 0) or not result:
        raise OSError('Impossibile rilevare gli schermi Windows.')
    return result


def choose(monitors, identifier):
    return next((m for m in monitors if m['id'] == identifier),
                next((m for m in monitors if m['primary']), monitors[0]))
