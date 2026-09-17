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
           budget_units: int | None = None, envelope_units: int | None = None, max_polls: int = 5,
           core_path: str | None = None, required_core_sha: str | None = None,
           provider_mode: str = "fake", barrier=None, inputs_over: dict | None = None,
           intent: str = "resume", reason: str | None = None, permit_id: str | None = None,
           auto_permit: bool = False, operation_id: str | None = "__auto__",
           envelope_id: str | None = None, crash_after_send: bool = False,
           quote_id: str | None = None, governed: bool = False,
           budget_units_none: bool = False, clock_offset: float = 0.0) -> dict:
    """Esegue il candidate `go` e riferisce un dict serializzabile (mai eccezioni).

    operation_id="__auto__" (default di laboratorio) deriva l'operazione dal solo
    prompt ("lab:<prompt>"): stabile quando cambiano run/modello/params. Passare
    esplicitamente None prova il fail-closed (CR-01). governed=True attiva
    l'autorizzazione fidata LAB (envelope derivato + quote, CR-02)."""
    from runtime import go_candidate
    from runtime.authorization import DEFAULT_LAB_AUTHORIZATION, AuthorizationRefused
    from runtime.core_pin import CorePinError
    from runtime.provider_gate import RealProviderDisabled
    if operation_id == "__auto__":
        operation_id = f"lab:{prompt}"
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
            if crash_after_send:
                # TEST-RESTART: il processo muore DOPO il marcatore di invio e PRIMA del journal.
                _send = adapter.transport.send
                def _send_then_die(payload):
                    _send(payload)
                    os._exit(4)
                adapter.transport.send = _send_then_die
        kw = dict(adapter=adapter, provider_mode=provider_mode, store_path=db,
                  budget_units=None if budget_units_none else budget_units,
                  envelope_units=envelope_units,
                  max_polls=max_polls, intent=intent, reason=reason, permit_id=permit_id,
                  auto_permit=auto_permit, operation_id=operation_id, envelope_id=envelope_id,
                  quote_id=quote_id,
                  authorization=DEFAULT_LAB_AUTHORIZATION if governed else None)
        if clock_offset:
            import time as _t
            kw["clock"] = lambda: _t.time() + clock_offset
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
                   core_sha=res.core_sha, persisted=res.persisted, intent=res.intent,
                   resumed_terminal=res.resumed_terminal, permit_id=res.permit_id,
                   operation_id=res.operation_id, core_pin=res.core_pin,
                   governance=res.governance, envelope_id=res.envelope_id,
                   quote_id=res.quote_id, budget_units=res.budget_units,
                   resumed=res.resumed, requested_spec_key=res.requested_spec_key,
                   legacy_resume_as_start=res.legacy_resume_as_start)
    except AuthorizationRefused as e:
        out.update(ok=False, error="AuthorizationRefused", code=e.code, message=str(e))
    except RealProviderDisabled as e:
        out.update(ok=False, error=e.code, message=str(e))
    except CorePinError as e:
        out.update(ok=False, error=e.code, observed=e.observed, required=e.required)
    except go_candidate.IntentRefused as e:
        out.update(ok=False, error="IntentRefused", code=e.code, message=str(e))
    except Exception as e:                                  # noqa: BLE001
        out.update(ok=False, error=type(e).__name__, message=str(e),
                   trace=traceback.format_exc(limit=3))
    if adapter is not None:
        out["submits"] = adapter.submits
        out["transport_sent"] = getattr(getattr(adapter, "transport", None), "sent_count", None)
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
    with sqlite3.connect(db) as c:
        extra = c.execute("SELECT job_id,provider_account,revision,attempt_token,operation_id,"
                          "permit_id,envelope_id,settled_units FROM reservations ORDER BY job_id").fetchall()
        n_anom = c.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
        n_ledger = c.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
        # DELTA 03: evidenza "zero permit / zero quote consumata" nei rifiuti
        n_permits = c.execute("SELECT COUNT(*) FROM permits").fetchone()[0]
        n_permits_consumed = c.execute("SELECT COUNT(*) FROM permits WHERE consumed_by IS NOT NULL").fetchone()[0]
        n_quotes_consumed = c.execute("SELECT COUNT(*) FROM quotes WHERE consumed_by IS NOT NULL").fetchone()[0]
    return {"pid": os.getpid(),
            "rows": [dict(zip(("job_id", "spec_key", "provider", "state",
                               "provider_job_id", "polls", "budget_units",
                               "cost_credits"), r)) for r in rows],
            "ownership": [dict(zip(("job_id", "provider_account", "revision", "attempt_token",
                                    "operation_id", "permit_id", "envelope_id", "settled_units"), r))
                          for r in extra],
            "anomalies": n_anom, "ledger_entries": n_ledger,
            "permits": n_permits, "permits_consumed": n_permits_consumed,
            "quotes_consumed": n_quotes_consumed,
            "reserved_units": store.reserved_units()}


