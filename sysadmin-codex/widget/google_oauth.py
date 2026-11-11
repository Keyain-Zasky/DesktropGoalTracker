"""Flusso OAuth desktop Google Calendar in sola lettura, attivato dall'utente."""
import json
import sys
from pathlib import Path
import credentials

VENDOR = Path(__file__).resolve().parent / 'vendor'
sys.path.insert(0, str(VENDOR))
SCOPE = 'https://www.googleapis.com/auth/calendar.events.readonly'


def validate_client(config):
    installed = config.get('installed', {})
    client_id = installed.get('client_id', '')
    if not client_id.endswith('.apps.googleusercontent.com'):
        raise ValueError('Serve un file JSON di un client OAuth Google di tipo desktop.')
    if installed.get('auth_uri') != 'https://accounts.google.com/o/oauth2/auth':
        raise ValueError('Endpoint di autorizzazione Google inatteso.')
    if installed.get('token_uri') != 'https://oauth2.googleapis.com/token':
        raise ValueError('Endpoint token Google inatteso.')
    if not installed.get('client_secret'):
        raise ValueError('Nel client desktop manca il campo client_secret.')
    return config


def connect(client_file):
    from google_auth_oauthlib.flow import InstalledAppFlow
    with open(client_file, encoding='utf-8') as f:
        config = validate_client(json.load(f))
    flow = InstalledAppFlow.from_client_config(config, scopes=[SCOPE], autogenerate_code_verifier=True)
    result = flow.run_local_server(host='127.0.0.1', bind_addr='127.0.0.1', port=0,
                                   authorization_prompt_message=None, timeout_seconds=180,
                                   success_message='Autorizzazione completata. Puoi tornare al launcher.',
                                   access_type='offline', prompt='consent')
    if not result.refresh_token:
        raise ValueError('Google non ha rilasciato il rinnovo: ripeti l’autorizzazione.')
    credentials.put('google_oauth', result.to_json())
    return result.token


def access_token():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    encoded = credentials.get('google_oauth')
    if not encoded:
        return None
    value = Credentials.from_authorized_user_info(json.loads(encoded), scopes=[SCOPE])
    if not value.valid:
        value.refresh(Request())
        credentials.put('google_oauth', value.to_json())
    return value.token
