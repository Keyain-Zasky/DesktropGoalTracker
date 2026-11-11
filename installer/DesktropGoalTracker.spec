# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import re
import sys
from PyInstaller.utils.hooks import collect_submodules
root = Path(SPECPATH).resolve().parent
src = root / 'sysadmin-codex' / 'widget'
sys.path.insert(0, str(src / 'vendor'))
a = Analysis([str(src / 'entry.py')], pathex=[str(src), str(src / 'vendor')],
    binaries=[], datas=[(str(src / 'app-icon.ico'), '.'), (str(src / 'GOOGLE-CALENDAR.md'), '.')],
    hiddenimports=['desktop', 'launcher'] + collect_submodules('google_auth_oauthlib'),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0)
# Qt uses Windows' ICU; a third-party ICU DLL shadows it and breaks QtCore.
a.binaries = [item for item in a.binaries if not (Path(item[0]).name.lower() == 'icuuc.dll' or re.fullmatch(r'icudt\d+\.dll', Path(item[0]).name.lower()))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DesktropGoalTracker',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False,
    disable_windowed_traceback=False, icon=str(src / 'app-icon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name='DesktropGoalTracker')
