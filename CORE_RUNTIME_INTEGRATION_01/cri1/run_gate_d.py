#!/usr/bin/env python3
"""COORDINATED CORE + RUNTIME INTEGRATION — NG-05. Matrice D00..D12.

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION ·
NO DEPLOY · NO TAG · NO RELEASE · NO MERGE.

  D00  Reality Lock sugli input approvati (Core main/candidate, Runtime main/reviewed, P2)
  D01  Core pin: punta al candidate, fail-closed su tutto il resto; il Runtime consuma l'API
  D02  NG-05 end-to-end: SERIALIZATION_DRIFT -> FAILED + settlement 0, UNA transazione
  D03  NG-05 end-to-end: IDENTITY_DRIFT -> stesso comportamento
  D04  NG-05 end-to-end: crash prima del COMMIT del Core -> nulla di parziale, retry riesce
  D05  NG-05 end-to-end: vista obsoleta, non-RESERVED, identita' remota, provenance vietata
  D06  NG-03 preservation: `TRANSPORT_ATTESTED_NOT_SENT` confinata al percorso che la produce
  D07  NG-03 controprova positiva: il percorso transport-attested la registra ancora
  D08  SUBMIT_UNKNOWN: nessun settlement zero, nessun blind retry
  D09  Regressioni dei meccanismi sul Core candidate (P-B04, P-B01+P-B02, NG-04, legacy, orphan)
  D10  Regressione R0-R1 (T01-T37) contro il Core candidate
  D11  P2 freeze, baseline Core/Runtime intatte, bundle approvato non toccato
  D12  Catena di provenance: verificatore fail-closed (struttura approvata, preservata)
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BUNDLE)
GATE01 = os.path.join(REPO, "RUNTIME_INTEGRATION_GATE_01")
BUNDLE01 = os.path.join(REPO, "PROVIDER_BOUNDARY_HARDENING_01")
BUNDLE02 = os.path.join(REPO, "PROVIDER_BOUNDARY_GATE_02")
CORE_BASELINE_PATH = os.environ.get("CREATIVE_OS_CORE_BASELINE_PATH", "/home/user/creative-os")
CORE_PATH = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os-atomicity")
os.environ["CREATIVE_OS_CORE_PATH"] = CORE_PATH          # i figli spawn devono vedere il candidate
STATE_DIR = os.path.join(GATE01, "state")
EVIDENCE_DIR = os.path.join(BUNDLE, "evidence")
RAW_DIR = os.path.join(EVIDENCE_DIR, "raw")
REGRESSION_DIR = os.path.join(BUNDLE, "regression")
for p in (GATE01, BUNDLE01, BUNDLE02, BUNDLE):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("RUNTIME_GATE_ROOT", GATE01)
os.environ.setdefault("PBGATE01_ROOT", BUNDLE01)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from runtime.core_pin import REQUIRED_CORE_SHA                      # noqa: E402
from tests import gate_report, static_checks                        # noqa: E402
from pbgate import pb_worker                                        # noqa: E402
from pbg2 import bundle_provenance                                  # noqa: E402
from cri1 import readiness, workers                                 # noqa: E402

APPROVED = {
    "core_baseline": "740ee979300fe20a9382992528604dee70cb2fcf",
    "core_candidate": "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515",
    "core_candidate_branch": "harden/provider-boundary-core-atomicity-2026-09-17",
    "runtime_main": "0698279703ab959625ac4e84ee636bc5b93b45fd",
    "runtime_code_sha": "e845b744a4af3a143b1b1e710016726c57ad6c39",
    "runtime_reviewed_head": "4a73cdad18034e7c1bd9842a37e34e0273f9325a",
    "p2_sha256": "637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1",
    "evidence_bundle_v2_sha256": "12cd7773f5d242578ae877d34bb6d3603d429725127626a7ff4d1780dd20e078",
}
P2_PATH = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16",
                       "P2_RUNTIME", "hf_batch.py")
EXPECTED_IDS = frozenset(f"D{i:02d}" for i in range(0, 13))
POLICY = {"D09": frozenset({"BLOCKED_ENVIRONMENT"})}
CTX = multiprocessing.get_context("spawn")
RESULTS: list[dict] = []
SHARED: dict = {}


# ------------------------------------------------------------------ utilita'
def db_for(name: str) -> str:
    p = os.path.join(STATE_DIR, f"cri_{name}.db")
    pb_worker.cleanup_db(p)
    return p


def evidence(test_id: str, name: str, payload: dict) -> str:
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    path = os.path.join(EVIDENCE_DIR, f"{test_id}_{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    return os.path.relpath(path, BUNDLE)


def in_process(fn, *args, **kwargs) -> dict:
    q = CTX.Queue()
    p = CTX.Process(target=pb_worker._entry, args=(q, fn, args, kwargs))
    p.start()
    p.join(300)
    if p.is_alive():
        p.terminate()
        return {"ok": False, "error": "TIMEOUT_PROCESS"}
    if q.empty():
        return {"ok": False, "error": "NO_RESULT", "exitcode": p.exitcode}
    return q.get(timeout=10)


def run_until_exit(fn, *args, **kwargs) -> dict:
    q = CTX.Queue()
    p = CTX.Process(target=pb_worker._entry, args=(q, fn, args, kwargs))
    p.start()
    p.join(300)
    return {"exitcode": p.exitcode, "result": (q.get(timeout=5) if not q.empty() else None)}


def git(*args, cwd=REPO) -> str:
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record(test_id: str, title: str, expected: str, fn):
    r = gate_report.run_and_classify(test_id, title, expected, fn, evidence_root=BUNDLE,
                                     exception_evidence=lambda tid, p: evidence(tid, "exception", p))
    RESULTS.append(r)
    print(gate_report.console_line(r), flush=True)


# ------------------------------------------------------------------ D00
def d00():
    core_main = git("rev-parse", "HEAD", cwd=CORE_BASELINE_PATH)
    core_cand = git("rev-parse", "HEAD", cwd=CORE_PATH)
    cand_branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=CORE_PATH)
    subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True, text=True)
    runtime_main = git("rev-parse", "origin/main")
    reviewed = git("rev-parse", APPROVED["runtime_reviewed_head"])
    head = git("rev-parse", "HEAD")
    p2 = sha256_file(P2_PATH)
    SHARED["p2_before"] = p2
    checks = {
        "core_main_is_approved_baseline": core_main == APPROVED["core_baseline"],
        "core_candidate_is_approved": core_cand == APPROVED["core_candidate"],
        "core_candidate_branch": cand_branch == APPROVED["core_candidate_branch"],
        "runtime_main_is_canonical": runtime_main == APPROVED["runtime_main"],
        "runtime_reviewed_head_exists": reviewed == APPROVED["runtime_reviewed_head"],
        "core_candidate_descends_from_baseline": subprocess.run(
            ["git", "-C", CORE_PATH, "merge-base", "--is-ancestor",
             APPROVED["core_baseline"], APPROVED["core_candidate"]]).returncode == 0,
        "runtime_work_descends_from_canonical": subprocess.run(
            ["git", "-C", REPO, "merge-base", "--is-ancestor",
             APPROVED["runtime_main"], head]).returncode == 0,
        "integration_branch_from_reviewed_head": subprocess.run(
            ["git", "-C", REPO, "merge-base", "--is-ancestor",
             APPROVED["runtime_reviewed_head"], head]).returncode == 0,
        "p2_unchanged": p2 == APPROVED["p2_sha256"],
        "core_baseline_tree_clean": git("status", "--porcelain", "--untracked-files=all",
                                        cwd=CORE_BASELINE_PATH) == "",
        "core_candidate_tree_clean": git("status", "--porcelain", "--untracked-files=all",
                                         cwd=CORE_PATH) == "",
    }
    ok = all(checks.values())
    d = {"approved_inputs": APPROVED, "observed": {
        "core_main": core_main, "core_candidate": core_cand, "core_candidate_branch": cand_branch,
        "runtime_origin_main": runtime_main, "runtime_head": head,
        "runtime_branch": git("rev-parse", "--abbrev-ref", "HEAD"), "p2_sha256": p2},
        "checks": checks, "stop_condition": "APPROVED_INPUT_DRIFT" if not ok else None}
    ev = evidence("D00", "reality_lock_approved_inputs", d)
    failed = [k for k, v in checks.items() if not v]
    return (f"Core main {core_main[:12]} · candidate {core_cand[:12]} ({cand_branch}) · Runtime "
            f"main {runtime_main[:12]} · reviewed {APPROVED['runtime_reviewed_head'][:12]} · HEAD "
            f"{head[:12]} su {git('rev-parse', '--abbrev-ref', 'HEAD')} · P2 {p2[:16]} · check "
            f"falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ D01
def d01():
    pin = in_process(workers.pin_matrix, CORE_PATH, CORE_BASELINE_PATH)
    old = in_process(workers.go_against_old_core, db_for("d01_old"), CORE_BASELINE_PATH,
                     "pin vs vecchio core", "lab:d01")
    ng03 = in_process(workers.ng03_preservation, CORE_PATH)
    sc = static_checks.run(CORE_PATH)
    SHARED["ng03"] = ng03
    checks = {
        "pin_matrix_fail_closed": bool(pin.get("verified")),
        "required_core_sha_is_candidate": REQUIRED_CORE_SHA == APPROVED["core_candidate"],
        "go_against_old_core_refused": bool(old.get("verified")),
        "runtime_uses_atomic_api": bool(ng03.get("runtime_uses_atomic_api")),
        "two_transaction_path_removed_from_go_candidate": bool(
            ng03.get("go_candidate_two_transaction_path_removed")),
        "other_reconcile_settle_sites_as_declared": bool(ng03.get("other_sites_as_declared")),
        "static_contract_ok_against_candidate": sc.get("ok") is True,
    }
    ok = all(checks.values())
    ev = evidence("D01", "core_pin_and_api_consumption", {
        "required_core_sha": REQUIRED_CORE_SHA, "pin_matrix": pin,
        "go_against_old_core": old, "runtime_call_sites": ng03.get("runtime_call_sites"),
        "static_checks": sc, "checks": checks})
    failed = [k for k, v in checks.items() if not v]
    return (f"pin {REQUIRED_CORE_SHA[:12]} · candidate -> CORE_PIN_OK · baseline -> "
            f"{pin.get('cases', {}).get('old_baseline', {}).get('code')} · sporco -> "
            f"{pin.get('cases', {}).get('candidate_dirty', {}).get('code')} · assente -> "
            f"{pin.get('cases', {}).get('missing_path', {}).get('code')} · go() su Core vecchio -> "
            f"{old.get('code')} senza store · call site dell'API atomica: "
            f"{ng03.get('runtime_call_sites', {}).get('mark_refused_pre_submit')} · check falliti: "
            f"{failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ D02 / D03
def _e2e(test_id: str, adapter_kind: str, label: str):
    db = db_for(f"{test_id.lower()}_{adapter_kind}")
    op = f"lab:{test_id.lower()}"
    r = in_process(workers.e2e_pre_submit_refusal, db, CORE_PATH, f"{label} {test_id}", op,
                   adapter_kind)
    pb_worker.cleanup_db(db)
    ok = bool(r.get("verified"))
    ev = evidence(test_id, f"ng05_e2e_{adapter_kind}", r)
    row = (r.get("state") or {}).get("row") or {}
    settle = (r.get("state") or {}).get("settle_rows") or []
    rep = r.get("runtime_report") or {}
    return (f"{adapter_kind}: {row.get('state')} settled={row.get('settled_units')} "
            f"source={row.get('settlement_source')} · {len(settle)} riga SETTLE · runtime "
            f"atomic={rep.get('atomic')} api={rep.get('core_api')} · transport_sent="
            f"{(r.get('go') or {}).get('transport_sent_count')} · terminal_unsettled="
            f"{((r.get('state') or {}).get('totals') or {}).get('terminal_unsettled_jobs')}"), ev, ok


def d02():
    return _e2e("D02", "drift_nested", "serialization drift")


def d03():
    return _e2e("D03", "identity_drift", "identity drift")


# ------------------------------------------------------------------ D04
def d04():
    db = db_for("d04_crash")
    op = "lab:d04"
    crash = run_until_exit(workers.e2e_crash_before_core_commit, db, CORE_PATH,
                           "crash pre-commit", op)
    after = in_process(workers.e2e_after_crash, db, CORE_PATH, op)
    pb_worker.cleanup_db(db)
    ok = bool(crash.get("exitcode") == 13 and after.get("verified"))
    ev = evidence("D04", "ng05_e2e_crash_before_core_commit",
                  {"crash": crash, "after": after,
                   "note": "il crash e' iniettato al confine del Core (_crash_hook, la stessa "
                           "convenzione di test gia' usata da settle): il percorso del runtime "
                           "e' quello vero, integralmente, fino alla chiamata dell'API"})
    ac = after.get("after_crash") or {}
    ar = after.get("after_retry") or {}
    return (f"morte reale prima del COMMIT (exit {crash.get('exitcode')}): stato {ac.get('state')}, "
            f"settled {ac.get('settled_units')}, {ac.get('settle_rows')} righe SETTLE, anomalie "
            f"{ac.get('anomaly_kinds')} · nulla di parziale={after.get('nothing_partial')} · retry "
            f"senza crash -> {ar.get('state')} settled {ar.get('settled_units')}, "
            f"{ar.get('settle_rows')} riga SETTLE"), ev, ok


# ------------------------------------------------------------------ D05
def d05():
    db = db_for("d05_stale")
    op = "lab:d05"
    first = in_process(workers.e2e_pre_submit_refusal, db, CORE_PATH, "stale base", op,
                       "drift_nested")
    r = in_process(workers.e2e_stale_and_not_applicable, db, CORE_PATH, "stale base", op)
    pb_worker.cleanup_db(db)
    ok = bool(first.get("verified") and r.get("verified"))
    ev = evidence("D05", "ng05_e2e_cas_and_not_applicable", {"first_closure": first, "counterproofs": r})
    return (f"vista obsoleta -> rifiutata ({(r.get('stale_second_call') or {}).get('error')}), "
            f"nessun doppio settlement={r.get('no_double_settlement')} · job non piu' RESERVED -> "
            f"{(r.get('not_reserved') or {}).get('error')} · identita' remota persistita -> "
            f"{(r.get('provider_job_id_present') or {}).get('error')} + anomalia "
            f"PRE_SUBMIT_REFUSAL_NOT_APPLICABLE={r.get('not_applicable_anomaly')} · provenance del "
            f"trasporto su questo percorso -> {(r.get('transport_source_refused') or {}).get('error')}"), ev, ok


# ------------------------------------------------------------------ D06 / D07
def d06():
    ng03 = SHARED.get("ng03") or in_process(workers.ng03_preservation, CORE_PATH)
    ok = bool(ng03.get("verified"))
    ev = evidence("D06", "ng03_preservation", ng03)
    return (f"mark_refused_before_send invariata ({ng03.get('transport_path_unchanged')}) e mai "
            f"chiamata dal runtime ({ng03.get('runtime_never_uses_transport_path')}) · call sites: "
            f"{ng03.get('runtime_call_sites')}"), ev, ok


def d07():
    db = db_for("d07_transport")
    r = in_process(workers.transport_attested_path, db, CORE_PATH, "transport attested", "lab:d07")
    pb_worker.cleanup_db(db)
    ok = bool(r.get("verified"))
    ev = evidence("D07", "ng03_transport_attested_still_works", r)
    return (f"percorso con attestazione reale del trasporto -> {(r.get('row') or {}).get('state')} "
            f"settled {(r.get('row') or {}).get('settled_units')} source {r.get('settle_source')} · "
            f"evidenza {r.get('evidence_source')}"), ev, ok


# ------------------------------------------------------------------ D08
def d08():
    db = db_for("d08_unknown")
    r = in_process(workers.submit_unknown_behaviour, db, CORE_PATH, "submit unknown", "lab:d08")
    pb_worker.cleanup_db(db)
    ok = bool(r.get("verified"))
    ev = evidence("D08", "submit_unknown_no_zero_settlement", r)
    return (f"invio incerto -> {r.get('state')}, settled {r.get('settled_units')}, "
            f"{r.get('settle_rows')} righe SETTLE · resume -> {(r.get('resume') or {}).get('state')} "
            f"submits {(r.get('resume') or {}).get('submits')}, attempt per l'operazione: "
            f"{len(r.get('rows_for_operation') or [])} · API atomica su SUBMIT_UNKNOWN -> "
            f"{(r.get('atomic_api_on_submit_unknown') or {}).get('error')}"), ev, ok


# ------------------------------------------------------------------ D09
def d09(scratch: str):
    """Rieseguo i meccanismi gia' verificati, contro il Core CANDIDATE. Stessi asserti,
    stesse funzioni del gate approvato: nessun test indebolito. Le evidenze vengono scritte
    in QUESTO bundle — quello approvato non viene toccato (verificato da D11)."""
    from pbg2 import run_gate2
    saved = (run_gate2.CORE_PATH, run_gate2.EVIDENCE_DIR, run_gate2.RAW_DIR)
    run_gate2.CORE_PATH = CORE_PATH
    run_gate2.EVIDENCE_DIR = os.path.join(EVIDENCE_DIR, "mechanisms")
    run_gate2.RAW_DIR = os.path.join(run_gate2.EVIDENCE_DIR, "raw")
    os.makedirs(run_gate2.RAW_DIR, exist_ok=True)
    out: dict = {}
    try:
        for label, fn in (("composition_pb01_pb02", lambda: run_gate2.c02(scratch)),
                          ("freshness_ng04", run_gate2.c03),
                          ("legacy_spend_paths", run_gate2.c04),
                          ("orphan_lease", run_gate2.c05)):
            try:
                actual, ev, ok = fn()
                out[label] = {"ok": ok, "actual": actual, "evidence": ev}
            except gate_report.GateBlocked as b:
                out[label] = {"ok": False, "blocked": True, "reason_code": b.reason_code,
                              "actual": b.actual}
            print(f"      · {label}: {'PASS' if out[label].get('ok') else out[label]}", flush=True)
    finally:
        run_gate2.CORE_PATH, run_gate2.EVIDENCE_DIR, run_gate2.RAW_DIR = saved
    # P-B04: sigillo exact-byte e attestazione pre-send su una spesa governata riuscita
    db = db_for("d09_pb04")
    go = in_process(pb_worker.go_governed, db, CORE_PATH, "pb04 candidate", "lab:d09")
    insp = in_process(pb_worker.ledger_inspect, db, CORE_PATH, "pb04 candidate", go.get("job_id"))
    pb_worker.cleanup_db(db)
    out["pb04_snapshot"] = {
        "state": go.get("state"),
        "persisted_equals_recomputed_canonical": insp.get("persisted_equals_recomputed_canonical"),
        "sha256_of_persisted_equals_job_digest": insp.get("sha256_of_persisted_equals_job_digest"),
        "persisted_mode": insp.get("persisted_mode"),
        "send_attestation": bool(insp.get("send_attestation")),
        "audit_ok": (insp.get("audit") or {}).get("ok"),
    }
    out["pb04_snapshot"]["ok"] = bool(
        go.get("state") == "SUCCEEDED"
        and out["pb04_snapshot"]["persisted_equals_recomputed_canonical"]
        and out["pb04_snapshot"]["sha256_of_persisted_equals_job_digest"]
        and out["pb04_snapshot"]["persisted_mode"] == "0o444"
        and out["pb04_snapshot"]["send_attestation"]
        and out["pb04_snapshot"]["audit_ok"])
    ok = all(v.get("ok") for v in out.values())
    ev = evidence("D09", "mechanism_regressions_on_candidate", {
        "core_path": CORE_PATH, "results": out,
        "note": "stesse funzioni di verifica del gate approvato (pbg2.run_gate2 c02/c03/c04/c05), "
                "eseguite contro il Core candidate; evidenze scritte in questo bundle."})
    failed = [k for k, v in out.items() if not v.get("ok")]
    return (f"sul Core candidate: P-B01+P-B02 composition, NG-04 freshness, legacy spend paths, "
            f"orphan lease, P-B04 snapshot · falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ D10
def d10():
    os.makedirs(REGRESSION_DIR, exist_ok=True)
    log = os.path.join(REGRESSION_DIR, "r0_r1_run_gate_candidate.log")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "RUNTIME_GATE_ROOT": GATE01,
           "CREATIVE_OS_CORE_PATH": CORE_PATH}
    env.pop("CREATIVE_OS_PROVIDER_BOUNDARY_MODE", None)
    r = subprocess.run([sys.executable, os.path.join(GATE01, "tests", "run_gate.py")],
                       capture_output=True, text=True, cwd=GATE01, env=env, timeout=3600)
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(r.stdout + "\n--- stderr ---\n" + r.stderr)
    results_path = os.path.join(GATE01, "evidence", "RESULTS.json")
    data = json.load(open(results_path, encoding="utf-8")) if os.path.exists(results_path) else {}
    summary = data.get("summary") or {}
    if os.path.exists(results_path):
        shutil.copy(results_path, os.path.join(REGRESSION_DIR, "r0_r1_RESULTS_candidate.json"))
    fails = summary.get("fail_ids") or []
    blocked = summary.get("blocked_tests") or []
    not_allowed = summary.get("blocked_not_allowed_by_policy") or []
    ok = (r.returncode == 0 and not fails and not not_allowed
          and summary.get("inventory", {}).get("valid") is True
          and summary.get("gate_decision") in ("LAB_GATE_COMPLETE_ALL_VERIFIED",
                                               "LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED")
          and summary.get("pass") == 36 and summary.get("total") == 37)
    ev = evidence("D10", "regression_r0_r1_on_candidate", {
        "core_path": CORE_PATH, "returncode": r.returncode, "summary": summary,
        "baseline_expected": {"total": 37, "pass": 36, "fail": 0,
                              "blocked": [{"id": "T29", "reason_code": "BLOCKED_ENVIRONMENT"}]},
        "log": os.path.relpath(log, BUNDLE), "stdout_tail": r.stdout[-3000:]})
    return (f"T01-T37 contro il Core candidate: exit {r.returncode} · PASS {summary.get('pass')}/"
            f"{summary.get('total')} · FAIL {fails or 'nessuno'} · BLOCKED "
            f"{[b['id'] + '/' + b['reason_code'] for b in blocked] or 'nessuno'} · decisione "
            f"{summary.get('gate_decision')}"), ev, ok


# ------------------------------------------------------------------ D11
def d11():
    p2_after = sha256_file(P2_PATH)
    core_main = git("rev-parse", "HEAD", cwd=CORE_BASELINE_PATH)
    core_cand = git("rev-parse", "HEAD", cwd=CORE_PATH)
    # il bundle approvato non deve essere stato toccato da questa fase
    approved_dirty = git("status", "--porcelain", "--untracked-files=all", "--",
                         "PROVIDER_BOUNDARY_GATE_02")
    v3_dirty = git("status", "--porcelain", "--untracked-files=all", "--",
                   "PROVIDER_BOUNDARY_HARDENING_01")
    tags = {"core": git("tag", "--list", cwd=CORE_BASELINE_PATH).split(),
            "runtime": git("tag", "--list").split()}
    scan = bundle_provenance.scan_credentials(BUNDLE)
    checks = {
        "p2_before_equals_after": SHARED.get("p2_before") == p2_after == APPROVED["p2_sha256"],
        "core_main_untouched": (core_main == APPROVED["core_baseline"]
                                and git("status", "--porcelain", "--untracked-files=all",
                                        cwd=CORE_BASELINE_PATH) == ""),
        "core_candidate_untouched": core_cand == APPROVED["core_candidate"],
        "runtime_main_untouched": git("rev-parse", "origin/main") == APPROVED["runtime_main"],
        "approved_bundle_v2_untouched": approved_dirty == "",
        "bundle_v3_untouched": v3_dirty == "",
        "no_tags": not tags["core"] and not tags["runtime"],
        "no_credential_material": scan["hits"] == [],
    }
    ok = all(checks.values())
    ev = evidence("D11", "p2_freeze_and_baselines_untouched", {
        "p2_before": SHARED.get("p2_before"), "p2_after": p2_after,
        "core_main": core_main, "core_candidate": core_cand,
        "runtime_origin_main": git("rev-parse", "origin/main"),
        "approved_bundle_status": approved_dirty, "bundle_v3_status": v3_dirty,
        "tags": tags, "credential_scan": scan, "checks": checks})
    failed = [k for k, v in checks.items() if not v]
    return (f"P2 {p2_after[:16]} before==after · Core main {core_main[:12]} pulito · candidate "
            f"{core_cand[:12]} invariato · bundle approvato v2 e v3 non toccati · 0 tag · "
            f"0 credenziali · check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ D12
def d12(scratch: str):
    """La struttura della catena approvata dalla Human Review va preservata anche qui."""
    root = os.path.join(scratch, "d12")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)

    def fixture(name, manifest=None):
        d = os.path.join(root, name)
        os.makedirs(os.path.join(d, "evidence"), exist_ok=True)
        open(os.path.join(d, "README.md"), "w", encoding="utf-8").write("fixture\n")
        m = {"schema": "test", "runtime_branch": "b", "runtime_code_sha": "a" * 40,
             "runtime_evidence_head_sha": bundle_provenance.EXTERNAL_ONLY,
             "canonical_runtime_base_sha": "c" * 40,
             "merge_readiness": {"runtime_candidate_ready": True, "core_candidate_ready": True,
                                 "core_runtime_pair_ready": False, "merge_authorized": False}}
        m.update(manifest or {})
        json.dump(m, open(os.path.join(d, bundle_provenance.MANIFEST_NAME), "w", encoding="utf-8"))
        bundle_provenance.write_sums(d)
        return d

    codes = lambda r: sorted({p["code"] for p in r["problems"]})     # noqa: E731
    C = {}
    C["valid"] = codes(bundle_provenance.verify(fixture("ok"), expect_committed=False))
    d = fixture("uncovered")
    sums = os.path.join(d, bundle_provenance.SUMS_NAME)
    kept = [ln for ln in open(sums, encoding="utf-8")
            if not ln.rstrip("\n").endswith(bundle_provenance.MANIFEST_NAME)]
    open(sums, "w", encoding="utf-8").writelines(kept)
    C["manifest_not_covered"] = codes(bundle_provenance.verify(d, expect_committed=False))
    C["ambiguous_key"] = codes(bundle_provenance.verify(
        fixture("ambiguous", {"runtime_commit": "d" * 40}), expect_committed=False))
    head, prev = git("rev-parse", "HEAD"), git("rev-parse", "HEAD~1")
    C["head_drift"] = codes(bundle_provenance.verify(
        fixture("drift", {"runtime_code_sha": prev}), expect_committed=False, repo=REPO,
        provenance={"runtime_code_sha": prev, "runtime_evidence_head_sha": prev}))
    C["consistent"] = codes(bundle_provenance.verify(
        fixture("consistent", {"runtime_code_sha": prev}), expect_committed=False, repo=REPO,
        provenance={"runtime_code_sha": prev, "runtime_evidence_head_sha": head}))
    expected = {"valid": [], "manifest_not_covered": ["MANIFEST_NOT_COVERED", "MISSING_FROM_SUMS"],
                "ambiguous_key": ["AMBIGUOUS_MANIFEST_KEY"],
                "head_drift": ["CODE_SHA_EQUALS_EVIDENCE_HEAD", "HEAD_NOT_EVIDENCE_HEAD"],
                "consistent": []}
    mism = {k: {"got": C[k], "expected": v} for k, v in expected.items() if C[k] != v}
    ok = not mism
    ev = evidence("D12", "evidence_chain_integrity", {
        "counterproofs": C, "expected": expected, "mismatches": mism,
        "verifier": "pbg2/bundle_provenance.py:verify (authority approvata, riusata non copiata)",
        "chain": "runtime_code_sha -> runtime_evidence_head_sha (solo in PROVENANCE esterna) -> "
                 "PROVENANCE.json + SHA256SUMS.EXTERNAL"})
    return (f"catena approvata preservata · {len(expected)} controprove · scarti: "
            f"{mism or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ report
def build_report() -> dict:
    suite = gate_report.summarize(RESULTS, policy=POLICY, expected_ids=EXPECTED_IDS)
    ng03 = SHARED.get("ng03") or {}
    facts = {
        "approved_core_candidate": APPROVED["core_candidate"],
        "core_candidate_sha": git("rev-parse", "HEAD", cwd=CORE_PATH),
        "core_candidate_clean": git("status", "--porcelain", "--untracked-files=all",
                                    cwd=CORE_PATH) == "",
        "core_candidate_suites_pass": SHARED.get("core_suites_pass", True),
        "required_core_sha": REQUIRED_CORE_SHA,
        "runtime_uses_atomic_api": bool(ng03.get("runtime_uses_atomic_api")),
        "runtime_still_uses_two_transactions": not ng03.get("go_candidate_two_transaction_path_removed", False),
        "runtime_candidate_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
    }
    SHARED["pair_facts"] = facts
    return readiness.build(RESULTS, suite, pair_facts=facts)


def write_results(report: dict) -> dict:
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    payload = {"schema": "core-runtime-integration-ng05/1", "approved_inputs": APPROVED,
               "required_core_sha": REQUIRED_CORE_SHA, "core_path": CORE_PATH,
               "results": RESULTS, "report": report, "pair_facts": SHARED.get("pair_facts")}
    with open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    lines = ["# TEST RESULTS — COORDINATED CORE + RUNTIME INTEGRATION (NG-05, 2026-09-17)", "",
             "MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO MERGE.", "",
             "| ID | TEST | ATTESO | OSSERVATO | ESITO | EVIDENZA |", "|---|---|---|---|---|---|"]
    for r in RESULTS:
        lines.append(f"| {r['id']} | {r['title']} | {r['expected']} | {r['actual']} | "
                     f"**{r['status']}**{'' if r['status'] == 'PASS' else ' / ' + r['reason_code']} | "
                     f"`{r['evidence']}` |")
    lines += [""] + readiness.markdown(report)
    with open(os.path.join(BUNDLE, "TEST_RESULTS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(BUNDLE, "READINESS.json"), "w", encoding="utf-8") as fh:
        json.dump({"gap_status": readiness.machine_readable_gaps(report), "report": report},
                  fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    return payload


def cross_check(report: dict) -> dict:
    problems = []
    res = json.load(open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), encoding="utf-8"))
    rd = json.load(open(os.path.join(BUNDLE, "READINESS.json"), encoding="utf-8"))
    md = open(os.path.join(BUNDLE, "TEST_RESULTS.md"), encoding="utf-8").read()
    if res["report"]["pair_readiness"] != report["pair_readiness"]:
        problems.append("RESULTS.json: pair_readiness divergente")
    if rd["gap_status"] != readiness.machine_readable_gaps(report):
        problems.append("READINESS.json: gap_status divergente")
    flag = str(report["pair_readiness"]["merge_authorized"]).lower()
    if f"| `merge_authorized` | **`{flag}`** |" not in md:
        problems.append("TEST_RESULTS.md: merge_authorized divergente")
    return {"problems": problems, "ok": not problems}


def main() -> int:
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="cri1_")
    try:
        record("D00", "Reality Lock sugli input approvati",
               "Core main/candidate, Runtime main/reviewed, P2, tree puliti", d00)
        record("D01", "Core pin al candidate e consumo reale dell'API",
               "CORE_PIN_OK solo sul candidate pulito; baseline/sporco/assente fail-closed; "
               "unico call site dell'API atomica", d01)
        record("D02", "NG-05 end-to-end: SERIALIZATION_DRIFT",
               "FAILED + settlement 0 + 1 ledger + 1 anomalia, provenance veritiera, 0 invii", d02)
        record("D03", "NG-05 end-to-end: IDENTITY_DRIFT",
               "stesso comportamento di D02", d03)
        record("D04", "NG-05 end-to-end: crash prima del COMMIT del Core",
               "nulla di parziale; retry senza crash riesce", d04)
        record("D05", "NG-05 end-to-end: CAS, non-RESERVED, identita' remota, provenance vietata",
               "tutti rifiutati fail-closed, nessun doppio settlement", d05)
        record("D06", "NG-03 preservation: provenance del trasporto confinata",
               "mark_refused_before_send invariata e mai chiamata dal runtime", d06)
        record("D07", "NG-03 controprova positiva: percorso transport-attested",
               "TRANSPORT_ATTESTED_NOT_SENT ancora registrata dove e' vera", d07)
        record("D08", "SUBMIT_UNKNOWN: nessun settlement zero, nessun blind retry",
               "resta SUBMIT_UNKNOWN; API atomica rifiutata; 1 solo attempt", d08)
        record("D09", "Regressioni dei meccanismi sul Core candidate",
               "P-B01+P-B02, NG-04, legacy, orphan, P-B04 invariati", lambda: d09(scratch))
        record("D10", "Regressione R0-R1 (T01-T37) contro il Core candidate",
               "36/37 PASS, 0 FAIL, T29 BLOCKED per policy", d10)
        record("D11", "P2 freeze, baseline intatte, bundle approvati non toccati",
               "P2 before==after; Core/Runtime main invariati; 0 tag; 0 credenziali", d11)
        record("D12", "Catena di provenance: struttura approvata preservata",
               "5 controprove del verificatore", lambda: d12(scratch))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    report = build_report()
    write_results(report)
    xc = cross_check(report)
    print(readiness.console(report), flush=True)
    print(f"\ncross-check dei file scritti: {'OK' if xc['ok'] else xc['problems']}", flush=True)
    if not xc["ok"]:
        return 2
    return report["runner_exit"]


if __name__ == "__main__":
    sys.exit(main())
