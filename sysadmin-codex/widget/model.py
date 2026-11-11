"""Dati locali del widget, indipendenti dalla grafica e dai provider."""
import copy
import datetime as dt
import json
import contextlib
import msvcrt
import os
import tempfile
import time
import uuid
from pathlib import Path
import paths

HERE = paths.DATA
CONFIG = HERE / 'config.json'
ENTRIES = HERE / 'obiettivi.json'
TRAINING = HERE / 'progressi.json'
TRAINING_SESSIONS = HERE / 'sessioni.json'
TRAINING_ACTIVE = HERE / 'sessione-attiva.json'

DEFAULTS = {
    'version': 1, 'selected': 'training',
    'goals': [{'id': 'training', 'name': 'Formazione Linux', 'kind': 'timer', 'weekly_target': 420}],
    'appearance': {'scale_percent': 100, 'opacity_percent': 100, 'accent': '#ffae85'},
    'github': {'enabled': False, 'username': '', 'year_mode': 'personal'},
    'integrations': {},
}


def read(path, default):
    if not path.exists():
        return copy.deepcopy(default)
    with path.open(encoding='utf-8') as f:
        return json.load(f)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + '-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def transaction_lock(target, timeout=3):
    """Serializza lettura-modifica-scrittura tra launcher, widget e tutor."""
    lock_path = target.parent / '.progressi.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+b') as lock:
        if lock.seek(0, os.SEEK_END) == 0:
            lock.write(b'\0')
            lock.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Il registro è occupato; riprova tra qualche secondo.') from None
                time.sleep(0.05)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def config():
    value = read(CONFIG, DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in value:
            value[key] = copy.deepcopy(default)
    return value


def selected_goal(cfg=None):
    cfg = cfg or config()
    return next((g for g in cfg['goals'] if g['id'] == cfg.get('selected')), cfg['goals'][0])


def new_goal(name, kind, target):
    if not name.strip() or kind not in ('timer', 'check') or not 1 <= target <= 10080:
        raise ValueError('Nome, tipo o obiettivo non valido.')
    return {'id': uuid.uuid4().hex, 'name': name.strip(), 'kind': kind, 'weekly_target': int(target)}


def now():
    return dt.datetime.now().astimezone()


def active(goal_id):
    if goal_id == 'training':
        return read(TRAINING_ACTIVE, {}).get('current_start')
    return read(ENTRIES, {'goals': {}}).get('goals', {}).get(goal_id, {}).get('started_at')


def values(goal_id, include_active=True):
    if goal_id == 'training':
        base = read(TRAINING, {'days': {}})
        days = {day: float(minutes)*60 for day, minutes in base.get('days', {}).items()}
        for item in read(TRAINING_SESSIONS, {'sessions': []}).get('sessions', []):
            for day, seconds in item.get('daily_seconds', {}).items():
                days[day] = days.get(day, 0) + seconds
    else:
        days = copy.deepcopy(read(ENTRIES, {'goals': {}}).get('goals', {}).get(goal_id, {}).get('days', {}))
    started = active(goal_id) if include_active else None
    if started:
        add_interval(days, dt.datetime.fromisoformat(started), now())
    return days


def add_interval(days, start, end):
    if end < start:
        raise ValueError('L’orologio è precedente all’inizio dell’attività.')
    while start.date() < end.date():
        boundary = (start + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        key = start.date().isoformat()
        days[key] = days.get(key, 0) + max(0, (boundary-start).total_seconds())
        start = boundary
    key = start.date().isoformat()
    days[key] = days.get(key, 0) + max(0, (end-start).total_seconds())


def toggle_timer(goal_id):
    if goal_id == 'training':
        # Usa lo stesso cronometro del tutor; mai creare due registri concorrenti.
        import sessione
        import sys
        old = sys.argv
        try:
            state = read(TRAINING_ACTIVE, {})
            action = 'fine' if state.get('current_start') else 'riprendi' if state else 'inizia'
            sys.argv = ['sessione.py', action]
            sessione.main()
        finally:
            sys.argv = old
        return
    with transaction_lock(ENTRIES):
        data = read(ENTRIES, {'goals': {}})
        entry = data.setdefault('goals', {}).setdefault(goal_id, {'days': {}})
        if entry.get('started_at'):
            add_interval(entry.setdefault('days', {}), dt.datetime.fromisoformat(entry['started_at']), now())
            entry.pop('started_at', None)
        else:
            entry['started_at'] = now().isoformat(timespec='seconds')
        save(ENTRIES, data)


def toggle_check(goal_id, day=None):
    if goal_id == 'training':
        raise ValueError('La formazione è un cronometro.')
    with transaction_lock(ENTRIES):
        data = read(ENTRIES, {'goals': {}})
        days = data.setdefault('goals', {}).setdefault(goal_id, {'days': {}}).setdefault('days', {})
        key = (day or dt.date.today()).isoformat()
        if days.get(key):
            days.pop(key)
        else:
            days[key] = 1
        save(ENTRIES, data)


def activate_selected():
    """Azione univoca del pulsante centrale e dell'obiettivo selezionato."""
    goal = selected_goal()
    if goal['kind'] == 'timer':
        toggle_timer(goal['id'])
    elif goal['kind'] == 'check':
        toggle_check(goal['id'])
    else:
        raise ValueError('Tipo di obiettivo non supportato.')
    return goal['id']
