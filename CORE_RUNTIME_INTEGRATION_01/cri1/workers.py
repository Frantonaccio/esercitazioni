"""COORDINATED CORE + RUNTIME INTEGRATION — NG-05. Helper eseguiti in PROCESSI REALI.

Ogni funzione e' a livello di modulo (multiprocessing 'spawn' la reimporta nel figlio) e
riferisce un dict serializzabile, mai eccezioni. Tutte girano contro il CORE CANDIDATE
approvato (`mark_refused_pre_submit`), mai contro la baseline.

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE01 = os.environ.get("RUNTIME_GATE_ROOT", os.path.join(REPO, "RUNTIME_INTEGRATION_GATE_01"))
BUNDLE01 = os.environ.get("PBGATE01_ROOT", os.path.join(REPO, "PROVIDER_BOUNDARY_HARDENING_01"))
for _p in (GATE01, BUNDLE01):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pbgate import pb_worker                                    # noqa: E402
from tests.worker import make_inputs                            # noqa: E402

PRE_SUBMIT_SOURCE = "RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED"
TRANSPORT_SOURCE = "TRANSPORT_ATTESTED_NOT_SENT"


def _core(core_path: str) -> None:
    if core_path not in sys.path:
        sys.path.insert(0, core_path)


def _err(e: BaseException) -> dict:
    return {"ok": False, "error": type(e).__name__, "code": getattr(e, "code", None),
            "message": str(e), "trace": traceback.format_exc(limit=4)}


def _snapshot(db: str, core_path: str, job_id: str | None = None) -> dict:
    """Stato economico e di audit, letto dallo store autorevole."""
    _core(core_path)
    from registry.reservations import SqliteReservationStore
    store = SqliteReservationStore(db)
    rows = pb_worker._rows(db)
    row = next((r for r in rows if r["job_id"] == job_id), None) if job_id else None
    anomalies = pb_worker._anomalies(db, job_id) if job_id else pb_worker._anomalies(db)
    ledger = [x for x in pb_worker._ledger(db) if not job_id or x["job_id"] == job_id]
    return {"row": row, "rows": rows, "anomalies": anomalies, "ledger": ledger,
            "settle_rows": [x for x in ledger if x["kind"] == "SETTLE"],
            "anomaly_kinds": [a["kind"] for a in anomalies],
            "totals": store.ledger_totals()}


def _runtime_report(anomalies: list) -> dict | None:
    """Il report che il runtime registra come anomalia `SNAPSHOT_REFUSED_PRE_SUBMIT`."""
    for a in reversed(anomalies):
        if a["kind"] == "SNAPSHOT_REFUSED_PRE_SUBMIT":
            return a["detail"]
    return None


# ===================================================================== NG-05 end-to-end
def e2e_pre_submit_refusal(db: str, core_path: str, prompt: str, op: str,
                           adapter_kind: str) -> dict:
    """Percorso GOVERNATO completo, con un adapter che fa fallire il binding dello snapshot
    a `mark_submitting`. Il runtime deve chiudere il tentativo con UNA sola transazione del
    Core, provenance veritiera e settlement zero, senza che nulla sia mai stato inviato."""
    out: dict = {"ok": False, "adapter_kind": adapter_kind}
    try:
        go = pb_worker.go_governed(db, core_path, prompt, op, adapter_kind=adapter_kind)
        out["go"] = {k: go.get(k) for k in ("ok", "error", "code", "message", "state",
                                            "job_id", "submits", "transport_sent_count")}
        row = next((r for r in pb_worker._rows(db) if r["operation_id"] == op), None)
        out["job_id"] = row["job_id"] if row else None
        snap = _snapshot(db, core_path, out["job_id"])
        out["state"] = snap
        report = _runtime_report(snap["anomalies"])
        out["runtime_report"] = report
        settle = snap["settle_rows"]
        recon = [a for a in snap["anomalies"] if a["kind"] == "RECONCILIATION"]
        out["reconciliation_evidence"] = recon[-1]["detail"]["evidence"] if recon else None
        out["verified"] = bool(
            # 1. terminale con settlement zero
            snap["row"] and snap["row"]["state"] == "FAILED"
            and snap["row"]["settled_units"] == 0
            and snap["row"]["settlement_source"] == PRE_SUBMIT_SOURCE
            # 2. UNA sola riga di ledger SETTLE, con la provenance veritiera
            and len(settle) == 1 and settle[0]["units"] == 0
            and settle[0]["source"] == PRE_SUBMIT_SOURCE
            and settle[0]["cost_known"] == 1
            # 3. una sola anomalia di riconciliazione, con l'evidenza del runtime
            and len(recon) == 1
            and recon[-1]["detail"]["evidence"]["source"] == PRE_SUBMIT_SOURCE
            and recon[-1]["detail"]["evidence"]["transport_attestation"] is None
            # 4. il runtime dichiara di aver usato l'API atomica
            and report and report.get("atomic") is True
            and report.get("core_api") == "mark_refused_pre_submit"
            and report.get("terminalized") is True and report.get("settled") is True
            and report.get("provenance") == PRE_SUBMIT_SOURCE
            # 5. nessuna provenance del trasporto in nessuna riga
            and all(x["source"] != TRANSPORT_SOURCE for x in snap["ledger"])
            # 6. nulla e' stato inviato
            and (go.get("transport_sent_count") in (0, None))
            # 7. esposizione rilasciata, nessun terminale non regolato
            and snap["totals"]["terminal_unsettled_jobs"] == 0)
        out["ok"] = True
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out


def e2e_crash_before_core_commit(db: str, core_path: str, prompt: str, op: str) -> dict:
    """PROCESSO REALE che muore DENTRO la transazione del Core, prima del COMMIT.

    Il crash viene iniettato al confine del Core (`_crash_hook`, la convenzione di test gia'
    usata da `settle`): il percorso del runtime e' quello vero, integralmente, fino alla
    chiamata dell'API. Se l'atomicita' non fosse reale, resterebbe qualcosa a meta'."""
    try:
        _core(core_path)
        from registry.reservations import SqliteReservationStore
        original = SqliteReservationStore.mark_refused_pre_submit

        def crashing(self, job, reason, *, source, evidence, now, _crash_hook=None):
            return original(self, job, reason, source=source, evidence=evidence, now=now,
                            _crash_hook=lambda: os._exit(13))
        SqliteReservationStore.mark_refused_pre_submit = crashing
        pb_worker.go_governed(db, core_path, prompt, op, adapter_kind="drift_nested")
        return {"ok": False, "error": "NO_CRASH", "message": "il figlio non e' morto"}
    except Exception as e:                                      # noqa: BLE001
        return _err(e)


def e2e_after_crash(db: str, core_path: str, op: str) -> dict:
    """Dopo il crash: NULLA deve essere stato applicato. Poi la stessa chiusura, senza
    crash, deve riuscire: la transazione abortita non lascia lock ne' stati intermedi."""
    out: dict = {"ok": False}
    try:
        row = next((r for r in pb_worker._rows(db) if r["operation_id"] == op), None)
        out["job_id"] = row["job_id"] if row else None
        snap = _snapshot(db, core_path, out["job_id"])
        out["after_crash"] = {"state": snap["row"]["state"] if snap["row"] else None,
                              "settled_units": snap["row"]["settled_units"] if snap["row"] else None,
                              "revision": snap["row"]["revision"] if snap["row"] else None,
                              "settle_rows": len(snap["settle_rows"]),
                              "anomaly_kinds": snap["anomaly_kinds"],
                              "totals": snap["totals"]}
        out["nothing_partial"] = bool(
            snap["row"] and snap["row"]["state"] == "RESERVED"
            and snap["row"]["settled_units"] is None
            and snap["row"]["settlement_source"] is None
            and not snap["settle_rows"]
            and "RECONCILIATION" not in snap["anomaly_kinds"]
            and "SNAPSHOT_REFUSED_PRE_SUBMIT" not in snap["anomaly_kinds"]
            and snap["totals"]["terminal_unsettled_jobs"] == 0)
        # riparazione: la stessa chiusura, senza crash, attraverso l'API del Core
        _core(core_path)
        from registry.reservations import SqliteReservationStore
        store = SqliteReservationStore(db)
        job = store.get(out["job_id"])
        evidence = {"source": PRE_SUBMIT_SOURCE, "remote_ref": "none:never_dispatched",
                    "reason": "retry dopo crash", "attested_by": "runtime_snapshot_guard",
                    "transport_attestation": None}
        store.mark_refused_pre_submit(job, "retry dopo crash", source=PRE_SUBMIT_SOURCE,
                                      evidence=evidence, now=2000.0)
        after = _snapshot(db, core_path, out["job_id"])
        out["after_retry"] = {"state": after["row"]["state"], "settled_units": after["row"]["settled_units"],
                              "settle_rows": len(after["settle_rows"]),
                              "totals": after["totals"]}
        out["retry_succeeds"] = bool(after["row"]["state"] == "FAILED"
                                     and after["row"]["settled_units"] == 0
                                     and len(after["settle_rows"]) == 1
                                     and after["totals"]["terminal_unsettled_jobs"] == 0)
        out["verified"] = bool(out["nothing_partial"] and out["retry_succeeds"])
        out["ok"] = True
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out


