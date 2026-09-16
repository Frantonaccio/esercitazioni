"""Funzioni eseguite in PROCESSI REALI (multiprocessing 'spawn' = nuovo interprete).

Ogni funzione e' a livello di modulo perche' `spawn` la reimporta nel figlio:
nessuna memoria Python condivisa con il padre. E' il punto: la durabilita' la
deve dimostrare il file SQLite, non l'oggetto in memoria.
"""
from __future__ import annotations

import os
import sys
import traceback

GATE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if GATE_ROOT not in sys.path:
    sys.path.insert(0, GATE_ROOT)

from runtime.genspec_bridge import GoInputs  # noqa: E402


def make_inputs(prompt: str, **over) -> GoInputs:
    d = dict(kind="image", model="fake_model_v1", prompt=prompt,
             params={"aspect_ratio": "9:16", "duration_s": 5},
             refs=("ref_element_001",), project_id="GATE01_LAB")
    d.update(over)
    return GoInputs(**d)


def _make_adapter(kind: str, **kw):
    """Costruisce SOLO FakeAdapter del Core o sue sottoclassi di laboratorio."""
    from adapters.fake import FakeAdapter
    if kind == "fake":
        return FakeAdapter(**kw)
    if kind == "fake_a":
        class FakeA(FakeAdapter):
            name = "fake_a"
        return FakeA(**kw)
    if kind == "fake_b":
        class FakeB(FakeAdapter):
            name = "fake_b"
        return FakeB(**kw)
    if kind == "submit_unknown":
        class UnknownSubmitFake(FakeAdapter):
            """Il submit parte e la risposta si perde: eccezione dopo l'invio."""
            def submit(self, spec):
                self.submits += 1
                raise ConnectionResetError("risposta del provider persa dopo l'invio")
        return UnknownSubmitFake(**kw)
    raise ValueError(kind)


def run_go(db: str, prompt: str, *, adapter_kind: str = "fake", adapter_kw: dict | None = None,
           budget_units: int = 0, envelope_units: int | None = None, max_polls: int = 5,
           core_path: str | None = None, required_core_sha: str | None = None,
           provider_mode: str = "fake", barrier=None, inputs_over: dict | None = None) -> dict:
    """Esegue il candidate `go` e riferisce un dict serializzabile (mai eccezioni)."""
    from runtime import go_candidate
    from runtime.core_pin import CorePinError
    from runtime.provider_gate import RealProviderDisabled
    out: dict = {"pid": os.getpid(), "submits": None}
    adapter = None
    try:
        if provider_mode == "fake":
            # l'import del Core qui e' legittimo: il pin e' verificato da go() prima
            # di importare, e i test di pin usano processi separati (vedi pin_probe).
            core = core_path or go_candidate.DEFAULT_CORE_PATH
            if core not in sys.path:
                sys.path.insert(0, core)
            adapter = _make_adapter(adapter_kind, **(adapter_kw or {}))
        kw = dict(adapter=adapter, provider_mode=provider_mode, store_path=db,
                  budget_units=budget_units, envelope_units=envelope_units,
                  max_polls=max_polls)
        if core_path:
            kw["core_path"] = core_path
        if required_core_sha:
            kw["required_core_sha"] = required_core_sha
        if barrier is not None:
            barrier.wait(timeout=30)
        res = go_candidate.go(make_inputs(prompt, **(inputs_over or {})), **kw)
        out.update(ok=True, outcome=res.outcome, reservation_outcome=res.reservation_outcome,
                   job_id=res.job_id, provider_job_id=res.provider_job_id,
                   provider=res.provider, state=res.state, spec_key=res.spec_key,
                   core_sha=res.core_sha, persisted=res.persisted)
    except RealProviderDisabled as e:
        out.update(ok=False, error=e.code, message=str(e))
    except CorePinError as e:
        out.update(ok=False, error=e.code, observed=e.observed, required=e.required)
    except Exception as e:                                  # noqa: BLE001
        out.update(ok=False, error=type(e).__name__, message=str(e),
                   trace=traceback.format_exc(limit=3))
    if adapter is not None:
        out["submits"] = adapter.submits
    out["core_imported"] = "adapters.base" in sys.modules
    return out


def read_state(db: str, core_path: str) -> dict:
    """Nuova istanza di store in un nuovo interprete: legge SOLO dal file."""
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    import sqlite3
    from registry.reservations import SqliteReservationStore
    store = SqliteReservationStore(db)
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT job_id,spec_key,provider,state,provider_job_id,"
                         "polls,budget_units,cost_credits FROM reservations "
                         "ORDER BY job_id").fetchall()
    return {"pid": os.getpid(),
            "rows": [dict(zip(("job_id", "spec_key", "provider", "state",
                               "provider_job_id", "polls", "budget_units",
                               "cost_credits"), r)) for r in rows],
            "reserved_units": store.reserved_units()}


def pin_probe_clean(core_path: str, required_core_sha: str | None, db: str) -> dict:
    """Come pin_probe, ma senza costruire l'adapter: prova pura del gate di pin."""
    from runtime import go_candidate
    from runtime.core_pin import CorePinError
    assert "adapters.base" not in sys.modules
    out: dict = {"pid": os.getpid()}
    kw = dict(adapter=None, provider_mode="fake", store_path=db, max_polls=1,
              core_path=core_path)
    if required_core_sha:
        kw["required_core_sha"] = required_core_sha
    try:
        res = go_candidate.go(make_inputs("pin probe"), **kw)
        out.update(ok=True, core_sha=res.core_sha)
    except CorePinError as e:
        out.update(ok=False, error=e.code, observed=e.observed, required=e.required)
    except Exception as e:                                  # noqa: BLE001
        out.update(ok=False, error=type(e).__name__, message=str(e))
    out["core_imported"] = "adapters.base" in sys.modules
    return out


def sentinel_run(mode: str, db: str, canary_home: str, core_path: str) -> dict:
    """Sentinella attiva PRIMA di qualunque import del runtime o del Core."""
    from tests import audit_sentinel
    audit_sentinel.install(canary_home)
    out: dict = {"pid": os.getpid(), "mode": mode}
    if mode == "fake":
        r = run_go(db, "sentinel fake", core_path=core_path, max_polls=5)
        out.update(go=r)
    elif mode == "real":
        # provider_mode non 'fake': deve fermarsi PRIMA di importare il Core.
        assert "adapters.base" not in sys.modules
        r = run_go(db, "sentinel real", provider_mode="higgsfield", core_path=core_path)
        out.update(go=r)
    elif mode == "counterproof":
        # Lettura DELIBERATA dell'esca: la sentinella deve accorgersene.
        p = os.path.join(canary_home, ".higgsfield", "credentials.json")
        with open(p, encoding="utf-8") as fh:
            fh.read()
        os.environ.get("HIGGSFIELD_API_KEY")
        import subprocess
        try:
            subprocess.run(["higgsfield", "--version"], capture_output=True, timeout=5)
        except Exception:                                   # noqa: BLE001
            pass
    out["violations"] = audit_sentinel.violations()
    out["core_imported"] = "adapters.base" in sys.modules
    return out


def _entry(q, fn, args, kwargs):
    try:
        q.put(fn(*args, **kwargs))
    except Exception as e:                                  # noqa: BLE001
        q.put({"ok": False, "error": type(e).__name__, "message": str(e),
               "trace": traceback.format_exc(limit=5)})
