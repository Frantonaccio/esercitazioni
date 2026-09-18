"""Controllo di versione del Core: il runtime rifiuta un Core non autorizzato.

Il pin NON e' una convenzione: e' un gate eseguito PRIMA di importare qualunque
modulo del Core. Quattro esiti, nessun fallback:

    CORE_PIN_OK          SHA osservato == SHA richiesto E working tree pulito
    STALE_CORE_PIN       SHA osservato e' un pin storico noto (es. 9afaddf, commit
                         iniziale del Core), superato dal canonical richiesto
    CORE_PIN_MISMATCH    qualunque altro SHA
    CORE_WORKTREE_DIRTY  SHA corretto ma il checkout ha modifiche non committate
                         o file non tracciati (T20): canonical SHA + exact tree

CONTROLLED PROMOTION (2026-09-16): l'esito LAB-only CORE_CANDIDATE_OK, che
accettava un tree sporco identificato da (SHA base, digest del delta dichiarato
via CREATIVE_OS_CORE_CANDIDATE_DELTA), e' stato RIMOSSO. Il runtime promosso
pinna SOLO un commit reale del Core: SHA esatto + working tree pulito. Nessun
digest sostituisce lo SHA.

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

# Core richiesto da questo runtime.
#
# LEGACY SPEND PATH CLOSURE (2026-09-18). Il runtime pretende ora il CONFINE DELLO
# SPENDER del Core (`adapters.base.SpendCapableAdapter`, `authorize_dispatch`,
# `grant_dispatch`, `require_governed_dispatch_inputs`): senza quel confine, un adapter
# capace di raggiungere un provider reale sarebbe dispacciabile da
# `transport.pipeline.run_job` e da `adapter.submit` diretto, cioe' la garanzia che
# questo runtime dichiara non esisterebbe. Il pin si sposta quindi sul commit che la
# porta: un runtime che pretende quell'invariante non puo' dichiararsi compatibile con
# un Core che non ce l'ha.
#
# HUMAN REVIEW 01 (DISPATCH_AUTHORIZATION_FORGEABLE): il pin si sposta ancora, sul
# delta correttivo. Il confine di `44f9ea29` si apriva con un'autorizzazione che il
# chiamante poteva costruire; quello di `605a8d74` pretende che la concessione nasca
# da una rilettura del journal. Un runtime che dichiara "lo spender e' raggiungibile
# solo dal percorso governato" non puo' pinnare il Core in cui quella frase era falsa.
# Core candidate: Frantonaccio/creative-os, branch
# harden/legacy-spend-core-2026-09-18, discendente della baseline canonica
# 9cf9cee1a751f7a2ad6c768574ff5aa38d8db515.
REQUIRED_CORE_SHA = "605a8d746fdafbfc33456ec6f26fa942947a43b9"

# Pin storici noti: un Core a questo SHA NON e' un Core sconosciuto, e' un Core
# VECCHIO. Va rifiutato con un esito che lo dica.
KNOWN_STALE_CORE_SHAS = frozenset({
    "9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7",   # commit iniziale del Core
    # Baseline canonica di COORDINATED CORE + RUNTIME INTEGRATION. Un runtime che consuma
    # `mark_refused_pre_submit` contro questo Core fallirebbe con AttributeError a meta'
    # percorso; qui fallisce PRIMA dell'import, con un codice che dice perche'.
    "740ee979300fe20a9382992528604dee70cb2fcf",
    # Baseline canonica PROVIDER_BOUNDARY_CORE_RUNTIME_PAIR_MERGED: e' il PADRE del
    # candidate di LEGACY SPEND PATH CLOSURE. Ha `mark_refused_pre_submit` ma NON ha il
    # confine dello spender: un adapter spendibile vi sarebbe dispacciabile. Non e' un
    # Core sconosciuto, e' un Core VECCHIO, e va rifiutato con un esito che lo dica.
    "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515",
    # Primo candidate di questa fase, sottoposto a Human Review. Ha il confine dello
    # spender, ma l'autorizzazione che lo apre era costruibile dal chiamante
    # (DISPATCH_AUTHORIZATION_FORGEABLE). E' un Core superato, non sconosciuto.
    "44f9ea29cea112dfb30c752e5519498e25044c19",
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

    @property
    def canonical(self) -> bool:
        """Vero SOLO per il Core canonical pulito (unico esito che supera il pin)."""
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
    Un tree sporco sullo SHA giusto e' SEMPRE CORE_WORKTREE_DIRTY: nessun digest
    dichiarato dal chiamante puo' trasformarlo in un esito positivo.
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
    return require_core_verdict(core_path, required).observed


def require_core_verdict(core_path: str, required: str = REQUIRED_CORE_SHA) -> CorePinVerdict:
    if not os.path.isdir(core_path):
        raise CorePinError("CORE_PIN_MISMATCH", None, required)
    dirty = resolve_core_dirty(core_path)
    v = verify_core_pin(resolve_core_sha(core_path), required, dirty)
    if not v.ok:
        raise CorePinError(v.code, v.observed, v.required, v.dirty)
    return v
