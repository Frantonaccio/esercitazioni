#!/usr/bin/env python3
"""PROVIDER BOUNDARY GATE — OPEN-GAP CLOSURE / PRE-REAL-PROVIDER — matrice C00..C09.

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION · NO DEPLOY.

  C00  Reality Lock (Core/Runtime agli SHA canonici, tree puliti, pin, P2 before)
  C01  PHASE A: ogni gap riprodotto sul Runtime canonico prima di ogni fix
  C02  P-B02 + P-B01 COMPOSIZIONE: firma e verifica DENTRO lo spender isolato (UID distinti)
  C03  NG-04 freshness: meccanismo fail-closed parametrico (policy iniettata dal test)
  C04  Legacy spend paths: inventario aggiornato + modalita' Provider Boundary fail-closed
  C05  Orphan RESERVED lease: meccanismo parametrico + policy che resta una decisione umana
  C06  NG-05: il Core canonico non offre la primitive; delta additivo su branch dedicato
  C07  Regressione R0-R1 (tests/run_gate.py T01-T37) sul Runtime modificato
  C08  P2 freeze after == before, Core main e pin invariati, static checks
  C09  Reporting: test suite result e phase readiness separati, authority unica fail-closed

La classificazione dei test usa la stessa authority della fase precedente
(`RUNTIME_INTEGRATION_GATE_01/tests/gate_report.py`): BLOCKED non e' PASS.
La readiness di fase ha la sua authority unica: `pbg2/readiness.py`.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BUNDLE)
GATE01 = os.path.join(REPO, "RUNTIME_INTEGRATION_GATE_01")
BUNDLE01 = os.path.join(REPO, "PROVIDER_BOUNDARY_HARDENING_01")
CORE_PATH = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")
CORE_BRANCH_PATH = os.environ.get("CREATIVE_OS_CORE_BRANCH_PATH", "/home/user/creative-os-atomicity")
STATE_DIR = os.path.join(GATE01, "state")
EVIDENCE_DIR = os.path.join(BUNDLE, "evidence")
RAW_DIR = os.path.join(EVIDENCE_DIR, "raw")
PRE_FIX_DIR = os.path.join(EVIDENCE_DIR, "pre_fix")
REGRESSION_DIR = os.path.join(BUNDLE, "regression")
for p in (GATE01, BUNDLE01, BUNDLE):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("RUNTIME_GATE_ROOT", GATE01)
os.environ.setdefault("PBGATE01_ROOT", BUNDLE01)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from runtime.core_pin import REQUIRED_CORE_SHA                      # noqa: E402
from tests import gate_report, static_checks                        # noqa: E402
from pbgate import pb_worker                                        # noqa: E402
from pbg2 import bundle_provenance, gate_workers, readiness         # noqa: E402

CANON = {"core_sha": "740ee979300fe20a9382992528604dee70cb2fcf",
         "runtime_main_sha": "0698279703ab959625ac4e84ee636bc5b93b45fd",
         "p2_sha256": "637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1"}
P2_PATH = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16",
                       "P2_RUNTIME", "hf_batch.py")
EXPECTED_IDS = frozenset(f"C{i:02d}" for i in range(0, 12))
CORE_CANDIDATE_SHA = "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515"
POLICY = {"C02": frozenset({"BLOCKED_ENVIRONMENT"})}
CTX = multiprocessing.get_context("spawn")
RESULTS: list[dict] = []
SHARED: dict = {}
UID_ORCH = int(os.environ.get("PB01_ORCH_UID", "65531"))
UID_SPENDER = int(os.environ.get("PB01_SPENDER_UID", "65532"))
UID_OTHER = int(os.environ.get("PB01_OTHER_UID", "65530"))
SETPRIV = ["setpriv", "--clear-groups", "--inh-caps=-all", "--bounding-set=-all", "--no-new-privs"]
# Parametri di PROVA della freshness passati al daemon: non sono una decisione di policy.
FRESHNESS_TEST_MAX_AGE = 300.0
FRESHNESS_TEST_MAX_SKEW = 5.0
FRESHNESS_TEST_LABEL = "LAB_GATE_PARAMETER_NOT_A_POLICY_DECISION"


# ------------------------------------------------------------------ utilita'
def db_for(name: str) -> str:
    p = os.path.join(STATE_DIR, f"pbg2_{name}.db")
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


def git(*args, cwd=CORE_PATH) -> str:
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
                                     exception_evidence=lambda tid, payload: evidence(tid, "exception", payload))
    RESULTS.append(r)
    print(gate_report.console_line(r), flush=True)


def caps_eff() -> int:
    for line in open("/proc/self/status", encoding="utf-8"):
        if line.startswith("CapEff:"):
            return int(line.split(":", 1)[1].strip(), 16)
    return 0


# ------------------------------------------------------------------ C00
def c00():
    core_head = git("rev-parse", "HEAD")
    core_branch = git("branch", "--show-current")
    core_status = git("status", "--porcelain", "--untracked-files=all")
    subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True, text=True)
    origin_main = git("rev-parse", "origin/main", cwd=REPO)
    runtime_head = git("rev-parse", "HEAD", cwd=REPO)
    descends = subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor",
                               CANON["runtime_main_sha"], runtime_head]).returncode == 0
    p2 = sha256_file(P2_PATH)
    SHARED["p2_before"] = p2
    unpublished = subprocess.run(["git", "-C", REPO, "log", "--oneline",
                                  f"{CANON['runtime_main_sha']}..HEAD"],
                                 capture_output=True, text=True).stdout.strip().splitlines()
    d = {"core_head": core_head, "core_branch": core_branch, "core_status_porcelain": core_status,
         "runtime_origin_main": origin_main, "runtime_head": runtime_head,
         "runtime_head_descends_from_canonical": descends,
         "runtime_branch": git("branch", "--show-current", cwd=REPO),
         "runtime_commits_beyond_canonical": unpublished,
         "required_core_sha": REQUIRED_CORE_SHA, "p2_sha256_before": p2, "canonical": CANON}
    ok = (core_head == CANON["core_sha"] and core_branch == "main" and core_status == ""
          and origin_main == CANON["runtime_main_sha"] and descends
          and REQUIRED_CORE_SHA == CANON["core_sha"] and p2 == CANON["p2_sha256"])
    ev = evidence("C00", "reality_lock", d)
    return (f"Core {core_head[:12]} ({core_branch}) clean={core_status == ''} · Runtime origin/main "
            f"{origin_main[:12]} (HEAD {runtime_head[:12]} discende={descends}) · pin "
            f"{REQUIRED_CORE_SHA[:12]} · P2 {p2[:16]}"), ev, ok


# ------------------------------------------------------------------ C01
def c01():
    names = ("ng04_freshness", "ng05_atomicity", "orphan_lease", "legacy_spend_paths",
             "pb01_pb02_composition")
    found, statuses = {}, {}
    for n in names:
        path = os.path.join(PRE_FIX_DIR, f"reproduction_{n}.json")
        if not os.path.exists(path):
            statuses[n] = "MISSING"
            continue
        payload = json.load(open(path, encoding="utf-8"))
        statuses[n] = payload.get("status")
        found[n] = {"sha256": sha256_file(path), "status": payload.get("status")}
    # la premessa del mandato smentita deve essere registrata, non nascosta
    ng05 = json.load(open(os.path.join(PRE_FIX_DIR, "reproduction_ng05_atomicity.json"),
                          encoding="utf-8")) if statuses.get("ng05_atomicity") else {}
    core_change_required = (ng05.get("core_surface") or {}).get("core_change_required")
    ok = (all(v == "REPRODUCED" for v in statuses.values()) and core_change_required is True)
    ev = evidence("C01", "phase_a_reproductions", {"statuses": statuses, "files": found,
                                                   "core_change_required": core_change_required,
                                                   "gap_matrix": "GAP_MATRIX.md"})
    return (f"riproduzioni pre-fix: {statuses} · premessa «il Core offre gia' una primitive atomica» "
            f"verificata FALSA (core_change_required={core_change_required})"), ev, ok


# ------------------------------------------------------------------ C02 (composizione)
def _run_as(uid: int, argv: list, env: dict, timeout: int = 300):
    return subprocess.run(SETPRIV + [f"--reuid={uid}", f"--regid={uid}", "env",
                                     *[f"{k}={v}" for k, v in env.items()], *argv],
                          capture_output=True, text=True, timeout=timeout)


def _mkdir_owned(path: str, uid: int, mode: int) -> None:
    os.makedirs(path, exist_ok=True)
    os.chown(path, uid, uid)
    os.chmod(path, mode)


def c02(scratch: str):                                              # noqa: C901
    precond = {"euid": os.geteuid(), "setpriv": shutil.which("setpriv"),
               "cap_eff": hex(caps_eff()), "cap_setuid": bool(caps_eff() & (1 << 7)),
               "cap_setgid": bool(caps_eff() & (1 << 6)), "cap_chown": bool(caps_eff() & (1 << 0))}
    root = os.path.join(STATE_DIR, "pbg2_comp")
    shutil.rmtree(root, ignore_errors=True)
    can = (precond["euid"] == 0 and precond["setpriv"] and precond["cap_setuid"]
           and precond["cap_setgid"] and precond["cap_chown"])
    if not can:
        ev = evidence("C02", "pb01_pb02_composition",
                      {"precondition": precond, "status": "BLOCKED",
                       "reason_code": "BLOCKED_ENVIRONMENT", "requirement_verified": False})
        raise gate_report.GateBlocked(
            "BLOCKED_ENVIRONMENT",
            f"l'ambiente non consente UID distinti (euid={precond['euid']}, "
            f"setpriv={precond['setpriv']}, caps={precond['cap_eff']}): la COMPOSIZIONE "
            f"P-B01+P-B02 non e' dimostrabile qui, nessun PASS simulato", ev)
    spender, ipc, orch = (os.path.join(root, x) for x in ("spender", "ipc", "orch"))
    _mkdir_owned(root, 0, 0o755)
    _mkdir_owned(spender, UID_SPENDER, 0o700)
    _mkdir_owned(ipc, UID_SPENDER, 0o755)
    _mkdir_owned(orch, UID_ORCH, 0o700)
    db = os.path.join(spender, "store.db")
    secret_dir = os.path.join(spender, "secret")
    sock, ready = os.path.join(ipc, "spender.sock"), os.path.join(ipc, "ready.json")
    common_env = {"PYTHONDONTWRITEBYTECODE": "1", "RUNTIME_GATE_ROOT": GATE01,
                  "PBGATE01_ROOT": BUNDLE01, "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                  "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
                  "GIT_CONFIG_VALUE_0": "*"}
    os.makedirs(RAW_DIR, exist_ok=True)
    log_path = os.path.join(RAW_DIR, "C02_spender_daemon2.log")
    daemon_log = open(log_path, "w", encoding="utf-8")
    daemon = subprocess.Popen(
        SETPRIV + [f"--reuid={UID_SPENDER}", f"--regid={UID_SPENDER}", "env",
                   *[f"{k}={v}" for k, v in common_env.items()], f"HOME={spender}",
                   sys.executable, os.path.join(BUNDLE, "pbg2", "spender_daemon2.py"),
                   "--socket", sock, "--db", db, "--secret-dir", secret_dir, "--core", CORE_PATH,
                   "--canary-home", os.path.join(spender, "canary"),
                   "--allowed-peer-uid", str(UID_ORCH), "--ready-file", ready,
                   "--freshness-max-age-s", str(FRESHNESS_TEST_MAX_AGE),
                   "--freshness-max-future-skew-s", str(FRESHNESS_TEST_MAX_SKEW),
                   "--freshness-label", FRESHNESS_TEST_LABEL, "--max-sessions", "64"],
        stdout=daemon_log, stderr=subprocess.STDOUT)
    info = None
    try:
        for _ in range(600):
            if os.path.exists(ready):
                info = json.load(open(ready, encoding="utf-8"))
                break
            if daemon.poll() is not None:
                break
            time.sleep(0.1)
        if info is None:
            daemon_log.close()
            log = open(log_path, encoding="utf-8").read()
            ev = evidence("C02", "pb01_pb02_composition",
                          {"precondition": precond, "daemon_failed": True, "log": log})
            return f"daemon spender v2 non avviato (uid {UID_SPENDER}): {log[-400:]}", ev, False
        probe = [sys.executable, os.path.join(BUNDLE, "pbg2", "composition_probe.py"),
                 "--socket", sock, "--spend-secret-path", info["secret_path"],
                 "--recon-secret-path", info["recon_secret_path"], "--ready-file", ready,
                 "--db", db, "--core", CORE_PATH, "--spender-pid", str(info["pid"]),
                 "--operation-id", "lab:composition", "--prompt", "composition boundary"]
        r_full = _run_as(UID_ORCH, probe + ["--mode", "full"], {**common_env, "HOME": orch})
        r_other = _run_as(UID_OTHER, probe + ["--mode", "peer_only"],
                          {**common_env, "HOME": os.path.join(scratch, "other_home")})
        r_stop = _run_as(UID_ORCH, probe + ["--mode", "stop"], {**common_env, "HOME": orch})
        daemon.wait(60)
    finally:
        if daemon.poll() is None:
            daemon.terminate()
            daemon.wait(10)
        daemon_log.close()

    def parse(r):
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:                                           # noqa: BLE001
            return {"parse_error": True, "stdout": r.stdout[-3000:], "stderr": r.stderr[-3000:],
                    "rc": r.returncode}
    full, other, stop = parse(r_full), parse(r_other), parse(r_stop)
    C = full.get("counterproofs", {}) if isinstance(full.get("counterproofs"), dict) else {}
    binding = C.get("binding_counterproofs", {}) or {}
    key_probes = C.get("read_signing_key", {}) or {}
    rows = pb_worker._rows(db) if os.path.exists(db) else []
    st_recon = os.stat(info["recon_secret_path"])
    st_db = os.stat(db)
    daemon_log_text = open(log_path, encoding="utf-8").read()

    def refused(case, code):
        return (binding.get(case) or {}).get("refused") == code

    checks = {
        # --- 1. segreto ------------------------------------------------------------------
        "uids_distinct": (full.get("uid") == UID_ORCH and info["uid"] == UID_SPENDER
                          and other.get("uid") == UID_OTHER),
        "orchestrator_no_caps": (full.get("caps", {}).get("CapEff") == "0000000000000000"
                                 and full.get("no_new_privs") == "1"),
        "recon_secret_unreadable": str(C.get("read_recon_secret", "")).startswith("BLOCKED"),
        "spend_secret_unreadable": str(C.get("read_spend_secret", "")).startswith("BLOCKED"),
        "secret_dir_unlistable": str(C.get("list_secret_dir", "")).startswith("BLOCKED"),
        "recon_secret_owned_by_spender_0600": (st_recon.st_uid == UID_SPENDER
                                               and stat.S_IMODE(st_recon.st_mode) == 0o600),
        # --- 2. signing key --------------------------------------------------------------
        "proc_mem_unreadable": str(key_probes.get("proc_mem", "")).startswith("BLOCKED"),
        "proc_environ_unreadable": str(key_probes.get("proc_environ", "")).startswith("BLOCKED"),
        "ready_file_has_no_key": (isinstance(key_probes.get("ready_file"), dict)
                                  and key_probes["ready_file"].get("contains_key_material") is False
                                  and key_probes["ready_file"].get("signing_key_on_disk") is False),
        "no_key_files_on_disk": key_probes.get("key_files_in_ipc_dir") == [],
        "no_secret_marker_in_channel": (C.get("channel_leak", {}).get("secret_marker_in_channel")
                                        is False),
        "no_key_material_in_channel": C.get("channel_leak", {}).get("unexplained_hex64") == [],
        # --- 3. forgiatura ---------------------------------------------------------------
        "forged_report_refused": (C.get("forge_report_with_own_key", {}).get("refused")
                                  == "UNAUTHENTICATED"),
        "resigned_report_refused": (C.get("resign_with_observed_signature", {}).get("refused")
                                    == "UNAUTHENTICATED"),
        # --- 4. UID non autorizzato ------------------------------------------------------
        "third_uid_refused": ((other.get("peer_only") or [{}])[0].get("refused")
                              == "PEER_UID_NOT_AUTHORIZED"),
        # --- 5. report corretto dallo spender --------------------------------------------
        "correct_report_applied": (C.get("correct_report_from_spender", {}).get("ok") is True
                                   and C.get("correct_report_from_spender", {}).get("state")
                                   == "SUCCEEDED"),
        # --- 6. replay -------------------------------------------------------------------
        # Due facce, entrambe fail-closed: l'orchestrator che ripropone il report su un job
        # ormai terminale (NOT_RECONCILABLE) e il replay vero, su un job ancora riconciliabile,
        # rifiutato dal NONCE monouso dentro lo spender (REPLAY).
        "replay_by_orchestrator_refused": (C.get("replay_same_report", {}).get("refused")
                                           == "NOT_RECONCILABLE"),
        "replay_nonce_refused_inside_spender": refused("replay", "REPLAY"),
        # --- 7..11 binding, dentro lo spender --------------------------------------------
        "wrong_provider_refused": refused("wrong_provider", "PROVIDER_MISMATCH"),
        "wrong_account_refused": refused("wrong_account", "ACCOUNT_MISMATCH"),
        "wrong_job_refused": refused("wrong_job", "JOB_UNKNOWN"),
        "wrong_operation_refused": refused("wrong_operation", "OPERATION_MISMATCH"),
        "wrong_attempt_refused": refused("wrong_attempt", "ATTEMPT_TOKEN_MISMATCH"),
        "wrong_payload_digest_refused": refused("wrong_payload_digest", "PAYLOAD_DIGEST_MISMATCH"),
        # --- freshness composta col confine ----------------------------------------------
        "stale_refused_inside_spender": refused("stale", "REPORT_STALE"),
        "future_refused_inside_spender": refused("from_future", "REPORT_FROM_FUTURE"),
        # --- stato autorevole ------------------------------------------------------------
        "store_owned_by_spender": st_db.st_uid == UID_SPENDER,
        "one_row_reconciled_to_succeeded": (len(rows) == 1 and rows[0]["state"] == "SUCCEEDED"
                                            and rows[0]["provider_account"] == info["account_id"]),
        "sentinel_zero_violations": (stop.get("stop") or [{}])[0].get("violations") == [],
        "no_secret_in_daemon_log": ("FAKE_RECONCILIATION_SECRET_" not in daemon_log_text
                                    or "SECRET_OR_KEY_IN_CHANNEL" not in daemon_log_text),
        "freshness_enforced_by_daemon": (full.get("whoami", {}).get("freshness", {}).get("label")
                                         == FRESHNESS_TEST_LABEL),
    }
    ok = all(checks.values())
    ev = evidence("C02", "pb01_pb02_composition", {
        "precondition": precond,
        "uids": {"orchestrator": UID_ORCH, "spender": UID_SPENDER, "other": UID_OTHER},
        "daemon": info, "probe_full": full, "probe_other_uid": other, "stop": stop,
        "counterproofs": C, "binding_counterproofs": binding,
        "spender_store_rows": rows,
        "recon_secret_stat": {"uid": st_recon.st_uid, "mode": oct(stat.S_IMODE(st_recon.st_mode))},
        "checks": checks, "status": "PASS" if ok else "FAIL", "requirement_verified": ok,
        "scope_note": "composizione LAB: segreto e chiave fittizi, FakeAdapter, kernel DAC fra UID "
                      "non privilegiati. NON e' una verifica di provider reale ne' di credenziali reali.",
        "daemon_log_tail": daemon_log_text[-2000:]})
    failed = [k for k, v in checks.items() if not v]
    return (f"orchestrator uid {full.get('uid')} vs spender {info['uid']} · segreto di "
            f"riconciliazione {C.get('read_recon_secret')} · chiave: /proc/mem "
            f"{key_probes.get('proc_mem')}, ready-file senza chiave "
            f"{(key_probes.get('ready_file') or {}).get('contains_key_material') is False}, "
            f"0 hex64 estranei sul canale · forge -> "
            f"{C.get('forge_report_with_own_key', {}).get('refused')} · terzo uid -> "
            f"{(other.get('peer_only') or [{}])[0].get('refused')} · report dello spender -> "
            f"{C.get('correct_report_from_spender', {}).get('state')} · replay: orchestrator -> "
            f"{C.get('replay_same_report', {}).get('refused')}, nonce dentro lo spender -> "
            f"{(binding.get('replay') or {}).get('refused')} · binding "
            f"{ {k: (v or {}).get('refused') for k, v in binding.items()} } · check falliti: "
            f"{failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ C03
def c03():
    db = db_for("c03")
    ops = [f"lab:c03_{i}" for i in range(6)]
    prep = in_process(gate_workers.prepare_unknown_jobs, db, CORE_PATH, ops)
    r = in_process(gate_workers.ng04_matrix, db, CORE_PATH)
    pb_worker.cleanup_db(db)
    ok = bool(prep.get("ok") and r.get("verified"))
    ev = evidence("C03", "ng04_freshness_mechanism", {"prepare": prep, "matrix": r})
    cases = r.get("cases", {})
    return (f"{len(r.get('expected_codes', {}))} controprove fail-closed (scarti: "
            f"{r.get('code_mismatches') or 'nessuno'}) · casi che devono passare: "
            f"{'tutti' if not r.get('applied_mismatches') else r.get('applied_mismatches')} · "
            f"policy omessa -> {cases.get('policy_omitted', {}).get('code')} · 1970 -> "
            f"{cases.get('ancient_1970', {}).get('code')} · futuro -> "
            f"{cases.get('from_future_beyond_skew', {}).get('code')} · confine age==max -> "
            f"applicato={cases.get('boundary_age_eq_max', {}).get('applied')} · nonce non bruciato "
            f"da un rifiuto -> applicato={cases.get('same_nonce_after_stale_refusal', {}).get('applied')} · "
            f"replay -> {cases.get('replay_second', {}).get('code')} · journal invariato sui rifiuti: "
            f"{r.get('refusals_left_journal_unchanged')}"), ev, ok


# ------------------------------------------------------------------ C04
def c04():
    static = in_process(gate_workers.legacy_static_inventory)
    db_open, db_closed = db_for("c04_open"), db_for("c04_closed")
    disengaged = in_process(gate_workers.legacy_entry_points, db_open, CORE_PATH, False)
    engaged = in_process(gate_workers.legacy_entry_points, db_closed, CORE_PATH, True)
    for d in (db_open, db_closed):
        pb_worker.cleanup_db(d)
    E_off = disengaged.get("entry_points", {})
    E_on = engaged.get("entry_points", {})
    checks = {
        "mode_default_disengaged": disengaged.get("mode") == "DISENGAGED",
        "mode_engaged_when_asked": engaged.get("mode") == "ENGAGED",
        "legacy_open_when_disengaged": (E_off.get("#2_go_legacy", {}).get("reached_spend") is True
                                        and disengaged.get("legacy_switch_state") == "ENABLED_LAB_ONLY"),
        "legacy_closed_when_engaged": (E_on.get("#2_go_legacy", {}).get("code")
                                       == "LEGACY_SPEND_PATH_DISABLED"
                                       and E_on.get("#2_go_legacy", {}).get("reached_spend") is False
                                       and engaged.get("legacy_switch_state") == "DISABLED"),
        "store_call_open_when_disengaged": E_off.get("#7_store_call", {}).get("ok") is True,
        "store_call_closed_when_engaged": (E_on.get("#7_store_call", {}).get("code")
                                           == "PROVIDER_BOUNDARY_MODE_ENGAGED"
                                           and E_on.get("#7_store_call", {}).get("reached_store") is False
                                           and E_on.get("#7_store_call", {}).get("store_created") is False),
        "governed_path_works_in_both_modes": (E_off.get("#1_governed", {}).get("state") == "SUCCEEDED"
                                              and E_on.get("#1_governed", {}).get("state") == "SUCCEEDED"),
        # la verita' scomoda, asserita esplicitamente: le primitive del Core NON sono governate
        "core_primitives_reachable_in_both_modes": (
            E_off.get("#10_core_run_job", {}).get("reached_spend") is True
            and E_on.get("#10_core_run_job", {}).get("reached_spend") is True
            and E_off.get("#11_core_raw_reconcile", {}).get("accepted") is True
            and E_on.get("#11_core_raw_reconcile", {}).get("accepted") is True),
        "static_inventory_non_empty": bool(static.get("hits")),
    }
    ok = all(checks.values())
    ev = evidence("C04", "legacy_spend_paths_v2", {
        "static_inventory": static, "disengaged": disengaged, "engaged": engaged,
        "checks": checks, "inventory_doc": "LEGACY_SPEND_PATHS_V2.md",
        "residual_open": ["#10 transport.pipeline.run_job / adapter.submit",
                          "#11 registry.reservations.reconcile raw"],
        "residual_state": "CORE_CHANGE_REQUIRED",
        "note": "la modalita' chiude i percorsi del RUNTIME; le primitive del CORE restano "
                "raggiungibili da chiunque abbia il Core in sys.path: e' dichiarato, non aggirato."})
    failed = [k for k, v in checks.items() if not v]
    return (f"modalita' disingaggiata: legacy #2 spende ({E_off.get('#2_go_legacy', {}).get('state')}), "
            f"helper #7 ok · ingaggiata: #2 -> {E_on.get('#2_go_legacy', {}).get('code')}, #7 -> "
            f"{E_on.get('#7_store_call', {}).get('code')} (store non creato), #1 governato -> "
            f"{E_on.get('#1_governed', {}).get('state')} · primitive del Core #10/#11 raggiungibili in "
            f"ENTRAMBE le modalita' (CORE_CHANGE_REQUIRED) · check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ C05
def c05():
    db = db_for("c05")
    mech = in_process(gate_workers.orphan_mechanism, db, CORE_PATH)
    # crash DURANTE il reclaim, su un job dedicato
    db2 = db_for("c05_crash")
    crash_job = in_process(_make_orphan_for_crash, db2, CORE_PATH)
    crash = run_until_exit(gate_workers.orphan_crash_during_reclaim, db2, CORE_PATH,
                           crash_job.get("job_id")) if crash_job.get("ok") else None
    repair = (in_process(gate_workers.orphan_repair_after_crash, db2, CORE_PATH,
                         crash_job.get("job_id")) if crash_job.get("ok") else None)
    for d in (db, db2):
        pb_worker.cleanup_db(d)
    crash_ok = bool(crash and crash.get("exitcode") == 11
                    and (repair or {}).get("row_after_crash", {}).get("state") == "FAILED"
                    and (repair or {}).get("row_after_crash", {}).get("settled_units") is None
                    and (repair or {}).get("totals_after_crash", {}).get("terminal_unsettled_jobs") == 1
                    and (repair or {}).get("repair", {}).get("applied") is True
                    and (repair or {}).get("repair_idempotent", {}).get("applied") is False
                    and (repair or {}).get("totals_after_repair", {}).get("terminal_unsettled_jobs") == 0)
    ok = bool(mech.get("verified") and crash_ok)
    ev = evidence("C05", "orphan_lease_mechanism_policy", {
        "mechanism": mech, "crash_during_reclaim": {"job": crash_job, "crash": crash, "repair": repair},
        "policy_status": "POLICY_DECISION_REQUIRED",
        "requirement_closed": False,
        "note": "il MECCANISMO e' verificato; il requisito NON e' chiuso: finestra, attore, evidenze e "
                "classi ammesse restano una decisione umana (ORPHAN_LEASE_MECHANISM_POLICY.md)."})
    cases = mech.get("cases", {})
    return (f"policy omessa -> {cases.get('policy_omitted', {}).get('code')} · attore errato -> "
            f"{cases.get('wrong_actor', {}).get('code')} · evidenza incompleta -> "
            f"{cases.get('evidence_incomplete', {}).get('code')} · lease non scaduto -> "
            f"{cases.get('lease_not_expired', {}).get('code')} · fence stantio -> "
            f"{cases.get('fencing_token_stale', {}).get('code')} · classe non ammessa -> "
            f"{cases.get('class_not_allowed', {}).get('code')} · corsa persa dal reclaim -> "
            f"{cases.get('race_lost_by_reclaim', {}).get('code')} (riga intatta) · fence dopo "
            f"scrittura neutra -> {cases.get('fencing_token_stale_after_neutral_write', {}).get('code')} · "
            f"corsa vinta dal reclaim -> mark_submitting successivo "
            f"{cases.get('mark_submitting_after_reclaim', {}).get('error')} · reclaim legittimo -> FAILED "
            f"settled 0 · zero nuovi attempt · crash durante il reclaim (exit "
            f"{(crash or {}).get('exitcode')}): terminale non regolato VISIBILE e riparato "
            f"idempotentemente · RECLAIM_POLICY = {mech.get('reclaim_policy_constant')} "
            f"(requisito NON chiuso)"), ev, ok


def _make_orphan_for_crash(db: str, core_path: str) -> dict:
    """Prenotazione orfana (processo che muore prima di mark_submitting), creata a parte."""
    try:
        from runtime.genspec_bridge import build_genspec
        if core_path not in sys.path:
            sys.path.insert(0, core_path)
        from adapters.base import GenSpec
        from registry.reservations import SqliteReservationStore
        from tests.worker import make_inputs as mi
        store = SqliteReservationStore(db)
        store.open_envelope("ENV_LAB", 100, now=1.0)
        _, j = store.reserve_or_get_live(build_genspec(mi("orphan crash"), GenSpec), now=1.0,
                                         budget_units=10, envelope_id="ENV_LAB",
                                         operation_id="lab:orph_crash")
        return {"ok": True, "job_id": j.job_id}
    except Exception as e:                                          # noqa: BLE001
        return {"ok": False, "error": type(e).__name__, "message": str(e)}


# ------------------------------------------------------------------ C06
def c06():
    main_surface = in_process(gate_workers.ng05_core_main_surface, CORE_PATH)
    runtime_path = in_process(gate_workers.ng05_runtime_path_unchanged)
    branch = {"path": CORE_BRANCH_PATH, "exists": os.path.isdir(CORE_BRANCH_PATH)}
    if branch["exists"]:
        branch["head"] = git("rev-parse", "HEAD", cwd=CORE_BRANCH_PATH)
        branch["branch"] = git("branch", "--show-current", cwd=CORE_BRANCH_PATH)
        branch["base"] = git("rev-parse", "HEAD~1", cwd=CORE_BRANCH_PATH)
        branch["status"] = git("status", "--porcelain", "--untracked-files=all", cwd=CORE_BRANCH_PATH)
        branch["diff_stat"] = subprocess.run(
            ["git", "-C", CORE_BRANCH_PATH, "diff", "--stat", CANON["core_sha"], "HEAD"],
            capture_output=True, text=True).stdout.strip()
        os.makedirs(RAW_DIR, exist_ok=True)
        log = os.path.join(RAW_DIR, "C06_core_branch_tests.log")
        suites = {}
        for t in ("run_ng05_pre_submit_atomicity", "run_r0_r1_hardening", "run_reservation",
                  "run_review_pr2_final", "run_review_pr2", "run_block2", "run_golden",
                  "run_boot_paths", "run_case_collision"):
            r = subprocess.run([sys.executable, os.path.join(CORE_BRANCH_PATH, "tests", f"{t}.py")],
                               capture_output=True, text=True, cwd=CORE_BRANCH_PATH, timeout=600)
            suites[t] = {"returncode": r.returncode, "tail": r.stdout.strip()[-400:]}
        with open(log, "w", encoding="utf-8") as fh:
            json.dump(suites, fh, indent=2, ensure_ascii=False)
        branch["test_suites"] = suites
    patch = os.path.join(EVIDENCE_DIR, "CORE_DELTA_NG05_mark_refused_pre_submit.patch")
    checks = {
        "core_main_has_no_new_api": main_surface.get("core_main_has_new_api") is False,
        "core_main_protocol_unchanged": main_surface.get("protocol_has_new_api") is False,
        "runtime_still_conservative": (runtime_path.get("uses_reconcile_then_settle") is True
                                       and runtime_path.get("uses_new_core_api") is False),
        "runtime_never_uses_transport_provenance": runtime_path.get("uses_mark_refused_before_send") is False,
        "core_branch_exists": branch.get("exists") is True,
        "core_branch_is_dedicated": branch.get("branch") == "harden/provider-boundary-core-atomicity-2026-09-17",
        "core_branch_based_on_canonical": branch.get("base") == CANON["core_sha"],
        "core_branch_clean": branch.get("status") == "",
        "core_branch_all_suites_pass": all(v["returncode"] == 0
                                           for v in (branch.get("test_suites") or {"x": {"returncode": 1}}).values()),
        "patch_exported": os.path.exists(patch),
    }
    ok = all(checks.values())
    # fatti osservati per `merge_readiness` (BLOCKER 2): nessuno di questi e' asserito a mano
    SHARED["pair_facts"] = {
        "core_branch_all_suites_pass": checks["core_branch_all_suites_pass"],
        "core_branch_based_on_canonical": checks["core_branch_based_on_canonical"],
        "core_branch_clean": checks["core_branch_clean"],
        "runtime_uses_new_core_api": bool(runtime_path.get("uses_new_core_api")),
        "required_core_sha": REQUIRED_CORE_SHA,
        "core_candidate_sha": branch.get("head"),
        "core_candidate_branch": branch.get("branch"),
    }
    ev = evidence("C06", "ng05_decision_and_core_delta", {
        "core_main_surface": main_surface, "runtime_path": runtime_path, "core_branch": branch,
        "pair_facts": SHARED["pair_facts"],
        "core_review_state": readiness.CORE_REVIEW_STATE,
        "checks": checks, "decision": "CORE_CHANGE_REQUIRED",
        "requirement_closed": False,
        "note": "il delta e' prodotto e verificato su branch dedicato, NON mergiato. Core main resta "
                "740ee979 e il Runtime resta pinnato a quello, sul percorso conservativo a due "
                "transazioni. Il requisito NON e' chiuso: serve Human Review e un merge del Core."})
    failed = [k for k, v in checks.items() if not v]
    suites = branch.get("test_suites") or {}
    return (f"Core main: nessuna API nuova (pin {CANON['core_sha'][:12]}) · Runtime: percorso "
            f"conservativo invariato (reconcile->settle, mai mark_refused_before_send) · branch "
            f"{branch.get('branch')} @ {str(branch.get('head'))[:12]} su base "
            f"{str(branch.get('base'))[:12]}: {len([v for v in suites.values() if v['returncode'] == 0])}"
            f"/{len(suites)} suite PASS · {branch.get('diff_stat', '').splitlines()[-1] if branch.get('diff_stat') else ''} · "
            f"check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ C07
def c07():
    os.makedirs(REGRESSION_DIR, exist_ok=True)
    log = os.path.join(REGRESSION_DIR, "r0_r1_run_gate.log")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "RUNTIME_GATE_ROOT": GATE01}
    env.pop("CREATIVE_OS_PROVIDER_BOUNDARY_MODE", None)     # come a baseline: modalita' disingaggiata
    r = subprocess.run([sys.executable, os.path.join(GATE01, "tests", "run_gate.py")],
                       capture_output=True, text=True, cwd=GATE01, env=env, timeout=3600)
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(r.stdout + "\n--- stderr ---\n" + r.stderr)
    results_path = os.path.join(GATE01, "evidence", "RESULTS.json")
    data = json.load(open(results_path, encoding="utf-8")) if os.path.exists(results_path) else {}
    summary = data.get("summary") or {}
    if os.path.exists(results_path):
        shutil.copy(results_path, os.path.join(REGRESSION_DIR, "r0_r1_RESULTS.json"))
    fails = summary.get("fail_ids") or []
    blocked = summary.get("blocked_tests") or []
    not_allowed = summary.get("blocked_not_allowed_by_policy") or []
    decision = summary.get("gate_decision")
    # BASELINE (fase precedente, bundle v3): 36/37 PASS con T29 BLOCKED_ENVIRONMENT per policy,
    # 0 FAIL, decisione LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED. "Nessuna regressione" significa
    # esattamente questo, non un exit code.
    ok = (r.returncode == 0 and not fails and not not_allowed
          and summary.get("inventory", {}).get("valid") is True
          and decision in ("LAB_GATE_COMPLETE_ALL_VERIFIED", "LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED")
          and summary.get("pass") == 36 and summary.get("total") == 37)
    ev = evidence("C07", "regression_r0_r1", {
        "returncode": r.returncode, "summary": summary, "baseline_expected":
            {"total": 37, "pass": 36, "fail": 0, "blocked": [{"id": "T29",
                                                              "reason_code": "BLOCKED_ENVIRONMENT"}],
             "gate_decision": "LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED"},
        "log": os.path.relpath(log, BUNDLE), "stdout_tail": r.stdout[-3000:],
        "stderr_tail": r.stderr[-2000:]})
    return (f"tests/run_gate.py T01-T37: exit {r.returncode} · PASS {summary.get('pass')}/"
            f"{summary.get('total')} · FAIL {fails or 'nessuno'} · BLOCKED "
            f"{[b['id'] + '/' + b['reason_code'] for b in blocked] or 'nessuno'} (fuori policy: "
            f"{not_allowed or 'nessuno'}) · decisione {decision}"), ev, ok


# ------------------------------------------------------------------ C08
def c08():
    p2_after = sha256_file(P2_PATH)
    core_head = git("rev-parse", "HEAD")
    core_branch = git("branch", "--show-current")
    core_status = git("status", "--porcelain", "--untracked-files=all")
    sc = static_checks.run(CORE_PATH)
    d = {"p2_before": SHARED.get("p2_before"), "p2_after": p2_after,
         "p2_unchanged": SHARED.get("p2_before") == p2_after == CANON["p2_sha256"],
         "core_head": core_head, "core_branch": core_branch, "core_status_porcelain": core_status,
         "required_core_sha": REQUIRED_CORE_SHA, "static_checks": sc}
    ok = (d["p2_unchanged"] and core_head == CANON["core_sha"] and core_branch == "main"
          and core_status == "" and REQUIRED_CORE_SHA == CANON["core_sha"])
    ev = evidence("C08", "p2_freeze_core_pin_after", d)
    return (f"P2 {p2_after[:16]} (before == after == canonico: {d['p2_unchanged']}) · Core main "
            f"{core_head[:12]} clean={core_status == ''} · pin {REQUIRED_CORE_SHA[:12]}"), ev, ok


# ------------------------------------------------------------------ C09
def c09():
    """Il reporting non puo' dichiarare 'tutto verificato' mentre un requisito e' aperto,
    per NESSUNO dei nuovi stati. Cinque controprove, come nella fase precedente."""
    n = len(EXPECTED_IDS)
    base_suite = {"inventory": {"expected_count": n, "observed_count": n, "missing": [],
                                "unexpected": [], "duplicates": [], "valid": True},
                  "total": n, "pass": n, "fail": 0, "blocked": 0, "invalid": []}
    all_pass = [{"id": f"C{i:02d}", "status": "PASS", "reason_code": "VERIFIED"} for i in range(n)]
    real = readiness.build(all_pass, base_suite, pair_facts=SHARED.get("pair_facts"))
    C: dict = {}

    def expect_inconsistent(label, mutate):
        report = json.loads(json.dumps(real))
        mutate(report)
        try:
            readiness.validate(report)
            C[label] = {"raised": False}
        except readiness.ReportingInconsistent as e:
            C[label] = {"raised": True, "message": str(e)}

    expect_inconsistent("all_verified_with_open_requirements",
                        lambda r: r["phase_readiness"].update(all_requirements_verified=True))
    expect_inconsistent("all_verified_with_failed_tests", lambda r: (
        r["phase_readiness"].update(all_requirements_verified=True,
                                    open_requirements_blocking_all_verified=[]),
        r["test_suite"].update(all_tests_passed=False)))
    expect_inconsistent("decision_all_verified_without_flag",
                        lambda r: r["phase_readiness"].update(
                            phase_gate_decision=readiness.PHASE_COMPLETE_ALL_VERIFIED))
    expect_inconsistent("requirement_open_and_verified", lambda r: (
        r["phase_readiness"]["verified_requirements"].append(
            r["phase_readiness"]["open_requirements"][0]["id"])))
    expect_inconsistent("open_flag_incoherent_with_state", lambda r: (
        r["phase_readiness"]["requirements"][0].update(
            state=readiness.POLICY_DECISION_REQUIRED, open=False)))
    expect_inconsistent("all_tests_passed_with_blocked", lambda r: (
        r["test_suite"].update(all_tests_passed=True,
                               blocked_tests=[{"id": "C02", "reason_code": "BLOCKED_ENVIRONMENT"}])))
    # --- merge readiness: nessuna scorciatoia verso il merge (BLOCKER 2) -----------------
    expect_inconsistent("merge_authorized_without_pair",
                        lambda r: r["merge_readiness"].update(merge_authorized=True))
    expect_inconsistent("merge_authorized_with_open_requirements", lambda r: (
        r["merge_readiness"].update(merge_authorized=True, core_runtime_pair_ready=True,
                                    runtime_consumes_core_candidate=True,
                                    pin_points_to_core_candidate=True)))
    expect_inconsistent("merge_authorized_without_human", lambda r: (
        r["merge_readiness"].update(merge_authorized=True, core_runtime_pair_ready=True,
                                    runtime_consumes_core_candidate=True,
                                    pin_points_to_core_candidate=True,
                                    human_merge_authorization=False),
        r["phase_readiness"].update(all_requirements_verified=True,
                                    open_requirements_blocking_all_verified=[],
                                    open_requirements=[], requirements=[])))
    expect_inconsistent("pair_ready_without_consumption",
                        lambda r: r["merge_readiness"].update(core_runtime_pair_ready=True,
                                                              runtime_consumes_core_candidate=False))
    expect_inconsistent("no_blockers_without_authorization",
                        lambda r: r["merge_readiness"].update(blockers=[]))
    # e un caso POSITIVO: con un test BLOCKED la suite non e' all-pass e i requisiti degradano
    blocked_suite = dict(base_suite, blocked=1, **{"pass": n - 1})
    blocked_results = [r if r["id"] != "C02" else
                       {"id": "C02", "status": "BLOCKED", "reason_code": "BLOCKED_ENVIRONMENT"}
                       for r in all_pass]
    degraded = readiness.build(blocked_results, blocked_suite, pair_facts=SHARED.get("pair_facts"))
    comp = next(r for r in degraded["phase_readiness"]["requirements"]
                if r["id"] == "P_B02_P_B01_COMPOSITION")
    checks = {
        "all_five_counterproofs_raise": all(v["raised"] for v in C.values()),
        "real_report_not_all_verified": real["phase_readiness"]["all_requirements_verified"] is False,
        "real_decision_with_open_gaps": (real["phase_readiness"]["phase_gate_decision"]
                                         == readiness.PHASE_COMPLETE_WITH_OPEN_GAPS),
        "max_state_reachable_with_open_gaps": (real["phase_readiness"]["max_state"]
                                               == readiness.MAX_STATE),
        "policy_and_provider_buckets_populated": bool(
            real["phase_readiness"]["policy_decision_required"]
            and real["phase_readiness"]["real_provider_required"]
            and real["phase_readiness"]["core_change_required"]),
        "blocked_test_degrades_requirement": (comp["state"] == readiness.NOT_VERIFIED
                                              and degraded["test_suite"]["all_tests_passed"] is False),
        "not_implied_present": (real["phase_readiness"]["not_implied"] == readiness.NOT_IMPLIED),
        # --- BLOCKER 2: la merge readiness e' presente, calcolata e negativa --------------
        "merge_readiness_present": all(isinstance(real["merge_readiness"].get(k), bool)
                                       for k in readiness.MERGE_READINESS_KEYS),
        "core_runtime_pair_not_ready": real["merge_readiness"]["core_runtime_pair_ready"] is False,
        "merge_not_authorized": real["merge_readiness"]["merge_authorized"] is False,
        "merge_blockers_declared": bool(real["merge_readiness"]["blockers"]),
        "core_review_state_declared": (real["merge_readiness"]["core_review_state"]
                                       == readiness.CORE_REVIEW_STATE),
    }
    ok = all(checks.values())
    ev = evidence("C09", "reporting_phase_readiness", {
        "counterproofs": C, "checks": checks,
        "reference_report": real, "degraded_report_when_c02_blocked": degraded})
    return (f"{len(C)} controprove del reporting tutte sollevate: {checks['all_five_counterproofs_raise']} · "
            f"report reale: all_requirements_verified="
            f"{real['phase_readiness']['all_requirements_verified']}, decisione "
            f"{real['phase_readiness']['phase_gate_decision']}, stato massimo "
            f"{real['phase_readiness']['max_state']} · POLICY_DECISION_REQUIRED "
            f"{real['phase_readiness']['policy_decision_required']} · REAL_PROVIDER_REQUIRED "
            f"{real['phase_readiness']['real_provider_required']} · CORE_CHANGE_REQUIRED "
            f"{real['phase_readiness']['core_change_required']}"), ev, ok


# ------------------------------------------------------------------ C10
def _fixture_manifest(**over) -> dict:
    m = {"schema": "test", "runtime_branch": "b", "runtime_code_sha": "a" * 40,
         "runtime_evidence_head_sha": bundle_provenance.EXTERNAL_ONLY,
         "canonical_runtime_base_sha": "c" * 40,
         "merge_readiness": {"runtime_candidate_ready": True, "core_candidate_ready": True,
                             "core_runtime_pair_ready": False, "merge_authorized": False}}
    m.update(over)
    return m


def _make_fixture(root: str, manifest: dict | None = None) -> str:
    """Bundle finto, minimo ma con la stessa forma di quello vero."""
    os.makedirs(os.path.join(root, "evidence"), exist_ok=True)
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("fixture\n")
    with open(os.path.join(root, "evidence", "E.json"), "w", encoding="utf-8") as fh:
        fh.write('{"x": 1}\n')
    with open(os.path.join(root, bundle_provenance.MANIFEST_NAME), "w", encoding="utf-8") as fh:
        json.dump(manifest or _fixture_manifest(), fh, indent=2, ensure_ascii=False)
    bundle_provenance.write_sums(root)
    return root


def c10(scratch: str):                                              # noqa: C901
    """La catena di provenance deve essere verificata da un test che FALLISCE nei casi che la
    Human Review ha elencato. Si costruisce un bundle finto valido, poi lo si rompe in un modo
    per volta: ogni rottura deve produrre il codice atteso."""
    codes = lambda r: sorted({p["code"] for p in r["problems"]})     # noqa: E731
    C: dict = {}

    def fixture(name, manifest=None):
        root = os.path.join(scratch, "c10", name)
        shutil.rmtree(root, ignore_errors=True)
        os.makedirs(root, exist_ok=True)
        return _make_fixture(root, manifest)

    # 0. baseline: un bundle ben formato passa
    base = fixture("ok")
    C["valid_bundle"] = {"codes": codes(bundle_provenance.verify(base, expect_committed=False))}

    # 1. file presente ma NON coperto da SHA256SUMS
    f1 = fixture("missing")
    with open(os.path.join(f1, "EXTRA.md"), "w", encoding="utf-8") as fh:
        fh.write("non coperto\n")
    C["file_not_in_sums"] = {"codes": codes(bundle_provenance.verify(f1, expect_committed=False))}

    # 2. checksum EXTRA, per un file che non esiste
    f2 = fixture("extra")
    with open(os.path.join(f2, bundle_provenance.SUMS_NAME), "a", encoding="utf-8") as fh:
        fh.write(f"{'0' * 64}  GHOST.md\n")
    C["extra_checksum"] = {"codes": codes(bundle_provenance.verify(f2, expect_committed=False))}

    # 3. MISMATCH
    f3 = fixture("mismatch")
    with open(os.path.join(f3, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("alterato dopo il checksum\n")
    C["checksum_mismatch"] = {"codes": codes(bundle_provenance.verify(f3, expect_committed=False))}

    # 4. MANIFEST.json non coperto (il difetto esatto del package v1)
    f4 = fixture("manifest_uncovered")
    sums_path = os.path.join(f4, bundle_provenance.SUMS_NAME)
    kept = [ln for ln in open(sums_path, encoding="utf-8")
            if not ln.rstrip("\n").endswith(bundle_provenance.MANIFEST_NAME)]
    open(sums_path, "w", encoding="utf-8").writelines(kept)
    C["manifest_not_covered"] = {"codes": codes(bundle_provenance.verify(f4, expect_committed=False))}

    # 5. chiave ambigua `runtime_commit` (il nome bandito dalla review)
    f5 = fixture("ambiguous", _fixture_manifest(runtime_commit="d" * 40))
    C["ambiguous_runtime_commit_key"] = {
        "codes": codes(bundle_provenance.verify(f5, expect_committed=False))}

    # 6. chiave disambiguata mancante
    m6 = _fixture_manifest()
    m6.pop("canonical_runtime_base_sha")
    f6 = fixture("key_missing", m6)
    C["manifest_key_missing"] = {"codes": codes(bundle_provenance.verify(f6, expect_committed=False))}

    # 7. code_sha == evidence_head_sha, con il commit evidence esistente
    f7 = fixture("same_sha")
    head = git("rev-parse", "HEAD", cwd=REPO)
    prov_same = {"runtime_code_sha": "a" * 40, "runtime_evidence_head_sha": "a" * 40}
    C["code_sha_equals_evidence_head"] = {
        "codes": codes(bundle_provenance.verify(f7, expect_committed=False, provenance=prov_same))}

    # 8. HEAD del branch diverso dall'evidence head dichiarato. Gli SHA sono REALI e in
    #    relazione di discendenza, cosi' l'unico difetto misurato e' la deriva di HEAD.
    older, prev = git("rev-parse", "HEAD~2", cwd=REPO), git("rev-parse", "HEAD~1", cwd=REPO)
    f8 = fixture("head_drift", _fixture_manifest(runtime_code_sha=older))
    prov_drift = {"runtime_code_sha": older, "runtime_evidence_head_sha": prev}
    C["head_not_evidence_head"] = {
        "codes": codes(bundle_provenance.verify(f8, expect_committed=False, repo=REPO,
                                                provenance=prov_drift))}

    # 9. provenance coerente con HEAD reale: nessun problema di catena
    f9 = fixture("consistent", _fixture_manifest(runtime_code_sha=prev))
    prov_ok = {"runtime_code_sha": prev, "runtime_evidence_head_sha": head}
    C["provenance_consistent_with_head"] = {
        "codes": codes(bundle_provenance.verify(f9, expect_committed=False, repo=REPO,
                                                provenance=prov_ok))}

    # 10. merge_readiness assente
    m10 = _fixture_manifest()
    m10.pop("merge_readiness")
    f10 = fixture("no_merge_readiness", m10)
    C["merge_readiness_missing"] = {
        "codes": codes(bundle_provenance.verify(f10, expect_committed=False))}

    # 11. merge_authorized=true senza coppia pronta
    m11 = _fixture_manifest(merge_readiness={"runtime_candidate_ready": True,
                                             "core_candidate_ready": True,
                                             "core_runtime_pair_ready": False,
                                             "merge_authorized": True})
    f11 = fixture("merge_without_pair", m11)
    C["merge_authorized_without_pair"] = {
        "codes": codes(bundle_provenance.verify(f11, expect_committed=False))}

    expected = {
        "valid_bundle": [],
        "file_not_in_sums": ["MISSING_FROM_SUMS"],
        "extra_checksum": ["EXTRA_IN_SUMS"],
        "checksum_mismatch": ["CHECKSUM_MISMATCH"],
        "manifest_not_covered": ["MANIFEST_NOT_COVERED", "MISSING_FROM_SUMS"],
        "ambiguous_runtime_commit_key": ["AMBIGUOUS_MANIFEST_KEY"],
        "manifest_key_missing": ["MANIFEST_KEY_MISSING"],
        "code_sha_equals_evidence_head": ["CODE_SHA_EQUALS_EVIDENCE_HEAD"],
        "head_not_evidence_head": ["HEAD_NOT_EVIDENCE_HEAD"],
        "provenance_consistent_with_head": [],
        "merge_readiness_missing": ["MERGE_READINESS_MISSING"],
        "merge_authorized_without_pair": ["MERGE_AUTHORIZED_WITHOUT_PAIR"],
    }
    mismatches = {k: {"got": C[k]["codes"], "expected": v}
                  for k, v in expected.items() if C[k]["codes"] != v}
    # il verificatore deve anche essere quello REALMENTE usato per il bundle vero
    real = bundle_provenance.verify(BUNDLE, repo=REPO, bundle_rel="PROVIDER_BOUNDARY_GATE_02",
                                    expect_committed=True)
    ok = not mismatches
    ev = evidence("C10", "evidence_chain_verifier", {
        "counterproofs": C, "expected": expected, "mismatches": mismatches,
        "verifier": "pbg2/bundle_provenance.py:verify",
        "real_bundle_at_gate_time": {
            "note": "il bundle reale viene verificato DOPO il commit evidence da "
                    "pbg2/make_bundle.py; qui si registra solo lo stato al momento del gate, "
                    "quando MANIFEST.json e SHA256SUMS del nuovo package non esistono ancora",
            "result": real},
        "chain_design": "runtime_code_sha (commit codice) -> runtime_evidence_head_sha (commit "
                        "manifest+checksum, dichiarato solo nella PROVENANCE esterna) -> "
                        "PROVENANCE.json + SHA256SUMS.EXTERNAL"})
    return (f"{len(expected)} controprove della catena di provenance · scarti: "
            f"{mismatches or 'nessuno'} · bundle valido -> 0 problemi · MANIFEST non coperto -> "
            f"{C['manifest_not_covered']['codes']} · code_sha == evidence_head -> "
            f"{C['code_sha_equals_evidence_head']['codes']} · HEAD != evidence_head -> "
            f"{C['head_not_evidence_head']['codes']} · merge_authorized senza coppia -> "
            f"{C['merge_authorized_without_pair']['codes']}"), ev, ok


# ------------------------------------------------------------------ C11
def c11():
    """Regressione del DELTA CORRETTIVO (Human Review 01). Questo delta e'
    reporting/evidence-only: se una sola di queste verifiche cade, non lo e'."""
    code_sha = bundle_provenance.runtime_code_sha(REPO)
    unchanged = bundle_provenance.runtime_code_unchanged_since(REPO, code_sha)
    core_head = git("rev-parse", "HEAD", cwd=CORE_PATH)
    core_status = git("status", "--porcelain", "--untracked-files=all")
    core_candidate = git("rev-parse", "HEAD", cwd=CORE_BRANCH_PATH)
    subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True, text=True)
    origin_main = git("rev-parse", "origin/main", cwd=REPO)
    p2 = sha256_file(P2_PATH)
    tags = {"core": git("tag", "--list", cwd=CORE_PATH).split(),
            "runtime": git("tag", "--list", cwd=REPO).split()}
    # nessuna credenziale, in nessun file del bundle
    scan = bundle_provenance.scan_credentials(BUNDLE)
    from runtime import provider_gate as pg
    checks = {
        "runtime_functional_diff_unchanged": unchanged["unchanged"],
        "runtime_code_sha_is_not_head": code_sha != git("rev-parse", "HEAD"),
        "core_candidate_identical": core_candidate == CORE_CANDIDATE_SHA,
        "core_main_unchanged": core_head == CANON["core_sha"] and core_status == "",
        "runtime_main_unchanged": origin_main == CANON["runtime_main_sha"],
        "p2_unchanged": p2 == CANON["p2_sha256"],
        "pin_unchanged": REQUIRED_CORE_SHA == CANON["core_sha"],
        "no_tags_created": not tags["core"] and not tags["runtime"],
        "real_provider_still_disabled": pg.ALLOWED_PROVIDER_MODE == "fake",
        "no_credential_material_in_bundle": scan["hits"] == [],
    }
    ok = all(checks.values())
    ev = evidence("C11", "corrective_delta_regression", {
        "runtime_code_sha": code_sha, "runtime_code_unchanged": unchanged,
        "core_candidate_sha": core_candidate, "core_candidate_expected": CORE_CANDIDATE_SHA,
        "core_main": {"head": core_head, "status_porcelain": core_status},
        "runtime_origin_main": origin_main, "p2_sha256": p2, "tags": tags,
        "credential_scan": scan,
        "checks": checks,
        "scope": "questo delta corregge SOLO evidence chain e reporting: nessuna riga "
                 "funzionale del Runtime, nessun merge, nessuna integrazione Core+Runtime"})
    failed = [k for k, v in checks.items() if not v]
    return (f"runtime_code_sha {code_sha[:12]} · diff funzionale Runtime dopo quel commit: "
            f"{unchanged['diff_bytes']} byte (invariato={unchanged['unchanged']}) · Core "
            f"candidate {core_candidate[:12]} == atteso · Core main {core_head[:12]} pulito · "
            f"Runtime origin/main {origin_main[:12]} · P2 {p2[:16]} · 0 tag · provider reale "
            f"disabilitato · 0 credenziali nel bundle · check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ report
def build_report() -> dict:
    suite = gate_report.summarize(RESULTS, policy=POLICY, expected_ids=EXPECTED_IDS)
    return readiness.build(RESULTS, suite, pair_facts=SHARED.get("pair_facts"))


def write_results(report: dict) -> dict:
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    payload = {"schema": "provider-boundary-gate-open-gap-closure/1",
               "required_core_sha": REQUIRED_CORE_SHA, "canonical": CANON,
               "results": RESULTS, "report": report}
    with open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    lines = ["# TEST RESULTS — PROVIDER BOUNDARY GATE / OPEN-GAP CLOSURE (2026-09-17)", "",
             "MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION.", "",
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


def cross_check_written_files(report: dict) -> dict:
    """I file scritti devono dire la STESSA cosa del report in memoria."""
    problems = []
    results = json.load(open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), encoding="utf-8"))
    rd = json.load(open(os.path.join(BUNDLE, "READINESS.json"), encoding="utf-8"))
    md = open(os.path.join(BUNDLE, "TEST_RESULTS.md"), encoding="utf-8").read()
    if results["report"]["phase_readiness"]["all_requirements_verified"] != \
            report["phase_readiness"]["all_requirements_verified"]:
        problems.append("RESULTS.json: all_requirements_verified divergente")
    if rd["gap_status"] != readiness.machine_readable_gaps(report):
        problems.append("READINESS.json: gap_status divergente")
    flag = str(report["phase_readiness"]["all_requirements_verified"]).lower()
    if f"`all_requirements_verified = {flag}`" not in md:
        problems.append("TEST_RESULTS.md: all_requirements_verified divergente")
    if report["phase_readiness"]["all_requirements_verified"] and \
            report["phase_readiness"]["open_requirements_blocking_all_verified"]:
        problems.append("report incoerente sfuggito a validate")
    return {"problems": problems, "ok": not problems}


