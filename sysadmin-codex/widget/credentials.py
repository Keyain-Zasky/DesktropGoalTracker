"""Credenziali opzionali protette da DPAPI, legate all'utente Windows corrente."""
import base64
import ctypes
from ctypes import wintypes as w
import model

PATH = model.HERE / 'credenziali.json'
crypt = ctypes.WinDLL('crypt32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)


class Blob(ctypes.Structure):
    _fields_ = [('cbData', w.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob), w.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_void_p, w.DWORD, ctypes.POINTER(Blob)]
crypt.CryptProtectData.restype = w.BOOL
crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p, w.DWORD, ctypes.POINTER(Blob)]
crypt.CryptUnprotectData.restype = w.BOOL
kernel.LocalFree.argtypes = [ctypes.c_void_p]
kernel.LocalFree.restype = ctypes.c_void_p


def transform(raw, encrypt):
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source = Blob(len(raw), buffer)
    result = Blob()
    operation = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree(result.pbData)


def put(provider, secret):
    if not secret:
        raise ValueError('Credenziale vuota.')
    data = model.read(PATH, {})
    data[provider] = base64.b64encode(transform(secret.encode('utf-8'), True)).decode('ascii')
    model.save(PATH, data)


def get(provider):
    data = model.read(PATH, {})
    encoded = data.get(provider)
    if not encoded:
        return None
    return transform(base64.b64decode(encoded), False).decode('utf-8')


def delete(provider):
    data = model.read(PATH, {})
    data.pop(provider, None)
    model.save(PATH, data)
