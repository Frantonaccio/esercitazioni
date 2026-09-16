"""Sentinella di isolamento: nessuna credenziale, nessun subprocess provider, nessuna rete.

Usa `sys.addaudithook` (PEP 578): ogni `open`, `subprocess.Popen`, `socket.connect`
e `os.system` del processo passa di qui. Le violazioni si ACCUMULANO (non si
sollevano subito, per non mascherare il punto in cui il codice le ha tentate) e
il test le legge a fine corsa. Un test di controprova dimostra che la
sentinella intercetta davvero.

Le variabili d'ambiente non sono auditabili: si sostituisce `os.environ` con un
mapping che registra ogni accesso a una chiave segreta di provider.
"""
from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping

CREDENTIAL_PATH_MARKERS = (".higgsfield", "credentials.json", "higgsfield")
SECRET_ENV_MARKERS = ("HIGGSFIELD", "SEEDANCE", "KLING", "CINEMA_STUDIO", "API_KEY",
                      "SECRET", "TOKEN")
PROVIDER_BINARIES = ("higgsfield", "hf", "seedance", "kling")

VIOLATIONS: list[dict] = []


def _record(kind: str, detail: str) -> None:
    VIOLATIONS.append({"kind": kind, "detail": detail})


def _hook(event: str, args: tuple) -> None:
    if event == "open":
        path = str(args[0]) if args else ""
        low = path.lower()
        if any(m in low for m in CREDENTIAL_PATH_MARKERS):
            _record("credential_file_open", path)
    elif event == "subprocess.Popen":
        exe = str(args[0]) if args else ""
        argv = [str(a) for a in (args[1] or [])] if len(args) > 1 and args[1] else []
        joined = " ".join([exe, *argv]).lower()
        base = os.path.basename(exe).lower()
        if base in PROVIDER_BINARIES or any(f" {b} " in f" {joined} " for b in PROVIDER_BINARIES):
            _record("provider_subprocess", joined)
    elif event == "os.system":
        cmd = str(args[0]).lower() if args else ""
        if any(b in cmd for b in PROVIDER_BINARIES):
            _record("provider_os_system", cmd)
    elif event in ("socket.connect", "socket.create_connection", "socket.getaddrinfo"):
        _record("network", f"{event}:{args[:2]!r}")


class _TripwireEnviron(MutableMapping):
    """os.environ che registra ogni lettura di una chiave segreta di provider."""

    def __init__(self, inner):
        self._inner = inner

    def _check(self, key):
        k = str(key).upper()
        if any(m in k for m in SECRET_ENV_MARKERS):
            _record("secret_env_read", str(key))

    def __getitem__(self, key):
        self._check(key)
        return self._inner[key]

    def get(self, key, default=None):
        self._check(key)
        return self._inner.get(key, default)

    def __contains__(self, key):
        self._check(key)
        return key in self._inner

    def __setitem__(self, key, value):
        self._inner[key] = value

    def __delitem__(self, key):
        del self._inner[key]

    def __iter__(self):
        return iter(self._inner)

    def __len__(self):
        return len(self._inner)

    def copy(self):
        _record("secret_env_read", "<environ.copy>")
        return dict(self._inner)


def install(canary_home: str) -> None:
    """Attiva la sentinella. `canary_home` e' una HOME finta con credenziali esca."""
    hf_dir = os.path.join(canary_home, ".higgsfield")
    os.makedirs(hf_dir, exist_ok=True)
    with open(os.path.join(hf_dir, "credentials.json"), "w", encoding="utf-8") as fh:
        fh.write('{"api_key": "CANARY_DO_NOT_READ"}')
    os.environ["HOME"] = canary_home
    os.environ["HIGGSFIELD_API_KEY"] = "CANARY_DO_NOT_READ"
    os.environ["HIGGSFIELD_TOKEN"] = "CANARY_DO_NOT_READ"
    VIOLATIONS.clear()
    os.environ = _TripwireEnviron(os.environ)      # type: ignore[assignment]
    sys.addaudithook(_hook)


def violations() -> list[dict]:
    return list(VIOLATIONS)


def reset() -> None:
    VIOLATIONS.clear()