def e2e_stale_and_not_applicable(db: str, core_path: str, prompt: str, op: str) -> dict:
    """Dopo una chiusura riuscita:
       a. una seconda chiamata con la vista PRE-rifiuto (revisione obsoleta) e' rifiutata e
          NON produce un secondo settlement;
       b. un job non piu' RESERVED e' rifiutato (`TransitionRefused` + anomalia);
       c. un job con `provider_job_id` persistito e' rifiutato: non e' un pre-submit."""
    out: dict = {"ok": False}
    try:
        _core(core_path)
        from adapters.base import Job, JobState
        from registry.reservations import SqliteReservationStore
        store = SqliteReservationStore(db)
        evidence = {"source": PRE_SUBMIT_SOURCE, "remote_ref": "none:never_dispatched",
                    "reason": "controprova", "attested_by": "runtime_snapshot_guard",
                    "transport_attestation": None}

        # --- a. vista obsoleta su un job gia' chiuso dal percorso runtime ------------------
        row = next((r for r in pb_worker._rows(db) if r["operation_id"] == op), None)
        out["job_id"] = row["job_id"] if row else None
        before = _snapshot(db, core_path, out["job_id"])
        stale = store.get(out["job_id"])
        stale.revision = max(0, stale.revision - 1)          # vista letta PRIMA della chiusura
        stale.state = JobState("RESERVED")
        try:
            store.mark_refused_pre_submit(stale, "doppio", source=PRE_SUBMIT_SOURCE,
                                          evidence=evidence, now=3000.0)
            out["stale_second_call"] = {"refused": False}
        except Exception as e:                                  # noqa: BLE001
            out["stale_second_call"] = {"refused": True, "error": type(e).__name__}
        after = _snapshot(db, core_path, out["job_id"])
        out["no_double_settlement"] = (len(after["settle_rows"]) == len(before["settle_rows"]) == 1)
        out["journal_unchanged"] = before["row"] == after["row"]

        # --- b. job non piu' RESERVED (gia' terminale) -------------------------------------
        try:
            store.mark_refused_pre_submit(store.get(out["job_id"]), "terminale",
                                          source=PRE_SUBMIT_SOURCE, evidence=evidence, now=3100.0)
            out["not_reserved"] = {"refused": False}
        except Exception as e:                                  # noqa: BLE001
            out["not_reserved"] = {"refused": True, "error": type(e).__name__}

        # --- c. job RESERVED ma con identita' remota persistita ----------------------------
        from runtime.authorization import LAB_QUOTE_UNIT
        from runtime.genspec_bridge import build_genspec
        from adapters.base import GenSpec
        # L'envelope e' gia' aperto dal percorso governato: riaprirlo e' idempotente SOLO con
        # id, unita', importo e scope identici. Qualunque scarto e' una reinterpretazione, e il
        # Core la rifiuta (CR-11) — quindi qui si riapre con esattamente i suoi valori.
        store.open_envelope("ENV_LAB", 100, unit=LAB_QUOTE_UNIT, scope=None, now=1.0)
        spec = build_genspec(make_inputs(prompt + " remote"), GenSpec)
        _, live = store.reserve_or_get_live(spec, now=1.0, budget_units=10,
                                            envelope_id="ENV_LAB", operation_id=op + "_remote")
        marked = store.mark_submitting(live, provider="fake", provider_account="fake_acct_a",
                                       payload_digest="a" * 64, attempt_token="att_r", now=2.0)
        pj = Job(job_id=marked.job_id, spec_key=marked.spec_key, provider="fake",
                 state=JobState.SUBMITTED, provider_job_id="pv_remote", submitted_at=3.0,
                 terminal_by=60.0, provider_account="fake_acct_a")
        submitted = store.mark_submitted(marked, pj)
        try:
            store.mark_refused_pre_submit(submitted, "ha identita' remota",
                                          source=PRE_SUBMIT_SOURCE, evidence=evidence, now=3200.0)
            out["provider_job_id_present"] = {"refused": False}
        except Exception as e:                                  # noqa: BLE001
            out["provider_job_id_present"] = {"refused": True, "error": type(e).__name__}
        remote_snap = _snapshot(db, core_path, submitted.job_id)
        out["not_applicable_anomaly"] = "PRE_SUBMIT_REFUSAL_NOT_APPLICABLE" in remote_snap["anomaly_kinds"]
        out["remote_job_untouched"] = (remote_snap["row"]["state"] == "SUBMITTED"
                                       and remote_snap["row"]["settled_units"] is None)

        # --- d. la provenance del trasporto e' vietata su questo percorso -------------------
        try:
            store.mark_refused_pre_submit(store.get(out["job_id"]), "falsa",
                                          source=TRANSPORT_SOURCE,
                                          evidence=dict(evidence, source=TRANSPORT_SOURCE),
                                          now=3300.0)
            out["transport_source_refused"] = {"refused": False}
        except Exception as e:                                  # noqa: BLE001
            out["transport_source_refused"] = {"refused": True, "error": type(e).__name__}

        out["verified"] = bool(
            out["stale_second_call"]["refused"] and out["no_double_settlement"]
            and out["journal_unchanged"] and out["not_reserved"]["refused"]
            and out["provider_job_id_present"]["refused"] and out["not_applicable_anomaly"]
            and out["remote_job_untouched"] and out["transport_source_refused"]["refused"])
        out["ok"] = True
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== NG-03 preservation
def ng03_preservation(core_path: str) -> dict:
    """Il percorso con vera attestazione del trasporto deve restare quello di prima, e il
    runtime non deve poterlo usare per il caso pre-transport."""
    import inspect
    out: dict = {"ok": False}
    try:
        _core(core_path)
        from registry.reservations import SqliteReservationStore
        src = inspect.getsource(SqliteReservationStore.mark_refused_before_send)
        out["transport_path_signature"] = str(
            inspect.signature(SqliteReservationStore.mark_refused_before_send))
        out["transport_path_uses_transport_source"] = TRANSPORT_SOURCE in src
        out["transport_path_unchanged"] = (
            out["transport_path_signature"] == "(self, job: 'Job', reason: 'str', now: 'float') -> 'Job'"
            and out["transport_path_uses_transport_source"])
        # il runtime NON deve chiamare mark_refused_before_send da nessuna parte
        calls: dict = {}
        rt = os.path.join(GATE01, "runtime")
        for name in sorted(os.listdir(rt)):
            if not name.endswith(".py"):
                continue
            tree = ast.parse(open(os.path.join(rt, name), encoding="utf-8").read(), filename=name)
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                            and node.func.attr in ("mark_refused_before_send",
                                                   "mark_refused_pre_submit",
                                                   "reconcile", "settle"):
                        calls.setdefault(node.func.attr, set()).add((name, fn.name))
        out["runtime_call_sites"] = {k: sorted(v) for k, v in sorted(calls.items())}
        out["runtime_never_uses_transport_path"] = "mark_refused_before_send" not in calls
        out["runtime_uses_atomic_api"] = (
            sorted(calls.get("mark_refused_pre_submit", set()))
            == [("go_candidate.py", "_refuse_pre_submit")])
        # Il percorso PRE-SUBMIT non compone piu' due transazioni: `go_candidate` non chiama
        # ne' `reconcile` ne' `settle`.
        go_sites = {s for k in ("reconcile", "settle") for s in calls.get(k, set())
                    if s[0] == "go_candidate.py"}
        out["go_candidate_two_transaction_path_removed"] = not go_sites
        out["go_candidate_residual_sites"] = sorted(go_sites)
        # Gli ALTRI usi di `reconcile`/`settle` nel runtime sono percorsi diversi, dichiarati e
        # fuori dallo scope di questo delta: il report autenticato P-B02 e il reclaim dell'orphan
        # lease (che conserva la propria sequenza conservativa a due transazioni, invariata).
        out["declared_other_sites"] = {
            "reconcile": [("orphan_lease.py", "reclaim_orphan_reserved"),
                          ("reconciliation.py", "reconcile_authenticated")],
            "settle": [("orphan_lease.py", "reclaim_orphan_reserved")]}
        out["other_sites_as_declared"] = (
            sorted(calls.get("reconcile", set())) == out["declared_other_sites"]["reconcile"]
            and sorted(calls.get("settle", set())) == out["declared_other_sites"]["settle"])
        out["orphan_lease_path_unchanged_by_this_delta"] = True
        out["verified"] = bool(out["transport_path_unchanged"]
                               and out["runtime_never_uses_transport_path"]
                               and out["runtime_uses_atomic_api"]
                               and out["go_candidate_two_transaction_path_removed"]
                               and out["other_sites_as_declared"])
        out["ok"] = True
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out


