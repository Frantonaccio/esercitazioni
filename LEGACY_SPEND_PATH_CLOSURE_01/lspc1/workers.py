"""SONDE DEI PERCORSI DI SPESA — una per entry point, ognuna in un PROCESSO REALE.

`multiprocessing` in modalita' 'spawn': nuovo interprete, nessuna memoria Python
condivisa col padre. Cio' che una sonda riferisce lo ha osservato davvero, non lo
ha ereditato.

Ogni sonda riferisce SEMPRE, anche quando rifiuta:
  - l'esito (`ok`, `error`, `code`);
  - i contatori della sentinella (`sentinel`): e' li' che si legge se un confine
    e' stato attraversato;
  - lo stato dello store (`store`): righe, ledger, quote consumate, permessi;
  - se il Core e' stato importato e se lo store e' stato creato: un rifiuto che
    arriva DOPO l'import non e' lo stesso rifiuto.

Nessuna sonda usa un provider reale, una credenziale, la rete o un credito.
"""
from __future__ import annotations

import os
import sys
import traceback

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BUNDLE_ROOT)

# RUNTIME sotto sonda. Di default e' quello di QUESTO albero (il candidate). La
# RIPRODUZIONE PRE-FIX punta invece a un worktree del Runtime canonico
# `fea7b439`: riprodurre il difetto sul Runtime gia' corretto non riprodurrebbe
# nulla. Le sonde restano le stesse: cambia solo il codice sotto prova.
GATE01 = os.environ.get("LSPC1_GATE01") or os.path.join(REPO_ROOT, "RUNTIME_INTEGRATION_GATE_01")
for _p in (BUNDLE_ROOT, GATE01):
    if _p not in sys.path:
        sys.path.insert(0, _p)

BASELINE_CORE_SHA = "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515"
STATE_DIR = os.path.join(GATE01, "state")


def state_db(name: str) -> str:
    """Store confinato in `state/` del Runtime sotto sonda: `go()` rifiuta uno
    store fuori di li', ed e' giusto che lo faccia. I file sono prefissati
    `lspc1_` e rimossi a fine gate."""
    os.makedirs(STATE_DIR, exist_ok=True)
    p = os.path.join(STATE_DIR, f"lspc1_{name}.db")
    for suffix in ("", "-journal", "-wal", "-shm"):
        if os.path.exists(p + suffix):
            os.remove(p + suffix)
    for suffix in (".snapshots", ".reconciliation"):
        d = p + suffix
        if os.path.isdir(d):
            import shutil
            shutil.rmtree(d, ignore_errors=True)
    return p


# --------------------------------------------------------------- utilita'
def _store_counts(db: str) -> dict:
    """Stato dello store LETTO DAL FILE. Se il file non esiste, lo dice: uno
    store mai creato e' un fatto piu' forte di uno store vuoto."""
    import sqlite3
    if not os.path.exists(db):
        return {"created": False}
    out = {"created": True}
    try:
        with sqlite3.connect(db) as c:
            for label, sql in (
                    ("reservations", "SELECT COUNT(*) FROM reservations"),
                    ("live", "SELECT COUNT(*) FROM reservations WHERE state NOT IN "
                             "('SUCCEEDED','FAILED','TIMEOUT')"),
                    ("ledger", "SELECT COUNT(*) FROM ledger"),
                    ("permits_consumed", "SELECT COUNT(*) FROM permits WHERE consumed_by IS NOT NULL"),
                    ("quotes_consumed", "SELECT COUNT(*) FROM quotes WHERE consumed_by IS NOT NULL"),
                    ("anomalies", "SELECT COUNT(*) FROM anomalies")):
                try:
                    out[label] = c.execute(sql).fetchone()[0]
                except sqlite3.Error:
                    out[label] = None
    except sqlite3.Error as e:                              # noqa: BLE001
        out["error"] = str(e)
    return out


def _snapshots_dir(db: str) -> dict:
    """Ledger write-once degli snapshot P-B04 accanto allo store: un rifiuto che
    avviene prima non deve lasciare nemmeno un sigillo."""
    d = db + ".snapshots"
    if not os.path.isdir(d):
        return {"created": False, "files": 0}
    return {"created": True, "files": len(os.listdir(d))}


def _err(out: dict, e: BaseException) -> dict:
    out.update(ok=False, error=type(e).__name__, code=getattr(e, "code", None),
               message=str(e)[:400])
    return out


def _prelude(core_path: str) -> dict:
    return {"pid": os.getpid(), "core_path": core_path,
            "core_imported_at_entry": "adapters.base" in sys.modules}


def _epilogue(out: dict, db: str | None, adapter=None) -> dict:
    from lspc1 import spenders
    out["sentinel"] = spenders.observe(adapter)
    out["sentinel_zero"] = spenders.zero(out["sentinel"])
    out["core_imported"] = "adapters.base" in sys.modules
    if db is not None:
        out["store"] = _store_counts(db)
        out["snapshots"] = _snapshots_dir(db)
    return out


