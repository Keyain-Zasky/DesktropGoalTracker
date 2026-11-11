"""Provider in sola lettura; i risultati sono cache separate dai dati personali."""
import datetime as dt
import calendar
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
import model

CACHE = model.HERE / 'github-cache.json'
USERNAME = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$')
SERVICES = {
    'google': ('Google Calendar', 'www.googleapis.com'),
    'outlook': ('Outlook Calendar', 'graph.microsoft.com'),
    'todoist': ('Todoist', 'api.todoist.com'),
    'notion': ('Notion', 'api.notion.com'),
    'strava': ('Strava', 'www.strava.com'),
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Reindirizzamento inatteso: sincronizzazione interrotta.')


def request_json(service, url, token, body=None):
    expected = SERVICES[service][1]
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != expected or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Indirizzo del servizio non valido.')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json', 'User-Agent': 'ProgressiDesktop/1.0'}
    if service == 'notion':
        headers['Notion-Version'] = '2025-09-03'
    if service == 'outlook':
        headers['Prefer'] = 'outlook.timezone="W. Europe Standard Time"'
    payload = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        payload = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=25) as response:
            raw = response.read(5_000_001)
    except urllib.error.HTTPError as error:
        raise ValueError(f'{SERVICES[service][0]}: errore HTTP {error.code}. Controlla credenziale, permessi e parametri.') from None
    if len(raw) > 5_000_000:
        raise ValueError('Risposta del servizio troppo grande.')
    return json.loads(raw)


def query(base, params):
    return base + '?' + urllib.parse.urlencode(params)


