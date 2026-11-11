"""Punto d'ingresso per l'app Windows e la relativa area di notifica."""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import paths

NAME = paths.APP_NAME
HERE = Path(__file__).resolve().parent
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowW.restype = ctypes.c_void_p
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.PostMessageW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
kernel.CreateMutexW.restype = ctypes.c_void_p
kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
kernel.OpenProcess.restype = ctypes.c_void_p
kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
kernel.WaitForSingleObject.restype = ctypes.c_ulong
kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
kernel.TerminateProcess.restype = ctypes.c_int
kernel.CloseHandle.argtypes = [ctypes.c_void_p]


def command(mode):
    if getattr(sys, 'frozen', False):
        return [sys.executable, mode]
    return [sys.executable, str(HERE / 'entry.py'), mode]


def launch(mode):
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return subprocess.Popen(command(mode), creationflags=flags, close_fds=True)


def post(title, message):
    hwnd = user32.FindWindowW(None, title)
    return bool(hwnd and user32.PostMessageW(hwnd, message, 0, 0))


def legacy_root():
    return Path.home() / 'Documents' / 'ChatGPT' / 'Training' / 'sysadmin-codex' / 'widget'


def migrate_legacy(source=None, destination=None):
    """Copia esclusivamente dati espliciti; non sovrascrive e non elimina l'originale."""
    source = Path(source or legacy_root())
    destination = Path(destination or paths.DATA)
    marker = destination / 'migrazione.json'
    if marker.exists():
        return []
    destination.mkdir(parents=True, exist_ok=True)
    names = ['config.json', 'progressi.json', 'sessioni.json', 'sessione-attiva.json',
             'obiettivi.json', 'preset-aspetto.json', 'credenziali.json', 'github-cache.json',
             'cache-google.json', 'cache-outlook.json', 'cache-todoist.json', 'cache-notion.json', 'cache-strava.json']
    copied = []
    if source.exists() and source.resolve() != destination.resolve():
        for name in names:
            original, target = source / name, destination / name
            if original.is_file() and not target.exists():
                fd, temp = tempfile.mkstemp(prefix='import-', suffix='.tmp', dir=destination)
                try:
                    with original.open('rb') as src, os.fdopen(fd, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                        dst.flush(); os.fsync(dst.fileno())
                    if not target.exists():
                        os.replace(temp, target)
                finally:
                    if os.path.exists(temp): os.unlink(temp)
                copied.append(name)
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps({'source': str(source), 'copied': copied}, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, marker)
    return copied


def set_autostart(enabled):
    import winreg
    key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if enabled:
            args = subprocess.list2cmdline(command('--tray'))
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, args)
        else:
            try: winreg.DeleteValue(key, NAME)
            except FileNotFoundError: pass


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            winreg.QueryValueEx(key, NAME)
            return True
    except FileNotFoundError:
        return False


def settings():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    import launcher
    app = QApplication(sys.argv[:1]); app.setApplicationName(NAME)
    app.setWindowIcon(QIcon(str(paths.RESOURCES / 'app-icon.ico')))
    window = launcher.Launcher(); window.setWindowTitle(NAME + ' · Impostazioni'); window.show()
    return app.exec()