def main() -> int:
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="pbg2_")
    try:
        record("C00", "Reality Lock canonico (Core/Runtime/pin/P2)",
               "Core 740ee979 clean · Runtime origin/main 0698279 · pin == Core · P2 637f3a80", c00)
        record("C01", "PHASE A: gap riprodotti prima di ogni fix",
               "5/5 REPRODUCED su Runtime canonico; premessa Core falsificata", c01)
        record("C02", "P-B02 + P-B01: composizione dentro lo spender isolato",
               "segreto e chiave confinati; forge/replay/binding/UID non autorizzato fail-closed; "
               "report dello spender applicato", lambda: c02(scratch))
        record("C03", "NG-04: meccanismo di freshness fail-closed e parametrico",
               "policy obbligatoria; stale/futuro/malformato/assente/replay rifiutati; confini esatti", c03)
        record("C04", "Legacy spend paths: inventario + modalita' Provider Boundary",
               "percorsi non governati del Runtime chiusi fail-closed; primitive del Core dichiarate aperte", c04)
        record("C05", "Orphan lease: meccanismo parametrico, policy non decisa",
               "policy obbligatoria; authority/evidenza/lease/fence/classe fail-closed; reclaim "
               "legittimo senza nuovi attempt; crash riparabile", c05)
        record("C06", "NG-05: decisione e delta additivo del Core su branch dedicato",
               "Core main senza API nuova; Runtime conservativo; branch dedicato 9/9 suite PASS", c06)
        record("C07", "Regressione R0-R1 (T01-T37) sul Runtime modificato",
               "0 FAIL", c07)
        record("C08", "P2 freeze e Core pin invariati a fine fase",
               "P2 before == after == canonico; Core main pulito a 740ee979", c08)
        record("C09", "Reporting: test suite result e phase readiness separati",
               "6 controprove sollevano; all_requirements_verified=false con gap aperti", c09)
        record("C10", "Catena di provenance del bundle: verificatore fail-closed",
               "12 controprove: copertura, extra, mismatch, MANIFEST non coperto, chiave "
               "ambigua, code_sha == evidence_head, HEAD divergente, merge_readiness",
               lambda: c10(scratch))
        record("C11", "Regressione del delta correttivo (reporting/evidence-only)",
               "diff funzionale Runtime invariato, Core candidate identico, main e P2 "
               "invariati, 0 tag, 0 credenziali", c11)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    report = build_report()
    write_results(report)
    xc = cross_check_written_files(report)
    print(readiness.console(report), flush=True)
    print(f"\ncross-check dei file scritti: {'OK' if xc['ok'] else xc['problems']}", flush=True)
    if not xc["ok"]:
        return 2
    return report["runner_exit"]


if __name__ == "__main__":
    sys.exit(main())