def options_id(options):
    """Associa la cache alla connessione senza includere token o dettagli remoti."""
    serialized = json.dumps(options or {}, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def local_day(value):
    if not value:
        return None
    try:
        if len(value) == 10:
            return dt.date.fromisoformat(value).isoformat()
        date = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.astimezone().date().isoformat() if date.tzinfo else date.date().isoformat()
    except ValueError:
        return None


def external_fetch(service, token, options=None, year=None):
    """Scarica solo dati in lettura e salva esclusivamente i conteggi giornalieri."""
    if service not in SERVICES:
        raise ValueError('Servizio non supportato.')
    options, year = options or {}, year or dt.date.today().year
    counts = {}
    def add(value):
        day = local_day(value)
        if day and day.startswith(f'{year}-'):
            counts[day] = counts.get(day, 0) + 1
    def items(data, key):
        if not isinstance(data, dict) or not isinstance(data.get(key), list):
            raise ValueError(f'{SERVICES[service][0]}: risposta incompleta o inattesa; cache conservata.')
        return data[key]
    start, end = f'{year}-01-01T00:00:00Z', f'{year+1}-01-01T00:00:00Z'
    if service == 'google':
        calendar_id = options.get('calendar_id', 'primary') or 'primary'
        base = 'https://www.googleapis.com/calendar/v3/calendars/' + urllib.parse.quote(calendar_id, safe='') + '/events'
        params = {'timeMin': start, 'timeMax': end, 'singleEvents': 'true', 'maxResults': 2500}
        for _ in range(100):
            data = request_json(service, query(base, params), token)
            for item in items(data, 'items'):
                if item.get('status') != 'cancelled':
                    add(item.get('start', {}).get('dateTime') or item.get('start', {}).get('date'))
            cursor = data.get('nextPageToken')
            if not cursor: break
            params['pageToken'] = cursor
        else: raise ValueError('Limite pagine Google Calendar superato.')
    elif service == 'outlook':
        url = query('https://graph.microsoft.com/v1.0/me/calendarView',
                    {'startDateTime': start, 'endDateTime': end, '$select': 'start,isCancelled', '$top': 1000})
        for _ in range(100):
            data = request_json(service, url, token)
            for item in items(data, 'value'):
                if not item.get('isCancelled'):
                    add(item.get('start', {}).get('dateTime'))
            url = data.get('@odata.nextLink')
            if not url: break
        else: raise ValueError('Limite pagine Outlook superato.')
    elif service == 'todoist':
        base = 'https://api.todoist.com/api/v1/tasks/completed/by_completion_date'
        # L'API limita ogni intervallo a tre mesi.
        for month in (1, 4, 7, 10):
            until = f'{year+1}-01-01T00:00:00Z' if month == 10 else f'{year}-{month+3:02d}-01T00:00:00Z'
            params = {'since': f'{year}-{month:02d}-01T00:00:00Z', 'until': until, 'limit': 200}
            for _ in range(100):
                data = request_json(service, query(base, params), token)
                for item in items(data, 'items'): add(item.get('completed_at'))
                cursor = data.get('next_cursor')
                if not cursor: break
                params['cursor'] = cursor
            else: raise ValueError('Limite pagine Todoist superato.')
    elif service == 'strava':
        start_epoch = int(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        end_epoch = int(dt.datetime(year+1, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        base = 'https://www.strava.com/api/v3/athlete/activities'
        for page in range(1, 101):
            data = request_json(service, query(base, {'after': start_epoch, 'before': end_epoch, 'per_page': 200, 'page': page}), token)
            if not isinstance(data, list): raise ValueError('Risposta Strava inattesa.')
            for item in data:
                # Strava codifica start_date_local con suffisso Z, ma le cifre
                # rappresentano già l'ora locale dell'attività.
                local = item.get('start_date_local')
                add(local[:10] if local else item.get('start_date'))
            if len(data) < 200: break
        else: raise ValueError('Limite pagine Strava superato.')
    else:
        source_id = options.get('data_source_id', '').strip()
        prop = options.get('date_property', '').strip()
        if not re.fullmatch(r'[0-9a-fA-F-]{32,36}', source_id) or not prop:
            raise ValueError('Notion richiede ID data source e nome proprietà data.')
        url = f'https://api.notion.com/v1/data_sources/{source_id}/query'
        body = {'page_size': 100}
        for _ in range(100):
            data = request_json(service, url, token, body)
            for page in items(data, 'results'):
                if page.get('object', 'page') != 'page':
                    continue
                if prop not in page.get('properties', {}):
                    raise ValueError('Proprietà data Notion non trovata; controlla il nome. Cache conservata.')
                item = page.get('properties', {}).get(prop, {})
                if item.get('type') != 'date':
                    raise ValueError('La proprietà Notion selezionata non è una data; cache conservata.')
                if item.get('type') == 'date' and item.get('date'):
                    add(item['date'].get('start'))
            cursor = data.get('next_cursor')
            if data.get('has_more') and not cursor:
                raise ValueError('Paginazione Notion incompleta; cache conservata.')
            if not cursor: break
            body['start_cursor'] = cursor
        else: raise ValueError('Limite pagine Notion superato.')
    result = {'service': service, 'year': year, 'counts': counts, 'connection_hash': options_id(options),
              'fetched_at': dt.datetime.now().astimezone().isoformat(timespec='seconds')}
    model.save(model.HERE / f'cache-{service}.json', result)
    return result


def external_cached(service, year=None, options=None):
    if service not in SERVICES:
        return None
    data = model.read(model.HERE / f'cache-{service}.json', {})
    if data.get('year') != (year or dt.date.today().year):
        return None
    if options is not None and data.get('connection_hash') != options_id(options):
        return None
    return data


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days = {}

    def handle_starttag(self, tag, attrs):
        if tag != 'td':
            return
        attrs = dict(attrs)
        day, level = attrs.get('data-date'), attrs.get('data-level')
        if day and level is not None:
            try:
                dt.date.fromisoformat(day)
                level = int(level)
            except ValueError:
                return
            if 0 <= level <= 4:
                self.days[day] = level


def github_fetch(username, year=None):
    username = username.strip()
    if not USERNAME.fullmatch(username):
        raise ValueError('Nome GitHub non valido.')
    year = year or dt.date.today().year
    url = (f'https://github.com/users/{urllib.parse.quote(username)}/contributions'
           f'?from={year}-01-01&to={year}-12-31')
    request = urllib.request.Request(url, headers={'User-Agent': 'ProgressiDesktop/1.0',
                                                   'Accept': 'text/html'})
    with urllib.request.urlopen(request, timeout=20) as response:
        content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError('Risposta GitHub troppo grande.')
    parser = CalendarParser()
    parser.feed(content.decode('utf-8'))
    days = {day: level for day, level in parser.days.items() if day.startswith(str(year)+'-')}
    # Una risposta vuota o incompleta non sovrascrive una cache valida.
    if len(days) != (366 if calendar.isleap(year) else 365):
        raise ValueError('Calendario GitHub incompleto o profilo non disponibile.')
    result = {'username': username, 'year': year, 'levels': days,
              'fetched_at': dt.datetime.now().astimezone().isoformat(timespec='seconds')}
    model.save(CACHE, result)
    return result


def github_cached(username, year=None):
    cache = model.read(CACHE, {})
    if cache.get('username', '').lower() != username.strip().lower() or cache.get('year') != (year or dt.date.today().year):
        return None
    return cache