def transport_attested_path(db: str, core_path: str, prompt: str, op: str) -> dict:
    """Controprova positiva: quando l'attestazione del trasporto ESISTE davvero, il Core
    continua a registrare `TRANSPORT_ATTESTED_NOT_SENT`. Quella fonte non e' sparita: e'
    solo confinata al percorso che la produce."""
    out: dict = {"ok": False}
    try:
        from runtime.genspec_bridge import build_genspec
        _core(core_path)
        from adapters.base import GenSpec
        from registry.reservations import SqliteReservationStore
        store = SqliteReservationStore(db)
        store.open_envelope("ENV_LAB", 100, now=1.0)
        spec = build_genspec(make_inputs(prompt), GenSpec)
        _, job = store.reserve_or_get_live(spec, now=1.0, budget_units=10,
                                           envelope_id="ENV_LAB", operation_id=op)
        store.mark_refused_before_send(job, "trasporto attesta: nessun invio", 10.0)
        snap = _snapshot(db, core_path, job.job_id)
        settle = snap["settle_rows"]
        recon = [a for a in snap["anomalies"] if a["kind"] == "RECONCILIATION"]
        out["row"] = snap["row"]
        out["settle_source"] = settle[0]["source"] if settle else None
        out["evidence_source"] = recon[-1]["detail"]["evidence"]["source"] if recon else None
        out["verified"] = bool(snap["row"]["state"] == "FAILED"
                               and snap["row"]["settled_units"] == 0
                               and snap["row"]["settlement_source"] == TRANSPORT_SOURCE
                               and len(settle) == 1 and settle[0]["source"] == TRANSPORT_SOURCE
                               and out["evidence_source"] == TRANSPORT_SOURCE)
        out["ok"] = True
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== SUBMIT_UNKNOWN
def submit_unknown_behaviour(db: str, core_path: str, prompt: str, op: str) -> dict:
    """Invio incerto: resta SUBMIT_UNKNOWN, nessun settlement zero, nessun blind retry.
    L'API atomica non deve toccarlo: un invio che puo' essere avvenuto non e' gratis."""
    out: dict = {"ok": False}
    try:
        go = pb_worker.go_governed(db, core_path, prompt, op, adapter_kind="submit_unknown")
        row = next((r for r in pb_worker._rows(db) if r["operation_id"] == op), None)
        out["job_id"] = row["job_id"] if row else None
        snap = _snapshot(db, core_path, out["job_id"])
        out["state"] = snap["row"]["state"] if snap["row"] else None
        out["settled_units"] = snap["row"]["settled_units"] if snap["row"] else None
        out["settle_rows"] = len(snap["settle_rows"])
        out["submits_after_first"] = go.get("submits")
        # RESUME: nessun nuovo submit, nessuna nuova reservation
        resume = pb_worker.resume_only(db, core_path, prompt, op)
        out["resume"] = {k: resume.get(k) for k in ("ok", "outcome", "state", "submits", "resumed")}
        after = _snapshot(db, core_path, out["job_id"])
        out["rows_for_operation"] = [r["job_id"] for r in after["rows"] if r["operation_id"] == op]
        # l'API atomica deve rifiutare un job non RESERVED
        _core(core_path)
        from registry.reservations import SqliteReservationStore
        store = SqliteReservationStore(db)
        try:
            store.mark_refused_pre_submit(store.get(out["job_id"]), "non lecito",
                                          source=PRE_SUBMIT_SOURCE,
                                          evidence={"source": PRE_SUBMIT_SOURCE,
                                                    "remote_ref": "none:never_dispatched"},
                                          now=4000.0)
            out["atomic_api_on_submit_unknown"] = {"refused": False}
        except Exception as e:                                  # noqa: BLE001
            out["atomic_api_on_submit_unknown"] = {"refused": True, "error": type(e).__name__}
        final = _snapshot(db, core_path, out["job_id"])
        out["verified"] = bool(
            out["state"] == "SUBMIT_UNKNOWN"
            and out["settled_units"] is None and out["settle_rows"] == 0
            and resume.get("state") == "SUBMIT_UNKNOWN"
            and resume.get("submits") in (0, None)
            and len(out["rows_for_operation"]) == 1
            and out["atomic_api_on_submit_unknown"]["refused"]
            and final["row"]["state"] == "SUBMIT_UNKNOWN"
            and final["row"]["settled_units"] is None)
        out["ok"] = True
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out