def tray():
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
    from PySide6.QtGui import QIcon, QAction
    app = QApplication(sys.argv[:1]); app.setApplicationName(NAME); app.setQuitOnLastWindowClosed(False)
    ctypes.set_last_error(0)
    mutex = kernel.CreateMutexW(None, False, 'Local\\DesktropGoalTrackerTray')
    if not mutex: raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        launch('--settings'); return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, NAME, 'Area di notifica di Windows non disponibile.')
        return 1
    if getattr(sys, 'frozen', False) and not (paths.DATA / 'migrazione.json').exists():
        if user32.FindWindowW(None, 'Progressi · Centro di controllo'):
            QMessageBox.information(None, NAME, 'Chiudi prima il vecchio centro di controllo per conservare eventuali modifiche, poi riavvia il programma.')
            return 0
        # Una vecchia istanza può scrivere nel vecchio archivio durante la copia.
        old = user32.FindWindowW('TrainingProgressDesktopV2', 'Training Desktop Graphic')
        if old:
            answer = QMessageBox.question(None, NAME,
                'Per importare in modo sicuro i dati occorre chiudere il vecchio widget.\n\nChiuderlo ora e continuare?')
            if answer != QMessageBox.StandardButton.Yes: return 0
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(old, ctypes.byref(pid))
            process = kernel.OpenProcess(0x00100001, False, pid.value)  # SYNCHRONIZE | TERMINATE
            if not process:
                QMessageBox.warning(None, NAME, 'Impossibile chiudere il vecchio widget. Chiudilo e riavvia il programma.')
                return 1
            try:
                user32.PostMessageW(old, 0x0010, 0, 0)
                if kernel.WaitForSingleObject(process, 3000) == 0x102:
                    # Vecchie versioni distruggevano la finestra ma non terminavano il processo.
                    if not kernel.TerminateProcess(process, 0) or kernel.WaitForSingleObject(process, 3000) != 0:
                        QMessageBox.warning(None, NAME, 'Il vecchio widget è ancora attivo. Chiudilo e riavvia il programma.')
                        return 1
            finally:
                kernel.CloseHandle(process)
        try:
            migrate_legacy()
        except Exception as error:
            QMessageBox.critical(None, NAME, f'Importazione non completata. I file originali sono conservati.\n\n{error}')
            return 1
    icon = QIcon(str(paths.RESOURCES / 'app-icon.ico'))
    app.setWindowIcon(icon)
    tray_icon = QSystemTrayIcon(icon); tray_icon.setToolTip(NAME)
    menu = QMenu()
    open_action = QAction('Apri impostazioni', menu)
    open_action.triggered.connect(lambda: launch('--settings')); menu.addAction(open_action)
    toggle = QAction('Mostra / nascondi widget', menu)
    toggle.triggered.connect(lambda: post('Training Desktop Graphic', 0x800F)); menu.addAction(toggle)
    menu.addSeparator()
    startup = QAction('Avvia con Windows', menu); startup.setCheckable(True); startup.setChecked(autostart_enabled())
    def toggle_startup(checked):
        try: set_autostart(checked)
        except OSError as error:
            startup.setChecked(not checked)
            QMessageBox.warning(None, NAME, f'Impossibile modificare l’avvio automatico: {error}')
    startup.triggered.connect(toggle_startup); menu.addAction(startup)
    menu.addSeparator()
    quit_action = QAction('Esci', menu)
    def quit_app():
        post('Training Desktop Graphic', 0x0010)
        tray_icon.hide(); app.quit()
    quit_action.triggered.connect(quit_app); menu.addAction(quit_action)
    tray_icon.setContextMenu(menu)
    tray_icon.activated.connect(lambda reason: launch('--settings') if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray_icon.show()
    if not user32.FindWindowW('TrainingProgressDesktopV2', 'Training Desktop Graphic'):
        launch('--widget')
    return app.exec()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else '--tray'
    if mode == '--self-test':
        path = os.environ.get('DGT_SELFTEST_PATH')
        if not path or not os.environ.get('DGT_DATA_DIR'):
            raise SystemExit('La prova richiede un percorso e una cartella dati isolati.')
        result = {'ok': False}
        try:
            os.environ['QT_QPA_PLATFORM'] = 'offscreen'
            import desktop, launcher, model, providers, selection
            from google_auth_oauthlib.flow import InstalledAppFlow
            from PySide6.QtGui import QIcon
            from PySide6.QtWidgets import QApplication
            app = QApplication(sys.argv[:1])
            image = desktop.create_image()
            window = launcher.Launcher()
            before = model.config().get('appearance', {}).copy()
            window.rotation_slider.setValue(31)
            if model.config().get('appearance', {}) != before:
                raise ValueError('La bozza ha modificato le impostazioni salvate.')
            if QIcon(str(paths.RESOURCES / 'app-icon.ico')).isNull():
                raise ValueError('Icona non disponibile nel pacchetto.')
            if not (paths.RESOURCES / 'GOOGLE-CALENDAR.md').is_file():
                raise ValueError('Guida Google Calendar non disponibile.')
            result = {'ok': True, 'frozen': bool(getattr(sys, 'frozen', False)),
                      'image_size': list(image.size), 'preview_not_saved': True,
                      'icon_available': True, 'oauth_library_available': bool(InstalledAppFlow)}
            window.close()
        except Exception as error:
            import traceback
            from ctypes import wintypes as wt
            psapi = ctypes.WinDLL('psapi')
            kernel.GetCurrentProcess.restype = wt.HANDLE
            psapi.EnumProcessModules.argtypes = [wt.HANDLE, ctypes.POINTER(wt.HMODULE), wt.DWORD, ctypes.POINTER(wt.DWORD)]
            psapi.GetModuleFileNameExW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
            modules = (wt.HMODULE * 2048)(); needed = wt.DWORD(); process = kernel.GetCurrentProcess()
            psapi.EnumProcessModules(process, modules, ctypes.sizeof(modules), ctypes.byref(needed))
            libraries = []
            for item in modules[:needed.value // ctypes.sizeof(wt.HMODULE)]:
                filename = ctypes.create_unicode_buffer(2048)
                psapi.GetModuleFileNameExW(process, item, filename, 2048)
                if any(x in filename.value.lower() for x in ('qt6', 'pyside', 'shiboken', 'python3')):
                    libraries.append(filename.value)
            result = {'ok': False, 'error': f'{type(error).__name__}: {error}',
                      'traceback': traceback.format_exc(), 'libraries': libraries}
        Path(path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0 if result['ok'] else 1
    if mode == '--widget':
        import desktop
        desktop.main(); return 0
    if mode == '--settings': return settings()
    if mode == '--tray': return tray()
    raise SystemExit('Modalità non riconosciuta')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        user32.MessageBoxW(None, str(error), NAME, 0x10)
        raise