def store_call(db: str, core_path: str, method: str, *args, **kwargs) -> dict:
    """Nuovo interprete: invoca un metodo dello store durevole (recovery, ledger, permessi, quote).
    Due helper di test: `spec_key_of(prompt, over)` e `reserve_or_get_live_by_prompt(prompt, permit_id)`.

    LEGACY #7 (OPEN-GAP CLOSURE 2026-09-17): questo helper dispaccia DIRETTAMENTE sullo store,
    fuori dal percorso governato, nello stesso UID del chiamante. E' ammesso solo mentre la
    modalita' Provider Boundary e' disingaggiata (suite storica R0-R1). Ingaggiata, rifiuta
    PRIMA di importare il Core e prima di aprire lo store: nessun effetto di alcun tipo."""
    from runtime.provider_gate import ProviderBoundaryModeEngaged, refuse_if_provider_boundary_mode
    try:
        refuse_if_provider_boundary_mode("tests.worker.store_call")
    except ProviderBoundaryModeEngaged as e:
        return {"pid": os.getpid(), "ok": False, "error": type(e).__name__, "code": e.code,
                "message": str(e), "core_imported": "registry.reservations" in sys.modules,
                "store_created": False}
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    from adapters.base import GenSpec
    from registry.reservations import SqliteReservationStore
    from runtime.genspec_bridge import build_genspec
    store = SqliteReservationStore(db)
    try:
        if method == "spec_key_of":
            return {"pid": os.getpid(), "ok": True,
                    "result": build_genspec(make_inputs(args[0], **(args[1] or {})), GenSpec).spec_key}
        if method == "issue_lab_quote":
            # lato AUTORITA' di test: prezzo SOLO dal listino fidato LAB (CR-08), unita' LAB
            from runtime.authorization import (DEFAULT_LAB_AUTHORIZATION, LAB_QUOTE_UNIT, lab_price_for)
            prompt, op, over = args[0], args[1], (args[2] if len(args) > 2 else None) or {}
            env = kwargs.get("envelope_id") or DEFAULT_LAB_AUTHORIZATION.envelope_for(op)
            store.open_envelope(env, 100, unit=LAB_QUOTE_UNIT, scope=None)
            gs = build_genspec(make_inputs(prompt, **over), GenSpec)
            qid = store.issue_quote(operation_id=op, spec_key=gs.spec_key, envelope_id=env,
                                    amount=lab_price_for(gs.model), unit=kwargs.get("unit", LAB_QUOTE_UNIT),
                                    expires_at=kwargs.get("expires_at"))
            return {"pid": os.getpid(), "ok": True, "result": qid, "amount": lab_price_for(gs.model)}
        if method == "reserve_or_get_live_by_prompt_op":
            o, j = store.reserve_or_get_live(build_genspec(make_inputs(args[0]), GenSpec), now=1.0,
                                             operation_id=args[1])
            return {"pid": os.getpid(), "ok": True, "result": o.value, "job_id": j.job_id}
        if method == "reserve_or_get_live_by_prompt":
            # prova diretta sul Core: permesso presentato SENZA operation_id
            o, j = store.reserve_or_get_live(build_genspec(make_inputs(args[0]), GenSpec), now=1.0,
                                             permit_id=args[1])
            return {"pid": os.getpid(), "ok": True, "result": o.value}
        r = getattr(store, method)(*args, **kwargs)
        if isinstance(r, list):
            r = [x.to_dict() if hasattr(x, "to_dict") else x for x in r]
        elif hasattr(r, "to_dict"):
            r = r.to_dict()
        return {"pid": os.getpid(), "ok": True, "result": r}
    except Exception as e:                                  # noqa: BLE001
        return {"pid": os.getpid(), "ok": False, "error": type(e).__name__, "message": str(e)}


def pin_probe_clean(core_path: str, required_core_sha: str | None, db: str) -> dict:
    """Come pin_probe, ma senza costruire l'adapter: prova pura del gate di pin."""
    from runtime import go_candidate
    from runtime.core_pin import CorePinError
    assert "adapters.base" not in sys.modules
    out: dict = {"pid": os.getpid()}
    kw = dict(adapter=None, provider_mode="fake", store_path=db, max_polls=1,
              core_path=core_path, operation_id="lab:pin probe")
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


