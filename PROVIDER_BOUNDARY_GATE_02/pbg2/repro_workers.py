"""PHASE A — RIPRODUZIONI PRE-FIX, eseguite in PROCESSI REALI (multiprocessing 'spawn').

Ogni funzione e' a livello di modulo (spawn la reimporta nel figlio) e riferisce un dict
serializzabile. MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI.

Queste funzioni NON correggono nulla: dimostrano che il difetto esiste sul Runtime
canonico attuale (0698279…). Se una premessa del mandato risultasse falsa, e' qui che
deve emergere, e viene riferita come NOT_REPRODUCED / ALREADY_CLOSED.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import traceback

GATE01 = os.environ.get("RUNTIME_GATE_ROOT", "/home/user/esercitazioni/RUNTIME_INTEGRATION_GATE_01")
BUNDLE01 = os.environ.get("PBGATE01_ROOT", "/home/user/esercitazioni/PROVIDER_BOUNDARY_HARDENING_01")
for _p in (GATE01, BUNDLE01):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pbgate import pb_worker                                # noqa: E402  (helper della fase precedente)
from tests.worker import make_inputs                        # noqa: E402


def _core(core_path: str) -> None:
    if core_path not in sys.path:
        sys.path.insert(0, core_path)


def _err(e: BaseException) -> dict:
    return {"ok": False, "error": type(e).__name__, "code": getattr(e, "code", None),
            "message": str(e), "trace": traceback.format_exc(limit=4)}


def _totals(db: str, core_path: str) -> dict:
    _core(core_path)
    from registry.reservations import SqliteReservationStore
    return SqliteReservationStore(db).ledger_totals()


# ===================================================================== NG-04 (freshness)
def repro_ng04_stale_report_accepted(db: str, core_path: str) -> dict:
    """PREMESSA DEL MANDATO: `max_age_s` e' opzionale, quindi un report autenticato
    arbitrariamente VECCHIO viene applicato. Riproduzione su due assi:

      A. nessuna freshness richiesta  -> report del 1970 applicato;
      B. freshness richiesta ma timestamp NEL FUTURO -> `now - issued_at` e' negativo,
         quindi la condizione `> max_age_s` non scatta mai: applicato lo stesso.
    """
    out: dict = {"ok": False}
    try:
        from runtime.payload_snapshot import SnapshotLedger, ledger_dir_for
        from runtime.reconciliation import (LabProviderStatusAuthority, ReconciliationRefused,
                                            nonce_dir_for, reconcile_authenticated)
        import inspect
        _core(core_path)
        from adapters.fake import FakeAdapter
        from registry.reservations import SqliteReservationStore

        sig = inspect.signature(reconcile_authenticated)
        out["max_age_s_default"] = repr(sig.parameters["max_age_s"].default)
        out["freshness_is_optional"] = sig.parameters["max_age_s"].default is None

        store = SqliteReservationStore(db)
        adapter = FakeAdapter(account_id="fake_acct_a")
        auth = LabProviderStatusAuthority("LAB_SECRET_repro_ng04", "fake", "fake_acct_a")
        ledger = SnapshotLedger(ledger_dir_for(db))

        def attempt(label, row, *, issued_at, max_age_s, state):
            rep = auth.report(provider_job_id="pv_remote_1", attempt_token=row["attempt_token"],
                              payload_digest=row["payload_digest"], operation_id=row["operation_id"],
                              job_id=row["job_id"], state=state, remote_ref="remote:pv_remote_1",
                              now=issued_at)
            try:
                job = reconcile_authenticated(store, adapter, rep, job_id=row["job_id"], key=auth.key,
                                              nonce_dir=nonce_dir_for(db), snapshot_ledger=ledger,
                                              max_age_s=max_age_s)
                return {"applied": True, "state": job.state.value, "issued_at": issued_at,
                        "max_age_s": max_age_s, "label": label}
            except ReconciliationRefused as e:
                return {"applied": False, "code": e.code, "issued_at": issued_at,
                        "max_age_s": max_age_s, "label": label}

        rows = [r for r in pb_worker._rows(db) if r["state"] == "SUBMIT_UNKNOWN"]
        out["submit_unknown_rows"] = [r["job_id"] for r in rows]
        if len(rows) < 2:
            out["error"] = "PRECONDITION: servono 2 job SUBMIT_UNKNOWN"
            return out
        # A: report del 1970 (issued_at = 0), nessuna freshness richiesta
        out["A_ancient_report_no_policy"] = attempt("A", rows[0], issued_at=0.0, max_age_s=None,
                                                    state="SUCCEEDED")
        # B: freshness richiesta (60s) ma timestamp 10 anni NEL FUTURO
        out["B_future_report_with_policy"] = attempt("B", rows[1], issued_at=2_000_000_000.0,
                                                     max_age_s=60.0, state="SUCCEEDED")
        out["rows_after"] = pb_worker._rows(db)
        out["reproduced"] = bool(out["A_ancient_report_no_policy"].get("applied")
                                 and out["B_future_report_with_policy"].get("applied"))
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== NG-05 (atomicita')
def repro_ng05_core_surface(core_path: str) -> dict:
    """La domanda del mandato: il Core canonico offre GIA' una primitive che, in UNA
    transazione, fa terminalizzazione + settlement zero + provenance PARAMETRICA + ledger +
    anomaly/evidence + CAS? Si risponde leggendo il contratto reale, non la documentazione."""
    import inspect
    out: dict = {"ok": False}
    try:
        _core(core_path)
        from adapters import base as core_base
        from registry.reservations import SqliteReservationStore

        proto = [n for n in dir(core_base.ReservationStore) if not n.startswith("__")]
        candidates = {}
        for name in ("mark_refused_before_send", "reconcile", "settle"):
            fn = getattr(SqliteReservationStore, name)
            src = inspect.getsource(fn)
            candidates[name] = {
                "signature": str(inspect.signature(fn)),
                "in_protocol": name in proto,
                # provenance parametrica = la fonte del settlement arriva dal chiamante
                "settlement_source_parametric": ("source" in inspect.signature(fn).parameters),
                "writes_settled_units": "settled_units=" in src,
                "writes_ledger_settle": "'SETTLE'" in src,
                "writes_state": "_set_state(" in src,
                "hardcoded_sources": sorted({t for t in ("TRANSPORT_ATTESTED_NOT_SENT",)
                                             if t in src}),
                "accepts_caller_extra_sql": "extra_sql" in inspect.signature(fn).parameters,
            }
        single_tx = [n for n, c in candidates.items()
                     if c["writes_state"] and c["writes_settled_units"]
                     and c["settlement_source_parametric"]]
        out["protocol_methods"] = sorted(proto)
        out["candidates"] = candidates
        out["single_transaction_primitive_with_parametric_provenance"] = single_tx
        out["core_change_required"] = not single_tx
        out["private_set_state_is_private"] = hasattr(SqliteReservationStore, "_set_state")
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def repro_ng05_crash_between(db: str, core_path: str, job_id: str) -> dict:
    """PROCESSO REALE che muore FRA `reconcile` e `settle`: e' esattamente la finestra
    descritta da NG-05. Il figlio esce con os._exit(7) dopo la prima transazione."""
    out: dict = {"ok": False}
    try:
        from runtime.payload_snapshot import PRE_SUBMIT_REFUSAL_REMOTE_REF, PRE_SUBMIT_REFUSAL_SOURCE
        _core(core_path)
        from adapters.base import JobState
        from registry.reservations import SqliteReservationStore
        store = SqliteReservationStore(db)
        job = store.get(job_id)
        evidence = {"source": PRE_SUBMIT_REFUSAL_SOURCE, "remote_ref": PRE_SUBMIT_REFUSAL_REMOTE_REF,
                    "reason": "repro NG-05: crash fra reconcile e settle",
                    "attested_by": "runtime_snapshot_guard", "transport_attestation": None}
        store.reconcile(job, JobState("FAILED"), evidence, now=1000.0)
        sys.stdout.flush()
        os._exit(7)                     # morte reale: `settle` non avverra' mai
    except Exception as e:              # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== ORPHAN LEASE
def repro_orphan_no_exit(db: str, core_path: str) -> dict:
    """Riverifica sul Runtime canonico attuale: una RESERVED_NO_INTENT non ha uscite e
    nessun meccanismo di lease (parametrico o no) esiste nel runtime."""
    out: dict = {"ok": False}
    try:
        import runtime.orphan_lease as ol
        out["module_public_api"] = sorted(n for n in dir(ol) if not n.startswith("_"))
        out["reclaim_policy_constant"] = getattr(ol, "RECLAIM_POLICY", None)
        out["has_lease_mechanism"] = any(
            n.lower().startswith("lease") or "reclaim" in n.lower()
            for n in out["module_public_api"] if n not in ("RECLAIM_POLICY",))
        scen = pb_worker.orphan_scenario(db, core_path, "LAB_SECRET_repro_orphan")
        out["scenario"] = scen
        cls = scen.get("classify_no_intent") or {}
        out["reproduced"] = (cls.get("class") == "RESERVED_NO_INTENT"
                             and cls.get("exits_available") == []
                             and not out["has_lease_mechanism"])
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== LEGACY SPEND PATHS
def repro_legacy_spendable(db: str, core_path: str, prompt: str, op: str) -> dict:
    """Il percorso LEGACY_LAB (`authorization=None`) raggiunge ancora il trasporto con
    l'interruttore nello stato di default del Runtime canonico (`ENABLED_LAB_ONLY`):
    nessuna quote, nessun envelope derivato, nessun permit sulla prima spesa.

    NOTA: l'helper storico `pb_worker.legacy_go_disabled` passa `adapter=None` e verifica
    solo il ramo CHIUSO; per il ramo APERTO serve un adapter reale, altrimenti si misura
    `REAL_PROVIDER_DISABLED` e non la spendibilita' del percorso legacy."""
    out: dict = {"ok": False}
    try:
        from runtime import go_candidate
        from runtime.payload_snapshot import ledger_dir_for
        from runtime.provider_gate import legacy_spend_path_state
        _core(core_path)
        from adapters.fake import FakeAdapter
        out["switch_state_default"] = legacy_spend_path_state()
        adapter = FakeAdapter(account_id="fake_acct_legacy")
        res = go_candidate.go(make_inputs(prompt), adapter=adapter, provider_mode="fake",
                              store_path=db, core_path=core_path, max_polls=3,
                              intent="resume", operation_id=op, authorization=None)
        out["open"] = {"ok": True, "state": res.state, "job_id": res.job_id,
                       "governance": res.governance, "quote_id": res.quote_id,
                       "envelope_id": res.envelope_id, "permit_id": res.permit_id,
                       "budget_units": res.budget_units,
                       "legacy_resume_as_start": res.legacy_resume_as_start,
                       "submits": adapter.submits,
                       "ledger_dir": ledger_dir_for(db)}
        out["closed"] = pb_worker.legacy_go_disabled(db, core_path, prompt + " closed", op + "_closed",
                                                     disable=True)
        closed_code = out["closed"].get("code") or out["closed"].get("error")
        out["closed_code"] = closed_code
        out["reproduced"] = bool(out["open"]["submits"] >= 1
                                 and out["open"]["governance"] == "LEGACY_LAB"
                                 and out["open"]["quote_id"] is None
                                 and closed_code == "LEGACY_SPEND_PATH_DISABLED")
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def repro_test_helper_store_call(db: str, core_path: str) -> dict:
    """LEGACY #7: `tests/worker.store_call` invoca QUALUNQUE metodo dello store, fuori dal
    percorso governato. Same-UID: il confine P-B01 non lo copre."""
    from tests import worker as histworker
    out: dict = {"ok": False}
    try:
        r = histworker.store_call(db, core_path, "reserve_or_get_live_by_prompt_op", "legacy helper",
                                  "lab:legacy_helper")
        out["store_call"] = r
        out["rows"] = pb_worker._rows(db)
        out["reproduced"] = bool(r.get("ok"))
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def repro_core_primitive_direct(db: str, core_path: str) -> dict:
    """LEGACY #10/#11: le primitive del Core (`transport.pipeline.run_job`, `store.reconcile`
    raw) sono invocabili da qualunque codice che abbia il Core in sys.path e un adapter.
    Nessun pin, nessun intent, nessuna authorization del Runtime."""
    out: dict = {"ok": False}
    try:
        _core(core_path)
        from adapters.base import GenSpec, JobState
        from adapters.fake import FakeAdapter
        from registry.reservations import SqliteReservationStore
        from transport.pipeline import run_job
        from runtime.genspec_bridge import build_genspec
        store = SqliteReservationStore(db)
        adapter = FakeAdapter(account_id="fake_acct_direct")
        spec = build_genspec(make_inputs("direct core primitive"), GenSpec)
        job = run_job(adapter, spec, store, clock=lambda: 1.0, max_polls=3, budget_units=0,
                      envelope_units=None, operation_id="lab:core_primitive")
        out["run_job_direct"] = {"job_id": job.job_id, "state": job.state.value,
                                 "submits": adapter.submits,
                                 "provider_account": job.provider_account}
        # store.reconcile raw con evidenza arbitraria su un job terminale -> rifiutato dal
        # contratto (terminale assorbente); su uno vivo sarebbe accettato: si verifica su un
        # job RESERVED creato qui.
        o, live = store.reserve_or_get_live(build_genspec(make_inputs("raw reconcile"), GenSpec),
                                            now=1.0, operation_id="lab:raw_reconcile")
        try:
            r = store.reconcile(live, JobState("FAILED"),
                                {"source": "chiunque", "remote_ref": "pv:di_qualcun_altro"})
            out["raw_reconcile"] = {"accepted": True, "state": r.state.value}
        except Exception as e:                              # noqa: BLE001
            out["raw_reconcile"] = {"accepted": False, "error": type(e).__name__, "message": str(e)}
        out["reproduced"] = bool(out["run_job_direct"]["submits"] >= 1
                                 and out["raw_reconcile"].get("accepted"))
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== P-B02 + P-B01 composition
def repro_composition_not_exercised(core_path: str) -> dict:
    """NG-06. Due fatti, letti dal codice reale e non dalla documentazione:

      1. il daemon spender (`pbgate/spender_daemon.py`) non ha alcuna op di reconciliation:
         lo schema chiuso e' `ALLOWED_OPS` + `whoami`. La riconciliazione autenticata non
         viene MAI eseguita dentro il dominio isolato;
      2. l'API espone la chiave derivata (`LabProviderStatusAuthority.key`, `derive_report_key`):
         chiunque possieda il segreto, ovunque giri, produce un report valido.
    """
    import ast
    import inspect
    out: dict = {"ok": False}
    try:
        from runtime import reconciliation as rec
        from tests.boundary_mock import ALLOWED_OPS
        daemon_src = os.path.join(BUNDLE01, "pbgate", "spender_daemon.py")
        tree = ast.parse(open(daemon_src, encoding="utf-8").read(), filename=daemon_src)
        daemon_extra_ops = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "DAEMON_OPS":
                        daemon_extra_ops = list(ast.literal_eval(node.value))
        calls = {n.func.attr for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        out["daemon_allowed_ops"] = sorted(set(ALLOWED_OPS) | set(daemon_extra_ops))
        out["daemon_has_reconciliation_op"] = any(
            "reconcil" in o or o == "report" for o in out["daemon_allowed_ops"])
        out["daemon_imports_reconciliation_module"] = "reconciliation" in open(
            daemon_src, encoding="utf-8").read()
        out["daemon_calls_reconcile_authenticated"] = "reconcile_authenticated" in (calls | names)
        out["key_is_public_property"] = isinstance(
            getattr(rec.LabProviderStatusAuthority, "key", None), property)
        out["derive_report_key_is_public"] = inspect.isfunction(rec.derive_report_key)
        out["reproduced"] = (not out["daemon_has_reconciliation_op"]
                             and not out["daemon_calls_reconcile_authenticated"]
                             and out["key_is_public_property"])
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def repro_forge_with_leaked_key(db: str, core_path: str) -> dict:
    """Controprova del gap di COMPOSIZIONE: chi ottiene la chiave derivata (l'API la
    espone) forgia un report che supera la verifica, senza essere lo spender."""
    out: dict = {"ok": False}
    try:
        from runtime.payload_snapshot import SnapshotLedger, ledger_dir_for
        from runtime.reconciliation import (LabProviderStatusAuthority, ReconciliationRefused,
                                            nonce_dir_for, reconcile_authenticated, sign_report,
                                            REPORT_SCHEMA)
        _core(core_path)
        from adapters.fake import FakeAdapter
        from registry.reservations import SqliteReservationStore
        import secrets as _s
        rows = [r for r in pb_worker._rows(db) if r["state"] == "SUBMIT_UNKNOWN"]
        if not rows:
            out["error"] = "PRECONDITION: serve 1 job SUBMIT_UNKNOWN"
            return out
        row = rows[0]
        auth = LabProviderStatusAuthority("LAB_SECRET_repro_forge", "fake", "fake_acct_a")
        leaked_key = auth.key                       # <-- l'API la espone: nessun confine
        forged = sign_report(leaked_key, {
            "schema": REPORT_SCHEMA, "provider": "fake", "provider_account": "fake_acct_a",
            "provider_job_id": "pv_forged", "attempt_token": row["attempt_token"],
            "payload_digest": row["payload_digest"], "operation_id": row["operation_id"],
            "job_id": row["job_id"], "state": "SUCCEEDED", "remote_ref": "remote:forged",
            "nonce": f"nonce_{_s.token_hex(16)}", "issued_at": 1000.0})
        store = SqliteReservationStore(db)
        adapter = FakeAdapter(account_id="fake_acct_a")
        try:
            job = reconcile_authenticated(store, adapter, forged, job_id=row["job_id"],
                                          key=leaked_key, nonce_dir=nonce_dir_for(db),
                                          snapshot_ledger=SnapshotLedger(ledger_dir_for(db)))
            out["forged_accepted"] = {"applied": True, "state": job.state.value}
        except ReconciliationRefused as e:
            out["forged_accepted"] = {"applied": False, "code": e.code}
        out["key_hex_prefix"] = leaked_key.hex()[:16]
        out["reproduced"] = bool(out["forged_accepted"].get("applied"))
        out["ok"] = True
    except Exception as e:                                  # noqa: BLE001
        out.update(_err(e))
    return out


def prepare_unknown_jobs(db: str, core_path: str, ops: list) -> dict:
    """Crea N job SUBMIT_UNKNOWN attraverso il percorso GOVERNATO (nessuna scorciatoia)."""
    out = {"jobs": []}
    for i, op in enumerate(ops):
        r = pb_worker.go_governed(db, core_path, f"prep unknown {i}", op, adapter_kind="submit_unknown")
        out["jobs"].append({"op": op, "result": {k: r.get(k) for k in ("ok", "state", "job_id", "error")}})
    out["rows"] = pb_worker._rows(db)
    out["ok"] = True
    return out
