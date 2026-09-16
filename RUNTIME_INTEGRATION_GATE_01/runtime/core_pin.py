"""Controllo di versione del Core: il runtime rifiuta un Core non autorizzato.

Il pin NON e' una convenzione: e' un gate eseguito PRIMA di importare qualunque
modulo del Core. Tre esiti, nessun fallback:

    CORE_PIN_OK        SHA osservato == SHA richiesto
    STALE_CORE_PIN     SHA osservato e' un pin storico noto (es. 9afaddf, commit
                       iniziale del Core), superato dal canonical richiesto
    CORE_PIN_MISMATCH  qualunque altro SHA

Lo SHA osservato si legge dal checkout reale (`git rev-parse HEAD`), non da un
file di dichiarazione: un file puo' mentire, il checkout no.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

# Core canonical richiesto da questo gate (PR #2 merged, C26 canonical).
REQUIRED_CORE_SHA = "819e7cfedb0f6641dc797e7993bec79462ac8df6"

# Pin storici noti: un Core a questo SHA NON e' un Core sconosciuto, e' un Core
# VECCHIO. Va rifiutato con un esito che lo dica.
KNOWN_STALE_CORE_SHAS = frozenset({
    "9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7",   # commit iniziale del Core
})


class CorePinError(RuntimeError):
    """Il Core disponibile non e' quello autorizzato. Nessun import, nessun run."""

    def __init__(self, code: str, observed: str | None, required: str):
        self.code, self.observed, self.required = code, observed, required
        super().__init__(f"{code}: osservato {observed!r}, richiesto {required!r}")


@dataclass(frozen=True)
class CorePinVerdict:
    code: str            # CORE_PIN_OK | STALE_CORE_PIN | CORE_PIN_MISMATCH
    observed: str | None
    required: str

    @property
    def ok(self) -> bool:
        return self.code == "CORE_PIN_OK"


def resolve_core_sha(core_path: str) -> str | None:
    """SHA del checkout del Core. None se il path non e' un repository git."""
    try:
        out = subprocess.run(
            ["git", "-C", core_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=30)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    sha = out.stdout.strip()
    return sha if len(sha) == 40 else None


def verify_core_pin(observed: str | None, required: str = REQUIRED_CORE_SHA) -> CorePinVerdict:
    """Funzione pura: nessun I/O. Testabile con qualunque SHA."""
    if observed is None:
        return CorePinVerdict("CORE_PIN_MISMATCH", observed, required)
    observed = observed.strip().lower()
    if observed == required.lower():
        return CorePinVerdict("CORE_PIN_OK", observed, required)
    if observed in KNOWN_STALE_CORE_SHAS:
        return CorePinVerdict("STALE_CORE_PIN", observed, required)
    return CorePinVerdict("CORE_PIN_MISMATCH", observed, required)


def require_core(core_path: str, required: str = REQUIRED_CORE_SHA) -> str:
    """Verifica il pin e restituisce lo SHA osservato. Solleva CorePinError altrimenti.

    Va chiamata PRIMA di aggiungere `core_path` a sys.path.
    """
    if not os.path.isdir(core_path):
        raise CorePinError("CORE_PIN_MISMATCH", None, required)
    v = verify_core_pin(resolve_core_sha(core_path), required)
    if not v.ok:
        raise CorePinError(v.code, v.observed, v.required)
    return v.observed
