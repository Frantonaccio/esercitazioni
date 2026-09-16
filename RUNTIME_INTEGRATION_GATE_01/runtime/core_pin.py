"""Controllo di versione del Core: il runtime rifiuta un Core non autorizzato.

Il pin NON e' una convenzione: e' un gate eseguito PRIMA di importare qualunque
modulo del Core. Quattro esiti, nessun fallback:

    CORE_PIN_OK          SHA osservato == SHA richiesto E working tree pulito
    STALE_CORE_PIN       SHA osservato e' un pin storico noto (es. 9afaddf, commit
                         iniziale del Core), superato dal canonical richiesto
    CORE_PIN_MISMATCH    qualunque altro SHA
    CORE_WORKTREE_DIRTY  SHA corretto ma il checkout ha modifiche non committate
                         o file non tracciati (T20): canonical SHA + exact tree

Lo SHA osservato si legge dal checkout reale (`git rev-parse HEAD`), non da un
file di dichiarazione: un file puo' mentire, il checkout no. Lo stesso vale per
la pulizia: `git status --porcelain` sul checkout che verra' importato. Un HEAD
giusto con un file modificato NON e' il Core canonical: e' un Core diverso con
lo stesso nome.
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

    def __init__(self, code: str, observed: str | None, required: str,
                 dirty: tuple[str, ...] = ()):
        self.code, self.observed, self.required, self.dirty = code, observed, required, dirty
        msg = f"{code}: osservato {observed!r}, richiesto {required!r}"
        if dirty:
            msg += f", working tree non pulito: {list(dirty)}"
        super().__init__(msg)


@dataclass(frozen=True)
class CorePinVerdict:
    code: str            # CORE_PIN_OK | STALE_CORE_PIN | CORE_PIN_MISMATCH | CORE_WORKTREE_DIRTY
    observed: str | None
    required: str
    dirty: tuple[str, ...] = ()     # righe di `git status --porcelain` del checkout

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


def resolve_core_dirty(core_path: str) -> tuple[str, ...] | None:
    """Righe di `git status --porcelain` del checkout del Core. Vuoto = pulito.

    Include modifiche a file tracciati, staging e file NON tracciati dentro il
    checkout (un modulo estraneo dentro il Core verrebbe importato come Core).
    I file ignorati da .gitignore (es. __pycache__) non contano. Cio' che sta
    fuori dal checkout (evidence, runtime del gate) non e' visto da git e non
    conta. None se git non risponde: si tratta come non verificabile.
    """
    try:
        out = subprocess.run(
            ["git", "-C", core_path, "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=True, timeout=30)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return tuple(line for line in out.stdout.splitlines() if line.strip())


def verify_core_pin(observed: str | None, required: str = REQUIRED_CORE_SHA,
                    dirty: tuple[str, ...] | None = ()) -> CorePinVerdict:
    """Funzione pura: nessun I/O. Testabile con qualunque SHA e stato dell'albero.

    Ordine: prima l'identita' (STALE / MISMATCH vincono), poi la pulizia.
    `dirty=None` (stato non verificabile) e' trattato come sporco: fail-closed.
    """
    if observed is None:
        return CorePinVerdict("CORE_PIN_MISMATCH", observed, required)
    observed = observed.strip().lower()
    if observed == required.lower():
        if dirty is None:
            return CorePinVerdict("CORE_WORKTREE_DIRTY", observed, required,
                                  ("<git status non disponibile>",))
        if dirty:
            return CorePinVerdict("CORE_WORKTREE_DIRTY", observed, required, tuple(dirty))
        return CorePinVerdict("CORE_PIN_OK", observed, required)
    if observed in KNOWN_STALE_CORE_SHAS:
        return CorePinVerdict("STALE_CORE_PIN", observed, required)
    return CorePinVerdict("CORE_PIN_MISMATCH", observed, required)


def require_core(core_path: str, required: str = REQUIRED_CORE_SHA) -> str:
    """Verifica pin E pulizia; restituisce lo SHA osservato. Solleva CorePinError altrimenti.

    A. HEAD == required   (altrimenti STALE_CORE_PIN / CORE_PIN_MISMATCH)
    B. working tree clean (altrimenti CORE_WORKTREE_DIRTY)
    Va chiamata PRIMA di aggiungere `core_path` a sys.path.
    """
    if not os.path.isdir(core_path):
        raise CorePinError("CORE_PIN_MISMATCH", None, required)
    v = verify_core_pin(resolve_core_sha(core_path), required,
                        resolve_core_dirty(core_path))
    if not v.ok:
        raise CorePinError(v.code, v.observed, v.required, v.dirty)
    return v.observed