# ===================================================================== pin fail-closed
def pin_matrix(core_candidate: str, core_baseline: str) -> dict:
    """Il pin deve fallire CHIUSO su: baseline vecchio, SHA sbagliato, candidate sporco,
    candidate non disponibile. E passare SOLO sul candidate pulito."""
    import shutil
    import tempfile
    out: dict = {"ok": False}
    try:
        from runtime.core_pin import (REQUIRED_CORE_SHA, CorePinError, require_core_verdict,
                                      verify_core_pin)
        cases: dict = {}

        def probe(label, path):
            try:
                v = require_core_verdict(path)
                cases[label] = {"code": v.code, "observed": v.observed}
            except CorePinError as e:
                cases[label] = {"code": e.code, "observed": e.observed, "dirty": list(e.dirty)}

        probe("candidate_clean", core_candidate)
        probe("old_baseline", core_baseline)
        probe("missing_path", os.path.join(tempfile.gettempdir(), "no_such_core_dir"))
        # candidate sporco: file non tracciato dentro il checkout, poi rimosso
        canary = os.path.join(core_candidate, "__pin_probe_untracked__.txt")
        with open(canary, "w", encoding="utf-8") as fh:
            fh.write("probe\n")
        try:
            probe("candidate_dirty", core_candidate)
        finally:
            os.remove(canary)
        probe("candidate_clean_again", core_candidate)
        # SHA sbagliato, funzione pura
        cases["wrong_sha_pure"] = {"code": verify_core_pin("0" * 40).code, "observed": "0" * 40}
        out["required_core_sha"] = REQUIRED_CORE_SHA
        out["cases"] = cases
        expected = {"candidate_clean": "CORE_PIN_OK", "old_baseline": "STALE_CORE_PIN",
                    "missing_path": "CORE_PIN_MISMATCH", "candidate_dirty": "CORE_WORKTREE_DIRTY",
                    "candidate_clean_again": "CORE_PIN_OK", "wrong_sha_pure": "CORE_PIN_MISMATCH"}
        out["expected"] = expected
        out["mismatches"] = {k: {"got": cases[k]["code"], "expected": v}
                             for k, v in expected.items() if cases[k]["code"] != v}
        out["verified"] = (not out["mismatches"] and REQUIRED_CORE_SHA == out["cases"]
                           ["candidate_clean"]["observed"])
        out["ok"] = True
        del shutil
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out


def go_against_old_core(db: str, core_path_old: str, prompt: str, op: str) -> dict:
    """`go()` contro la baseline vecchia deve fermarsi PRIMA di importare il Core: il
    runtime pretende un'API che quel Core non ha, e lo dice invece di scoprirlo a meta'."""
    out: dict = {"ok": False}
    try:
        from runtime import go_candidate
        from runtime.core_pin import CorePinError
        out["core_imported_before"] = "registry.reservations" in sys.modules
        try:
            go_candidate.go(make_inputs(prompt), adapter=None, provider_mode="fake",
                            store_path=db, core_path=core_path_old, operation_id=op,
                            authorization=None)
            out["refused"] = False
        except CorePinError as e:
            out["refused"] = True
            out["code"] = e.code
            out["observed"] = e.observed
        out["store_created"] = os.path.exists(db)
        out["verified"] = bool(out["refused"] and out["code"] == "STALE_CORE_PIN"
                               and not out["store_created"])
        out["ok"] = True
    except Exception as e:                                      # noqa: BLE001
        out.update(_err(e))
    return out
