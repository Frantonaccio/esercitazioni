"""Candidate del verbo `go` di hf_batch, ricablato sul Core C26.

    go(...)
      1. FAKE MODE gate           -> REAL_PROVIDER_DISABLED se non 'fake'
      2. CORE PIN gate            -> CORE_PIN_MISMATCH / STALE_CORE_PIN
      3. import del Core          -> solo dopo 1 e 2
      4. GenSpec dal bridge       -> solo dati deterministici
      5. SqliteReservationStore   -> file in RUNTIME_INTEGRATION_GATE_01/state/
      6. Core run_job(...)        -> reserve_or_get_live -> submit -> poll -> put
      7. GoResult                 -> stato persistito, letto dallo store

COSA QUESTO MODULO NON FA (ed e' verificato dal test AST T19):
  - non chiama find_live_by_spec;
  - non chiama adapter.submit;
  - non definisce stati di job, esiti di prenotazione, budget;
  - non apre sqlite3, non scrive SQL, non tiene una reservation JSON parallela.

`ReservationObserver` e' un proxy trasparente sullo store del Core: registra
l'esito che il CORE ha deciso in `reserve_or_get_live`, cosi' il runtime puo'
riferirlo senza rifare la lettura "c'e' un job vivo?" per conto suo. Delega
tutto, non decide nulla.

NOTA SU hf_batch.py: il file reale (P2) non e' disponibile in questo ambiente.
Questo modulo e' il candidate del solo percorso `go -> Core`, scritto per
essere innestato nella copia `runtime/hf_batch_runtime.py` quando P2 sara'
leggibile. Non pretende di essere una copia di hf_batch.py.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from runtime.core_pin import REQUIRED_CORE_SHA, require_core
from runtime.genspec_bridge import GoInputs, build_genspec
from runtime.provider_gate import require_fake_adapter, require_fake_mode

GATE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(GATE_ROOT, "state")
DEFAULT_CORE_PATH = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")


@dataclass
class GoResult:
    """Cio' che `go` riferisce. Ogni valore viene dal Core o dallo store, mai inventato."""
    reservation_outcome: str        # RESERVED_NEW | EXISTING_LIVE_JOB (deciso dal Core)
    job_id: str
    provider_job_id: str | None
    provider: str
    state: str                      # JobState.value persistito
    spec_key: str
    core_sha: str
    store_path: str
    persisted: dict[str, Any] = field(default_factory=dict)

    @property
    def outcome(self) -> str:
        """Etichetta di sintesi per il chiamante di hf_batch."""
        if self.reservation_outcome == "EXISTING_LIVE_JOB":
            if self.state == "SUBMIT_UNKNOWN":
                return "EXISTING_LIVE_JOB/reconciliation-required"
            return "EXISTING_LIVE_JOB"
        return self.state


class ReservationObserver:
    """Proxy sullo store del Core. Registra l'esito deciso dal Core, delega tutto."""

    def __init__(self, inner):
        self._inner = inner
        self.last_outcome = None

    def reserve_or_get_live(self, spec, **kw):
        outcome, job = self._inner.reserve_or_get_live(spec, **kw)
        self.last_outcome = outcome
        return outcome, job

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _ensure_core_on_path(core_path: str) -> None:
    if core_path not in sys.path:
        sys.path.insert(0, core_path)


def go(inputs: GoInputs, *, adapter, provider_mode: str, store_path: str,
       core_path: str = DEFAULT_CORE_PATH, required_core_sha: str = REQUIRED_CORE_SHA,
       budget_units: int = 0, envelope_units: int | None = None,
       max_polls: int = 20, clock=time.time) -> GoResult:
    """Candidate `go`. Fail-closed su provider e pin; poi consuma il Core."""
    # 1) FAKE MODE: prima di tutto, prima di qualunque import del Core.
    require_fake_mode(provider_mode)
    # 2) CORE PIN: il Core non autorizzato non viene nemmeno importato.
    core_sha = require_core(core_path, required_core_sha)
    # 3) Import del Core canonical.
    _ensure_core_on_path(core_path)
    from adapters.base import GenSpec                       # noqa: WPS433
    from adapters.fake import FakeAdapter                   # noqa: WPS433
    from registry.reservations import SqliteReservationStore  # noqa: WPS433
    from transport.pipeline import run_job                  # noqa: WPS433
    # 3b) L'adapter deve essere il FakeAdapter del Core o una sottoclasse.
    require_fake_adapter(adapter, FakeAdapter)
    # 4) Spec deterministica.
    spec = build_genspec(inputs, GenSpec)
    # 5) Store durevole di riferimento, confinato in state/.
    store_path = os.path.abspath(store_path)
    if not store_path.startswith(STATE_DIR + os.sep):
        raise ValueError(f"store fuori da state/: {store_path}")
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    store = ReservationObserver(SqliteReservationStore(store_path))
    # 6) Il Core fa tutto: prenotazione atomica, submit, poll, persistenza.
    job = run_job(adapter, spec, store, clock=clock, max_polls=max_polls,
                  budget_units=budget_units, envelope_units=envelope_units)
    # 7) Lo stato riferito e' quello PERSISTITO, riletto dallo store.
    persisted = store.get(job.job_id)
    return GoResult(
        reservation_outcome=store.last_outcome.value,
        job_id=job.job_id, provider_job_id=persisted.provider_job_id,
        provider=persisted.provider, state=persisted.state.value,
        spec_key=spec.spec_key, core_sha=core_sha, store_path=store_path,
        persisted=persisted.to_dict())
