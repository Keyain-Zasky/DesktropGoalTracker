"""Cronometro esplicito di sessione; non indovina attività o pause."""
import argparse
import datetime as dt
import json
import model
import os
from pathlib import Path

ROOT = model.HERE
STATE = ROOT / 'sessione-attiva.json'
SESSIONS = ROOT / 'sessioni.json'


def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def now():
    return dt.datetime.now().astimezone()


def parse(value):
    return dt.datetime.fromisoformat(value)


def distribute(intervals):
    days = {}
    for start, end in intervals:
        begin, stop = parse(start), parse(end)
        if stop < begin:
            raise ValueError('L’orologio è precedente all’inizio; non registro la sessione.')
        while begin.date() < stop.date():
            boundary = (begin + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            days[begin.date().isoformat()] = days.get(begin.date().isoformat(), 0) + (boundary - begin).total_seconds()
            begin = boundary
        days[begin.date().isoformat()] = days.get(begin.date().isoformat(), 0) + (stop - begin).total_seconds()
    return {k: round(v) for k, v in days.items()}


def _execute():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['inizia', 'pausa', 'riprendi', 'fine', 'stato'])
    action = parser.parse_args().action
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else None
    stamp = now().isoformat(timespec='seconds')
    if action == 'stato':
        print(json.dumps(state, ensure_ascii=False) if state else 'Nessuna sessione attiva')
        return
    if action == 'inizia':
        if state:
            raise SystemExit('Sessione già aperta: verifica stato e pause prima di continuare.')
        save(STATE, {'started_at': stamp, 'current_start': stamp, 'intervals': []})
        print('Sessione iniziata:', stamp)
        return
    if not state:
        raise SystemExit('Nessuna sessione aperta.')
    if action == 'riprendi':
        if state['current_start']:
            raise SystemExit('Sessione già in corso.')
        state['current_start'] = stamp
        save(STATE, state)
        print('Sessione ripresa:', stamp)
        return
    if action == 'pausa' and not state['current_start']:
        raise SystemExit('Sessione già in pausa.')
    if state['current_start']:
        state['intervals'].append([state['current_start'], stamp])
        state['current_start'] = None
    if action == 'pausa':
        save(STATE, state)
        print('Sessione in pausa:', stamp)
        return
    records = json.loads(SESSIONS.read_text(encoding='utf-8')) if SESSIONS.exists() else {'sessions': []}
    if any(item['started_at'] == state['started_at'] for item in records['sessions']):
        raise SystemExit('Sessione già registrata: verificare il file attivo prima di ripetere.')
    daily = distribute(state['intervals'])
    records['sessions'].append({'started_at': state['started_at'], 'ended_at': stamp,
                                'intervals': state['intervals'], 'daily_seconds': daily})
    save(SESSIONS, records)
    STATE.unlink()
    print('Sessione registrata:', sum(daily.values()), 'secondi')


def main():
    with model.transaction_lock(STATE):
        _execute()


if __name__ == '__main__':
    main()
