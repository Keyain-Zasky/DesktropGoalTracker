"""Percorsi applicazione e dati; i file personali non vivono nel programma."""
import os
import sys
from pathlib import Path

APP_NAME = 'DesktropGoalTracker'
RESOURCES = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
SOURCE = Path(__file__).resolve().parent
LOCAL_DATA = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / APP_NAME / 'Data'
MARKER = LOCAL_DATA / 'migrazione.json'


def data_directory():
    override = os.environ.get('DGT_DATA_DIR')
    if override:
        return Path(override)
    if getattr(sys, 'frozen', False) or MARKER.exists():
        return LOCAL_DATA
    return SOURCE


DATA = data_directory()