def _pin_kwargs(core_path: str) -> dict:
    """Il pin del runtime punta al Core CANDIDATE. Una sonda che gira sul Core
    BASELINE deve dichiararlo esplicitamente, altrimenti si ferma al pin e non
    prova nulla del percorso che vuole provare."""
    import subprocess
    sha = subprocess.run(["git", "-C", core_path, "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    return {"required_core_sha": sha} if sha else {}


def _inputs(prompt: str, **over):
    from tests.worker import make_inputs
    return make_inputs(prompt, **over)


def _authority_quote(core_path: str, db: str, *, prompt: str, operation_id: str,
                     envelope: str, amount: int, authorized: int = 1000,
                     unit: str = "synthetic_units", inputs_over: dict | None = None) -> dict:
    """LATO AUTORITA'. Apre l'envelope ed emette la quote FIDATA. Il chiamante non
    sceglie l'importo: lo riceve. E' il ruolo che in produzione appartiene allo
    spender, e qui e' tenuto separato dal ruolo del client."""
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    from adapters.base import GenSpec
    from registry.reservations import SqliteReservationStore
    from runtime.genspec_bridge import build_genspec
    store = SqliteReservationStore(db)
    store.open_envelope(envelope, authorized, unit=unit, scope=None)
    spec = build_genspec(_inputs(prompt, **(inputs_over or {})), GenSpec)
    qid = store.issue_quote(operation_id=operation_id, spec_key=spec.spec_key,
                            envelope_id=envelope, amount=amount, unit=unit)
    return {"quote_id": qid, "envelope_id": envelope, "amount": amount,
            "spec_key": spec.spec_key}


# ===========================================================================
# P1 — percorso LEGACY_LAB con uno SPENDER
# ===========================================================================
def p1_legacy_with_spender(core_path: str, db: str, *, prompt: str = "p1 legacy spender",
                           break_pin: bool = False) -> dict:
    """`go(..., authorization=None)` con un adapter SPENDIBILE.

    Sul Core baseline il percorso spende. Sul candidate deve fallire PRIMA dello
    store e PRIMA del gate di pin.

    `break_pin=True` e' la prova dell'ORDINE: si passa uno SHA richiesto
    deliberatamente sbagliato. Se il rifiuto resta LEGACY_LAB_NOT_PROVIDER_CAPABLE
    invece di diventare CORE_PIN_MISMATCH, il confine precede il pin — e quindi
    precede l'import del Core e tutto cio' che viene dopo."""
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from lspc1.spenders import build_sentinel
        from runtime import go_candidate
        adapter = build_sentinel()
        out["core_imported_before_go"] = "adapters.base" in sys.modules
        pin = {"required_core_sha": "dead" * 10} if break_pin else _pin_kwargs(core_path)
        out["break_pin"] = break_pin
        res = go_candidate.go(_inputs(prompt), adapter=adapter, provider_mode="fake",
                              store_path=db, core_path=core_path, max_polls=5,
                              operation_id=f"LSPC1:{prompt}", authorization=None, **pin)
        out.update(ok=True, state=res.state, governance=res.governance,
                   reservation_outcome=res.reservation_outcome, job_id=res.job_id,
                   quote_id=res.quote_id, envelope_id=res.envelope_id)
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
        out["trace"] = traceback.format_exc(limit=3)
    return _epilogue(out, db, adapter)


# ===========================================================================
# P2 — percorso LEGACY_LAB con un adapter di LABORATORIO (non-regressione)
# ===========================================================================
def p2_legacy_with_lab_adapter(core_path: str, db: str, *, prompt: str = "p2 legacy lab") -> dict:
    """Il percorso LAB deve continuare a funzionare: e' cio' che la suite storica
    usa, ed e' esplicitamente conservato dal mandato."""
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from adapters.fake import FakeAdapter
        from runtime import go_candidate
        adapter = FakeAdapter()
        res = go_candidate.go(_inputs(prompt), adapter=adapter, provider_mode="fake",
                              store_path=db, core_path=core_path, max_polls=5,
                              operation_id=f"LSPC1:{prompt}", authorization=None,
                              **_pin_kwargs(core_path))
        out.update(ok=True, state=res.state, governance=res.governance,
                   submits=adapter.submits, legacy_resume_as_start=res.legacy_resume_as_start)
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
    out = _epilogue(out, db, None)
    out["lab_adapter"] = {"submits": getattr(adapter, "submits", None),
                          "transport_sent": getattr(getattr(adapter, "transport", None),
                                                    "sent_count", None)}
    return out


# ===========================================================================
# P3 — percorso GOVERNATO con uno SPENDER: deve passare
# ===========================================================================
def p3_governed_with_spender(core_path: str, db: str, *, prompt: str = "p3 governed spender",
                             amount: int = 10) -> dict:
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from lspc1.spenders import build_sentinel
        from runtime import go_candidate
        from runtime.authorization import LabAuthorization
        op = "LSPC1G:p3"
        env = "ENV_LSPC1G"
        q = _authority_quote(core_path, db, prompt=prompt, operation_id=op,
                             envelope=env, amount=amount)
        adapter = build_sentinel()
        auth = LabAuthorization({"LSPC1G": env})
        res = go_candidate.go(_inputs(prompt), adapter=adapter, provider_mode="fake",
                              store_path=db, core_path=core_path, max_polls=5,
                              operation_id=op, intent="new_attempt",
                              reason="LSPC1 controprova: il governato deve raggiungere lo spender",
                              auto_permit=True, quote_id=q["quote_id"], authorization=auth,
                              **_pin_kwargs(core_path))
        out.update(ok=True, state=res.state, governance=res.governance, job_id=res.job_id,
                   quote_id=res.quote_id, envelope_id=res.envelope_id,
                   budget_units=res.budget_units, permit_id=res.permit_id,
                   payload_snapshot=res.payload_snapshot)
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
        out["trace"] = traceback.format_exc(limit=4)
    return _epilogue(out, db, adapter)


# ===========================================================================
# P4 — primitive del CORE: run_job diretto coi soli default (#10)
# ===========================================================================
def p4_core_run_job_direct(core_path: str, db: str, *, prompt: str = "p4 core direct",
                           envelope_units: int | None = None) -> dict:
    """Il percorso legacy del CORE: nessun runtime, nessun pin, nessun intent.
    Solo `transport.pipeline.run_job(adapter, spec, store)`."""
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from adapters.base import GenSpec
        from lspc1.spenders import build_sentinel
        from registry.reservations import SqliteReservationStore
        from runtime.genspec_bridge import build_genspec
        from transport.pipeline import run_job
        adapter = build_sentinel()
        store = SqliteReservationStore(db)
        spec = build_genspec(_inputs(prompt), GenSpec)
        kw = {"max_polls": 5}
        if envelope_units is not None:
            kw.update(budget_units=10, envelope_units=envelope_units)
        job = run_job(adapter, spec, store, **kw)
        persisted = store.get(job.job_id)
        out.update(ok=True, state=persisted.state.value, job_id=job.job_id,
                   operation_id=persisted.operation_id, quote_id=persisted.quote_id)
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
    return _epilogue(out, db, adapter)


# ===========================================================================
# P5 — primitive del CORE: adapter.submit diretto (#10, forma estrema)
# ===========================================================================
def p5_adapter_submit_direct(core_path: str, db: str, *, prompt: str = "p5 submit") -> dict:
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from adapters.base import GenSpec
        from lspc1.spenders import build_sentinel
        from runtime.genspec_bridge import build_genspec
        adapter = build_sentinel()
        spec = build_genspec(_inputs(prompt), GenSpec)
        job = adapter.submit(spec)
        out.update(ok=True, provider_job_id=job.provider_job_id, provider=job.provider)
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
    return _epilogue(out, None, adapter)


# ===========================================================================
# P6 — primitive del CORE: adapter.authorize_payload diretto
# ===========================================================================
def p6_authorize_payload_direct(core_path: str, db: str, *, prompt: str = "p6 authorize") -> dict:
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        import hashlib
        from adapters.base import GenSpec
        from lspc1.spenders import build_sentinel
        from runtime.genspec_bridge import build_genspec
        adapter = build_sentinel()
        spec = build_genspec(_inputs(prompt), GenSpec)
        digest = hashlib.sha256(adapter.serialize(spec)).hexdigest()
        adapter.authorize_payload(digest)
        out.update(ok=True, authorized_digest=digest[:16])
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
    return _epilogue(out, None, adapter)


# ===========================================================================
# P7 — primitive del CORE: reconcile con evidenza arbitraria (#11)
# ===========================================================================
def p7_reconcile_raw(core_path: str, db: str, *, prompt: str = "p7 reconcile",
                     allowlist: bool = False) -> dict:
    """Libera l'identita' di una spec con un'evidenza fabbricata, poi prova a
    spendere su quell'identita' liberata con lo SPENDER.

    Due fatti distinti da riferire senza confonderli:
      - `reconcile` liberera' l'identita' (e' cio' che fa, e non e' un dispatch);
      - la spesa che ne seguirebbe deve restare impossibile.
    """
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from adapters.base import GenSpec, JobState
        from lspc1.spenders import build_sentinel
        from registry.reservations import SqliteReservationStore
        from runtime.genspec_bridge import build_genspec
        from transport.pipeline import run_job
        kw = {}
        if allowlist:
            import inspect
            if "reconciliation_sources" in inspect.signature(SqliteReservationStore).parameters:
                kw["reconciliation_sources"] = ("PROVIDER_API",)
            else:
                out["allowlist_supported"] = False
        store = SqliteReservationStore(db, **kw)
        out.setdefault("allowlist_supported", bool(kw))
        spec = build_genspec(_inputs(prompt), GenSpec)
        outcome, job = store.reserve_or_get_live(spec, budget_units=7, now=1.0,
                                                 operation_id="LSPC1:p7")
        out["reserved"] = {"outcome": outcome.value, "job_id": job.job_id}
        forged = {"source": "FABBRICATA_DAL_CHIAMANTE", "remote_ref": "inventato:1",
                  "reason": "evidenza arbitraria"}
        try:
            after = store.reconcile(job, JobState.FAILED, forged, now=2.0)
            out["reconcile"] = {"accepted": True, "state": after.state.value}
        except BaseException as e:                          # noqa: BLE001
            out["reconcile"] = {"accepted": False, "error": type(e).__name__,
                                "message": str(e)[:240],
                                "state": store.get(job.job_id).state.value}
        # identita' liberata o no, lo spender non deve poter dispacciare
        adapter = build_sentinel()
        try:
            j2 = run_job(adapter, spec, store, max_polls=5)
            out["respend"] = {"ok": True, "state": store.get(j2.job_id).state.value}
        except BaseException as e:                          # noqa: BLE001
            out["respend"] = {"ok": False, "error": type(e).__name__,
                              "code": getattr(e, "code", None), "message": str(e)[:240]}
        out["ok"] = True
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
        out["trace"] = traceback.format_exc(limit=3)
    return _epilogue(out, db, adapter)


# ===========================================================================
# P8 — helper di test che dispaccia sullo store (#7)
# ===========================================================================
def p8_store_call(core_path: str, db: str, *, method: str = "reconcile") -> dict:
    """`tests.worker.store_call`: prima dispacciava QUALUNQUE metodo."""
    out = _prelude(core_path)
    try:
        from tests.worker import STORE_CALL_ALLOWED, store_call
        r = store_call(db, core_path, method)
        out.update(ok=r.get("ok"), error=r.get("error"), code=r.get("code"),
                   message=str(r.get("message"))[:240],
                   store_created=r.get("store_created"), surface_declared=True,
                   dispatch_reached=r.get("code") != "STORE_CALL_METHOD_NOT_ALLOWED",
                   allowed_surface=sorted(STORE_CALL_ALLOWED))
    except ImportError:
        # Runtime BASELINE: nessuna superficie dichiarata. Il metodo viene
        # dispacciato davvero; l'errore che torna e' quello del METODO REALE
        # (es. TypeError per argomenti mancanti), non un rifiuto: e' la prova
        # che il dispatch arbitrario e' avvenuto.
        from tests.worker import store_call
        r = store_call(db, core_path, method)
        out.update(ok=r.get("ok"), error=r.get("error"), code=r.get("code"),
                   message=str(r.get("message"))[:240], allowed_surface=None,
                   surface_declared=False,
                   dispatch_reached=r.get("error") not in (None, "ProviderBoundaryModeEngaged",
                                                           "StoreCallMethodNotAllowed"))
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
    return _epilogue(out, db, None)


# ===========================================================================
# P9 — "basta cambiare adapter/mode/config?" — no.
# ===========================================================================
def p9_config_switches(core_path: str, db_prefix: str) -> dict:
    """Il mandato chiede di dimostrare che il percorso legacy non diventa
    spendibile cambiando semplicemente adapter, modalita' o configurazione.
    Qui si PROVA a farlo, in cinque modi, e si registra ogni rifiuto."""
    out = _prelude(core_path)
    attempts = {}
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    from lspc1.spenders import build_sentinel, observe, sentinel_class
    from runtime import go_candidate
    pin = _pin_kwargs(core_path)

    def attempt(label, fn):
        a = {"reached": None}
        try:
            a["result"] = fn()
            a["refused"] = False
        except BaseException as e:                          # noqa: BLE001
            a.update(refused=True, error=type(e).__name__, code=getattr(e, "code", None),
                     message=str(e)[:220])
        attempts[label] = a

    # 1. modalita' Provider Boundary INGAGGIATA: il legacy con spender resta chiuso
    def engaged():
        os.environ["CREATIVE_OS_PROVIDER_BOUNDARY_MODE"] = "engaged"
        try:
            ad = build_sentinel()
            go_candidate.go(_inputs("p9 engaged"), adapter=ad, provider_mode="fake",
                            store_path=db_prefix + "_1.db", core_path=core_path,
                            operation_id="LSPC1:p9a", authorization=None, **pin)
        finally:
            os.environ.pop("CREATIVE_OS_PROVIDER_BOUNDARY_MODE", None)
    attempt("modalita_ingaggiata", engaged)

    # 2. modalita' DISINGAGGIATA (default storico): stesso rifiuto
    def disengaged():
        ad = build_sentinel()
        go_candidate.go(_inputs("p9 disengaged"), adapter=ad, provider_mode="fake",
                        store_path=db_prefix + "_2.db", core_path=core_path,
                        operation_id="LSPC1:p9b", authorization=None, **pin)
    attempt("modalita_disingaggiata", disengaged)

    # 3. interruttore legacy forzato "abilitato" dall'ambiente
    def env_enabled():
        os.environ["CREATIVE_OS_LEGACY_LAB_SPEND_PATH"] = "enabled"
        try:
            ad = build_sentinel()
            go_candidate.go(_inputs("p9 env"), adapter=ad, provider_mode="fake",
                            store_path=db_prefix + "_3.db", core_path=core_path,
                            operation_id="LSPC1:p9c", authorization=None, **pin)
        finally:
            os.environ.pop("CREATIVE_OS_LEGACY_LAB_SPEND_PATH", None)
    attempt("ambiente_forza_abilitato", env_enabled)

    # 4. sottoclasse che prova a riprendersi `submit`
    def override():
        base_cls = sentinel_class("fake_spender_override")

        class Override(base_cls):                           # noqa: WPS431
            def submit(self, spec):
                self.reached += 1
                return None
        return f"classe creata: {Override.__name__}"
    attempt("sottoclasse_riprende_submit", override)

    # 5. un wrapper che NASCONDE la capability: e' un FakeAdapter a tutti gli
    #    effetti (supera il FAKE MODE gate del runtime, non dichiara
    #    `spend_capable`), ma delega submit/authorize_payload alla SENTINELLA.
    #    E' l'attacco piu' onesto contro un confine dichiarativo: mentire sulla
    #    dichiarazione. Non funziona, perche' il confine del Core non sta sul
    #    wrapper — sta sullo spender, ed e' li' che la concessione manca.
    from adapters.fake import FakeAdapter
    masked_inner = {}

    def masked():
        inner = build_sentinel("fake_masked_inner")
        masked_inner["adapter"] = inner

        class MaskedFake(FakeAdapter):                      # noqa: WPS431
            name = "fake_masked"
            spend_capable = False                           # la bugia

            def __init__(self, inner):
                FakeAdapter.__init__(self)
                self._inner = inner

            def serialize(self, spec):
                return self._inner.serialize(spec)

            def authorize_payload(self, digest):
                return self._inner.authorize_payload(digest)

            def submit(self, spec):
                return self._inner.submit(spec)

        go_candidate.go(_inputs("p9 masked"), adapter=MaskedFake(inner), provider_mode="fake",
                        store_path=db_prefix + "_5.db", core_path=core_path,
                        operation_id="LSPC1:p9e", authorization=None, **pin)
    attempt("wrapper_che_nasconde_la_capability", masked)
    attempts["_masked_inner"] = observe(masked_inner.get("adapter"))

    out.update(ok=True, attempts=attempts)
    out["core_imported"] = "adapters.base" in sys.modules
    return out


# ===========================================================================
# P10 — hf_batch (il percorso "di produzione" del runtime) con uno spender
# ===========================================================================
def p10_hf_batch_legacy(core_path: str, db: str) -> dict:
    """`Batch.run_job -> go(authorization=None)` con uno SPENDER (#4)."""
    out = _prelude(core_path)
    adapter = None
    try:
        # `Batch` non riceve un core_path: usa `go_candidate.DEFAULT_CORE_PATH`, letto
        # dall'ambiente al momento dell'import. Nel processo figlio l'import non e'
        # ancora avvenuto, quindi qui si dichiara il Core sotto sonda.
        os.environ["CREATIVE_OS_CORE_PATH"] = core_path
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        import json
        from lspc1.spenders import build_sentinel
        from runtime import hf_batch_runtime as hb
        from runtime.hf_batch_bridge import media_sha_from_lock
        handoff = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16")
        lock = json.load(open(os.path.join(handoff, "EVIDENCE",
                                           "MOTION_B1_B4C_RUNTIME_LOCK.json"), encoding="utf-8"))
        res = media_sha_from_lock(lock)
        adapter = build_sentinel()
        b = hb.Batch(os.path.join(handoff, "SPECS", "spec_motion_B1_B4C.json"),
                     adapter=adapter, store_path=db, max_polls=3, media_sha256=None,
                     authorization=None)
        import threading
        current = threading.local()
        b.media_sha256 = lambda flag, rid, ref: res(current.asset)(flag, rid, ref)
        orig = b.run_job

        def run_job(j, lk):
            current.asset = j["asset"]
            return orig(j, lk)
        b.run_job = run_job
        b.lock_path = os.path.join(handoff, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json")
        b.require = lambda: lock
        b.fingerprint = lambda: (lock["fingerprint_sha256"], {})
        b.trace_path = os.path.join(os.path.dirname(db), "LSPC1_P10_TRACE.json")
        trace = b.go()
        out.update(ok=True, run_verdict=trace["run_verdict"],
                   job_status=sorted({j.get("run_status") for j in trace["jobs"]}),
                   job_errors=sorted({str(j.get("error"))[:80] for j in trace["jobs"]}))
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
        out["trace"] = traceback.format_exc(limit=4)
    return _epilogue(out, db, adapter)


def _entry(q, fn, args, kwargs):
    try:
        q.put(fn(*args, **kwargs))
    except BaseException as e:                              # noqa: BLE001
        q.put({"ok": False, "error": type(e).__name__, "message": str(e),
               "trace": traceback.format_exc(limit=5)})


# ===========================================================================
# MIGRAZIONE DEI TEST STORICI — esecutore del PERCORSO GOVERNATO
#
# I test storici usavano `go(authorization=None)` (LEGACY_LAB): budget grezzo,
# nessuna quote, nessun envelope, resume-as-start. `gov_run` esegue la STESSA
# operazione sul percorso GOVERNATO, separando i due ruoli che in produzione
# stanno da due parti diverse del confine di privilegio:
#
#   AUTORITA'  apre l'envelope ed emette la quote fidata (importo incluso);
#   CLIENT     presenta operazione, intento, motivo e al massimo un `quote_id`.
#
# L'importo NON viene mai dal client: `amount` e' cio' che l'AUTORITA' decide in
# questo laboratorio, ed e' scelto per riprodurre esattamente il numero che il
# test storico verificava (es. T10: 30 unita' impegnate). Il listino LAB
# (`lab_price_for`) resta una comodita' del laboratorio, non un contratto: qui
# serve l'importo storico, non il prezzo di listino.
# ===========================================================================
def gov_run(core_path: str, db: str, prompt: str, *, op: str, amount: int = 10,
            envelope: str | None = None, authorized: int = 1000,
            unit: str = "synthetic_units", adapter_kind: str = "fake",
            adapter_kw: dict | None = None, max_polls: int = 5,
            intent: str = "resume", reason: str | None = None, auto_permit: bool = False,
            permit_id: str | None = None, quote_id: str = "__auto__",
            issue_quote: bool = True, inputs_over: dict | None = None,
            budget_units: int | None = None, envelope_units: int | None = None,
            clock_offset: float = 0.0, crash_after_send: bool = False,
            barrier=None, sentinel: bool = False) -> dict:
    out: dict = {"pid": os.getpid(), "submits": None, "op": op}
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from runtime import go_candidate
        from runtime.authorization import AuthorizationRefused, LabAuthorization, scope_of
        from runtime.core_pin import CorePinError
        from runtime.provider_gate import RealProviderDisabled
        from tests.worker import _make_adapter
        env = envelope or ("ENV_" + scope_of(op))
        if sentinel:
            from lspc1.spenders import build_sentinel
            adapter = build_sentinel(**(adapter_kw or {}))
        else:
            adapter = _make_adapter(adapter_kind, **(adapter_kw or {}))
        if crash_after_send:
            _send = adapter.transport.send

            def _send_then_die(payload):
                _send(payload)
                os._exit(4)
            adapter.transport.send = _send_then_die
        qid = quote_id
        if qid == "__auto__":
            qid = None
            if issue_quote:
                qid = _authority_quote(core_path, db, prompt=prompt, operation_id=op,
                                       envelope=env, amount=amount, authorized=authorized,
                                       unit=unit, inputs_over=inputs_over)["quote_id"]
        out["quote_issued"] = qid
        kw = dict(adapter=adapter, provider_mode="fake", store_path=db, core_path=core_path,
                  max_polls=max_polls, intent=intent, reason=reason, auto_permit=auto_permit,
                  permit_id=permit_id, operation_id=op, quote_id=qid,
                  budget_units=budget_units, envelope_units=envelope_units,
                  authorization=LabAuthorization({scope_of(op): env}), **_pin_kwargs(core_path))
        if clock_offset:
            import time as _t
            kw["clock"] = lambda: _t.time() + clock_offset
        if barrier is not None:
            barrier.wait(timeout=30)
        res = go_candidate.go(_inputs(prompt, **(inputs_over or {})), **kw)
        out.update(ok=True, outcome=res.outcome, reservation_outcome=res.reservation_outcome,
                   job_id=res.job_id, provider_job_id=res.provider_job_id, provider=res.provider,
                   state=res.state, spec_key=res.spec_key, persisted=res.persisted,
                   intent=res.intent, resumed_terminal=res.resumed_terminal,
                   permit_id=res.permit_id, operation_id=res.operation_id,
                   core_pin=res.core_pin, governance=res.governance, envelope_id=res.envelope_id,
                   quote_id=res.quote_id, budget_units=res.budget_units, resumed=res.resumed,
                   requested_spec_key=res.requested_spec_key,
                   legacy_resume_as_start=res.legacy_resume_as_start)
    except BaseException as e:                              # noqa: BLE001
        out.update(ok=False, error=type(e).__name__, code=getattr(e, "code", None),
                   message=str(e)[:400])
        if type(e).__name__ in ("AuthorizationRefused", "IntentRefused"):
            out["error"] = type(e).__name__
    if adapter is not None:
        out["submits"] = adapter.submits
        out["transport_sent"] = getattr(getattr(adapter, "transport", None), "sent_count", None)
        if sentinel:
            from lspc1.spenders import observe
            out["sentinel"] = observe(adapter)
    out["core_imported"] = "adapters.base" in sys.modules
    return out


def gov_authority(core_path: str, db: str, method: str, *args, **kwargs) -> dict:
    """Lato AUTORITA' in un processo separato: letture e primitive economiche.
    Sostituisce, nella suite migrata, le chiamate storiche a `tests.worker.store_call`
    che servivano a emettere quote/permessi o a leggere ledger e permessi."""
    out = {"pid": os.getpid(), "method": method}
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from registry.reservations import SqliteReservationStore
        store = SqliteReservationStore(db)
        if method == "authority_quote":
            # `core_path` e `db` sono gia' posizionali: il chiamante passa solo i
            # parametri della quote (prompt, operation_id, envelope, amount, ...).
            kwargs.pop("core_path", None)
            kwargs.pop("db", None)
            return {"pid": os.getpid(), "ok": True,
                    "result": _authority_quote(core_path, db, **kwargs)}
        r = getattr(store, method)(*args, **kwargs)
        if isinstance(r, list):
            r = [x.to_dict() if hasattr(x, "to_dict") else x for x in r]
        elif hasattr(r, "to_dict"):
            r = r.to_dict()
        out.update(ok=True, result=r)
    except BaseException as e:                              # noqa: BLE001
        out.update(ok=False, error=type(e).__name__, message=str(e)[:300])
    return out


def read_state(core_path: str, db: str) -> dict:
    """Come `tests.worker.read_state`, piu' i totali economici: nella suite
    migrata il budget non e' piu' un numero grezzo del client, e va letto dove
    ora vive davvero (ledger + envelope)."""
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    from tests.worker import read_state as legacy_read_state
    out = legacy_read_state(db, core_path)
    from registry.reservations import SqliteReservationStore
    store = SqliteReservationStore(db)
    out["ledger_totals"] = store.ledger_totals()
    return out


def gov_hf_batch(core_path: str, db: str, *, namespace: str = "WOG",
                 spec_name: str = "spec_motion_B1_B4C.json", amount: int = 10,
                 envelope: str | None = None, authorized: int = 1000,
                 intent: str = "resume", reason: str | None = None, auto_permit: bool = False,
                 rounds: int = 1, issue_quotes: bool = True, max_polls: int = 5) -> dict:
    """`hf_batch_runtime.Batch` sul PERCORSO GOVERNATO, su una spec REALE.

    Lato AUTORITA': un envelope per lo scope del work order e una quote fidata per
    ogni asset, legata all'operazione `<namespace>:<asset>` e allo spec_key reale.
    Lato CLIENT: `Batch` presenta solo `quote_for(asset) -> quote_id`."""
    out = {"pid": os.getpid(), "namespace": namespace}
    adapter = None
    try:
        os.environ["CREATIVE_OS_CORE_PATH"] = core_path
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        import json
        import threading
        from adapters.base import GenSpec
        from registry.reservations import SqliteReservationStore
        from runtime import hf_batch_runtime as hb
        from runtime.authorization import LabAuthorization
        from runtime.genspec_bridge import build_genspec
        from runtime.hf_batch_bridge import go_inputs_from_job, media_sha_from_lock
        from tests.worker import _make_adapter
        handoff = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16")
        lock = json.load(open(os.path.join(handoff, "EVIDENCE",
                                           "MOTION_B1_B4C_RUNTIME_LOCK.json"), encoding="utf-8"))
        spec_json = json.load(open(os.path.join(handoff, "SPECS", spec_name), encoding="utf-8"))
        res = media_sha_from_lock(lock)
        env = envelope or ("ENV_" + namespace)
        quotes: dict[str, str] = {}
        store = SqliteReservationStore(db)
        store.open_envelope(env, authorized, unit="synthetic_units", scope=None)
        for j in spec_json["jobs"]:
            asset = j["asset"]
            gs = build_genspec(go_inputs_from_job(spec_json, j, res(asset)), GenSpec)
            if issue_quotes:
                quotes[asset] = store.issue_quote(
                    operation_id=f"{namespace}:{asset}", spec_key=gs.spec_key,
                    envelope_id=env, amount=amount, unit="synthetic_units")
        out["quotes"] = dict(quotes)
        adapter = _make_adapter("fake")
        b = hb.Batch(os.path.join(handoff, "SPECS", spec_name), adapter=adapter, store_path=db,
                     max_polls=max_polls, media_sha256=None, intent=intent,
                     attempt_reason=reason, auto_permit=auto_permit,
                     operation_namespace=namespace,
                     authorization=LabAuthorization({namespace: env}),
                     quote_for=quotes.get)
        current = threading.local()
        b.media_sha256 = lambda flag, rid, ref: res(current.asset)(flag, rid, ref)
        orig = b.run_job

        def run_job(j, lk):
            current.asset = j["asset"]
            return orig(j, lk)
        b.run_job = run_job
        b.lock_path = os.path.join(handoff, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json")
        b.require = lambda: lock
        b.fingerprint = lambda: (lock["fingerprint_sha256"], {})
        b.trace_path = os.path.join(os.path.dirname(db), f"LSPC1_{namespace}_TRACE.json")
        # Il primo giro e' la PRIMA SPESA (new_attempt + motivo + permesso); i giri
        # successivi sono REPLAY, cioe' RESUME: nessuna nuova quote, nessun nuovo
        # permesso, nessun nuovo submit. E' la stessa semantica che il test storico
        # verificava con `rounds`, espressa dove ora vive: nell'intento.
        traces = []
        for i in range(rounds):
            if i == 1:
                b.intent, b.attempt_reason, b.auto_permit = "resume", None, False
            traces.append(b.go())
        out.update(ok=True, submits=adapter.submits, traces=[
            {"run_verdict": t["run_verdict"],
             "jobs": [{k: x.get(k) for k in ("asset", "run_status", "reservation_outcome",
                                             "job_id", "operation_id", "governance", "resumed",
                                             "quote_id", "budget_units", "permit_id",
                                             "legacy_resume_as_start", "error")}
                      for x in t["jobs"]]} for t in traces])
    except BaseException as e:                              # noqa: BLE001
        out.update(ok=False, error=type(e).__name__, code=getattr(e, "code", None),
                   message=str(e)[:300], trace=traceback.format_exc(limit=4))
    if adapter is not None:
        out["submits"] = adapter.submits
    return out


# ===========================================================================
# P11 — HUMAN REVIEW 01: l'autorizzazione si puo' STAMPARE IN CASA?
#
# Le controprove E04/E05 verificavano una concessione scaduta, rientrante, di altra
# spec, di altro digest e un journal alterato. Nessuna costruiva direttamente una
# `DispatchAuthorization` falsa — ed era esattamente il varco. Questa sonda lo prova
# nei tre modi in cui un chiamante ci proverebbe davvero.
#
# Gira su ENTRAMBI i Core: su `44f9ea29` (il candidate revisionato) deve RIUSCIRE,
# altrimenti non c'e' nulla da correggere; sul delta correttivo deve fallire.
# ===========================================================================
def _forge_fields(adapter, spec) -> dict:
    import hashlib
    return {"job_id": "forged", "spec_key": spec.spec_key, "operation_id": "forged-op",
            "attempt_token": "forged-attempt",
            "payload_digest": hashlib.sha256(adapter.serialize(spec)).hexdigest(),
            "provider": adapter.name, "provider_account": adapter.account_id,
            "envelope_id": "forged-envelope", "quote_id": "forged-quote",
            "quote_amount": 1, "quote_unit": "units"}


def _attempt(label: str, fn, into: dict) -> None:
    try:
        into[label] = {"refused": False, "result": str(fn())[:120]}
    except BaseException as e:                              # noqa: BLE001
        into[label] = {"refused": True, "error": type(e).__name__,
                       "code": getattr(e, "code", None), "message": str(e)[:200]}


def p11_forged_authorization(core_path: str, db: str, *, prompt: str = "p11 forged") -> dict:
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        import inspect
        import adapters.base as base
        from adapters.base import DispatchAuthorization, GenSpec, grant_dispatch
        from lspc1.spenders import build_sentinel
        from runtime.genspec_bridge import build_genspec
        adapter = build_sentinel()
        spec = build_genspec(_inputs(prompt), GenSpec)
        fields = _forge_fields(adapter, spec)
        attempts: dict = {}
        sig = inspect.signature(grant_dispatch)
        out["grant_dispatch_signature"] = list(sig.parameters)
        out["grant_dispatch_accepts_authorization"] = list(sig.parameters)[:2] == ["adapter", "auth"]

        # 1) il CONTROESEMPIO ESATTO della Human Review
        forged = {}

        def build_and_dispatch():
            f = DispatchAuthorization(**fields)
            forged["obj"] = f
            with grant_dispatch(adapter, f):
                adapter.authorize_payload(f.payload_digest)
                return adapter.submit(spec).provider_job_id
        _attempt("counterexample_review", build_and_dispatch, attempts)

        # 2) costruzione che AGGIRA il costruttore (chi falsifica non si ferma a un if)
        def bypass_constructor():
            obj = object.__new__(DispatchAuthorization)
            for k, v in {**fields, "mint": getattr(base, "_MINT", None)}.items():
                try:
                    object.__setattr__(obj, k, v)
                except AttributeError:
                    pass
            forged["bypassed"] = obj
            return obj
        _attempt("bypass_constructor", bypass_constructor, attempts)

        # 3) l'oggetto fabbricato infilato a mano nello slot della concessione
        def slot_injection():
            f = forged.get("bypassed") or forged.get("obj")
            if f is None:
                raise RuntimeError("nessun oggetto fabbricato disponibile")
            slot = base._grant_slot(adapter)
            slot.auth = f
            try:
                adapter.authorize_payload(f.payload_digest)
                return adapter.submit(spec).provider_job_id
            finally:
                slot.auth = None
        _attempt("slot_injection", slot_injection, attempts)

        # 4) la vecchia forma a due argomenti, se esiste ancora
        def legacy_two_arg_grant():
            f = forged.get("bypassed") or forged.get("obj")
            with grant_dispatch(adapter, f):
                return "grant aperto"
        _attempt("grant_dispatch_two_arg", legacy_two_arg_grant, attempts)

        out.update(ok=True, attempts=attempts,
                   reached_by_any=bool((getattr(adapter, "reached", 0) or 0) > 0))
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
        out["trace"] = traceback.format_exc(limit=4)
    return _epilogue(out, None, adapter)


# ===========================================================================
# P12 — gli hook di implementazione, chiamati direttamente
# ===========================================================================
def p12_direct_implementation_hooks(core_path: str, db: str, *, prompt: str = "p12 hooks") -> dict:
    """In Python il trattino basso non e' un confine di sicurezza. O gli hook sono
    protetti, o dietro la struttura c'e' una porta aperta."""
    out = _prelude(core_path)
    adapter = None
    try:
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        import adapters.base as base
        from adapters.base import DispatchAuthorization, GenSpec
        from lspc1.spenders import build_sentinel
        from runtime.genspec_bridge import build_genspec
        adapter = build_sentinel()
        spec = build_genspec(_inputs(prompt), GenSpec)
        fields = _forge_fields(adapter, spec)
        forged = object.__new__(DispatchAuthorization)
        for k, v in {**fields, "mint": getattr(base, "_MINT", None)}.items():
            try:
                object.__setattr__(forged, k, v)
            except AttributeError:
                pass
        attempts: dict = {}
        _attempt("_authorize_payload_senza_grant",
                 lambda: adapter._authorize_payload(fields["payload_digest"], None), attempts)
        _attempt("_dispatch_senza_grant",
                 lambda: adapter._dispatch(spec, None), attempts)
        _attempt("_authorize_payload_con_autorizzazione_fabbricata",
                 lambda: adapter._authorize_payload(fields["payload_digest"], forged), attempts)
        _attempt("_dispatch_con_autorizzazione_fabbricata",
                 lambda: adapter._dispatch(spec, forged), attempts)
        cls = type(adapter)
        out.update(ok=True, attempts=attempts,
                   hooks_guarded={n: bool(getattr(cls.__dict__.get(n), "__lspc_guarded__", False))
                                  for n in ("_dispatch", "_authorize_payload")})
    except BaseException as e:                              # noqa: BLE001
        _err(out, e)
        out["trace"] = traceback.format_exc(limit=4)
    return _epilogue(out, None, adapter)