HANDOFF = os.path.join(GATE_ROOT, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16")


def real_spec_keys(core_path: str) -> dict:
    """Nuovo interprete: ricalcola gli spec_key dei job reali di MOTION_B1_B4C dal lock."""
    import json
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    from adapters.base import GenSpec
    from runtime.genspec_bridge import build_genspec
    from runtime.hf_batch_bridge import go_inputs_from_job, media_sha_from_lock
    lock = json.load(open(os.path.join(HANDOFF, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json"), encoding="utf-8"))
    spec = json.load(open(os.path.join(HANDOFF, "SPECS", "spec_motion_B1_B4C.json"), encoding="utf-8"))
    res = media_sha_from_lock(lock)
    return {"pid": os.getpid(),
            "keys": {j["asset"]: build_genspec(go_inputs_from_job(spec, j, res(j["asset"])), GenSpec).spec_key
                     for j in spec["jobs"]}}


def hf_batch_runtime_go(db: str, canary_home: str, core_path: str, *, adapter_kw: dict | None = None,
                        max_polls: int = 5, rounds: int = 1, verb: str = "go",
                        intent: str = "resume", attempt_reason: str | None = None,
                        auto_permit: bool = False, spec_name: str = "spec_motion_B1_B4C.json",
                        operation_namespace: str | None = None, governed: bool = False) -> dict:
    """Sentinella attiva, poi il verbo `go` della COPIA hf_batch_runtime su una spec reale.

    `require`/`fingerprint` sono stubbati: il lock preventivo di P2 (fingerprint di
    tenant/Core/regole/media sul Mac) e' il controllo di deriva degli input, non
    fa parte del contratto C26 e i suoi file non esistono in questo ambiente.
    """
    import json
    from tests import audit_sentinel
    audit_sentinel.install(canary_home)
    out: dict = {"pid": os.getpid(), "verb": verb}
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from runtime import hf_batch_runtime as hb
        from runtime.authorization import DEFAULT_LAB_AUTHORIZATION
        from runtime.hf_batch_bridge import media_sha_from_lock
        from runtime.provider_gate import RealProviderDisabled
        lock = json.load(open(os.path.join(HANDOFF, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json"), encoding="utf-8"))
        res = media_sha_from_lock(lock)
        adapter = _make_adapter("fake", **(adapter_kw or {}))
        # DELTA 03: `governed=True` = percorso GOVERNATO di Batch (autorizzazione LAB, nessuna
        # quote_for: la prova e' che il default `resume` NON avvia il primo attempt e che
        # `new_attempt` arriva all'autorizzazione economica senza effetti).
        b = hb.Batch(os.path.join(HANDOFF, "SPECS", spec_name), adapter=adapter,
                     store_path=db, max_polls=max_polls,
                     media_sha256=None, intent=intent, attempt_reason=attempt_reason,
                     auto_permit=auto_permit, operation_namespace=operation_namespace,
                     authorization=DEFAULT_LAB_AUTHORIZATION if governed else None)
        # resolver per asset: il lock registra sha256_sent per (asset, role, id).
        # THREAD-LOCAL: Batch.go esegue i job in thread paralleli; un dict condiviso
        # faceva risolvere l'asset sbagliato (spec_key diversa) sotto race.
        import threading
        current = threading.local()
        b.media_sha256 = lambda flag, rid, ref: res(current.asset)(flag, rid, ref)
        orig_run_job = b.run_job
        def run_job(j, lk):
            current.asset = j["asset"]
            return orig_run_job(j, lk)
        b.run_job = run_job
        b.lock_path = os.path.join(HANDOFF, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json")  # lock reale
        b.require = lambda: lock                                    # stub: vedi docstring
        b.fingerprint = lambda: (lock["fingerprint_sha256"], {})
        b.trace_path = os.path.join(os.path.dirname(db), f"{b.name}_LAB_TRACE.json")
        if verb == "go":
            traces = []
            for _ in range(rounds):
                traces.append(b.go())
            out.update(ok=True, traces=[{"run_verdict": t["run_verdict"], "jobs": [
                {k: x.get(k) for k in ("asset", "run_status", "reservation_outcome", "job_id",
                                       "provider_job_id", "provider", "spec_key", "core_sha",
                                       "core_pin", "intent", "resumed_terminal", "permit_id",
                                       "operation_id", "operation_namespace", "resumed",
                                       "requested_spec_key", "governance", "legacy_resume_as_start")}
                for x in t["jobs"]]} for t in traces], submits=adapter.submits)
        else:
            try:
                getattr(b, verb)()
                out.update(ok=False, error="VERB_RAN")
            except RealProviderDisabled as e:
                out.update(ok=True, error=e.code, message=str(e))
    except Exception as e:                                  # noqa: BLE001
        code = getattr(e, "code", None)                     # IntentRefused / AuthorizationRefused
        out.update(ok=False, error=type(e).__name__, code=code, message=str(e), trace=traceback.format_exc(limit=4))
    if adapter is not None:
        out["submits"] = adapter.submits                    # evidenza anche nei rifiuti
    out["violations"] = audit_sentinel.violations()
    return out


def _entry(q, fn, args, kwargs):
    try:
        q.put(fn(*args, **kwargs))
    except Exception as e:                                  # noqa: BLE001
        q.put({"ok": False, "error": type(e).__name__, "message": str(e),
               "trace": traceback.format_exc(limit=5)})
