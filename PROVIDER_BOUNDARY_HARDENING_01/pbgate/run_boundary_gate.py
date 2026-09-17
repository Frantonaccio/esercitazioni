#!/usr/bin/env python3
"""PROVIDER / EXECUTION BOUNDARY GATE 01 — matrice B00..B11 (2026-09-17).

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION.

Ogni test produce evidence/Bxx_*.json e una riga strutturata PASS | FAIL | BLOCKED
(tests/gate_report.py del gate storico: stessa authority di classificazione, inventario
canonico B00..B11, BLOCKED solo via GateBlocked per precondizione ambientale riconosciuta).
BLOCKED non e' PASS.

  B00  Reality Lock (Core HEAD/clean, Runtime origin/main, pin, P2 before)
  B01  P-B01 confine di privilegio REALE (UID distinti, DAC, SO_PEERCRED, no_new_privs)
  B02  P-B01 controllo: la modalita' same-UID resta BLOCKED_ENVIRONMENT
  B03  P-B02 reconciliation autenticata: happy path + binding fail-closed
  B04  P-B02 replay, altra operazione, non autenticata, audit snapshot
  B05  P-B04 snapshot exact-byte: byte persistiti, digest, immutabilita', binding, attestazione pre-send
  B06  P-B04 controprove: nested mutation, drift, reorder, sostituzione post-authorization, missing, corrupt, altra op
  B07  Legacy spend paths: inventario + interruttore fail-closed + hf_batch_runtime
  B08  Orphan RESERVED lease: riproduzione, classificazione, zero blind retry (resta STILL_OPEN)
  B09  Authorization / pricing authority: stato LAB, irraggiungibile dall'orchestrator
  B10  Regressione R0-R1 (tests/run_gate.py T01-T37) sul runtime modificato
  B11  P2 freeze after == before, Core pin/tree invariati, static checks
  B12  NG-03 provenance economica del rifiuto PRE-SUBMIT (corrective delta, HUMAN REVIEW 01)
  B13  Reporting: test suite result e phase readiness separati (corrective delta, HUMAN REVIEW 02)
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
CORE_PATH = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")
STATE_DIR = os.path.join(GATE01, "state")              # go_candidate confina gli store qui
EVIDENCE_DIR = os.path.join(BUNDLE, "evidence")
RAW_DIR = os.path.join(EVIDENCE_DIR, "raw")
REGRESSION_DIR = os.path.join(BUNDLE, "regression")
for p in (GATE01, BUNDLE):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("RUNTIME_GATE_ROOT", GATE01)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from runtime.core_pin import REQUIRED_CORE_SHA                       # noqa: E402
from tests import gate_report, static_checks, worker                 # noqa: E402
from pbgate import pb_worker, phase_readiness                        # noqa: E402

CANON = {"core_sha": "740ee979300fe20a9382992528604dee70cb2fcf",
         "runtime_main_sha": "39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e",
         "p2_sha256": "637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1"}
P2_PATH = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "P2_RUNTIME", "hf_batch.py")
EXPECTED_IDS = frozenset(f"B{i:02d}" for i in range(0, 14))
POLICY = {"B01": frozenset({"BLOCKED_ENVIRONMENT"}), "B09": frozenset({"BLOCKED_ENVIRONMENT"})}
CTX = multiprocessing.get_context("spawn")
RESULTS: list[dict] = []
SHARED: dict = {}
# UID LAB (numerici, senza voce in passwd): orchestrator, spender, terzo non autorizzato
UID_ORCH = int(os.environ.get("PB01_ORCH_UID", "65531"))
UID_SPENDER = int(os.environ.get("PB01_SPENDER_UID", "65532"))
UID_OTHER = int(os.environ.get("PB01_OTHER_UID", "65530"))
SETPRIV = ["setpriv", "--clear-groups", "--inh-caps=-all", "--bounding-set=-all", "--no-new-privs"]


# ------------------------------------------------------------------ utilita'
def db_for(name: str) -> str:
    p = os.path.join(STATE_DIR, f"pb_{name}.db")
    pb_worker.cleanup_db(p)
    return p


def evidence(test_id: str, name: str, payload: dict) -> str:
    path = os.path.join(EVIDENCE_DIR, f"{test_id}_{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    return os.path.relpath(path, BUNDLE)


def in_process(fn, *args, **kwargs) -> dict:
    q = CTX.Queue()
    p = CTX.Process(target=pb_worker._entry, args=(q, fn, args, kwargs))
    p.start()
    p.join(180)
    if p.is_alive():
        p.terminate()
        return {"ok": False, "error": "TIMEOUT_PROCESS"}
    return q.get(timeout=10)


def git(*args, cwd=CORE_PATH) -> str:
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=True).stdout.strip()


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


# ------------------------------------------------------------------ B00
def b00():
    core_head = git("rev-parse", "HEAD")
    core_status = git("status", "--porcelain", "--untracked-files=all")
    subprocess.run(["git", "-C", REPO, "fetch", "origin", "main"], capture_output=True, text=True)
    origin_main = git("rev-parse", "origin/main", cwd=REPO)
    runtime_head = git("rev-parse", "HEAD", cwd=REPO)
    descends = subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", CANON["runtime_main_sha"], runtime_head]).returncode == 0
    p2 = sha256_file(P2_PATH)
    SHARED["p2_before"] = p2
    d = {"core_head": core_head, "core_status_porcelain": core_status, "runtime_origin_main": origin_main,
         "runtime_head": runtime_head, "runtime_head_descends_from_canonical": descends,
         "required_core_sha": REQUIRED_CORE_SHA, "p2_sha256_before": p2, "canonical": CANON,
         "runtime_branch": git("branch", "--show-current", cwd=REPO)}
    ok = (core_head == CANON["core_sha"] and core_status == "" and origin_main == CANON["runtime_main_sha"]
          and descends and REQUIRED_CORE_SHA == CANON["core_sha"] and p2 == CANON["p2_sha256"])
    ev = evidence("B00", "reality_lock", d)
    return (f"Core {core_head[:12]} clean={core_status == ''} · Runtime origin/main {origin_main[:12]} "
            f"(HEAD {runtime_head[:12]} discende={descends}) · pin {REQUIRED_CORE_SHA[:12]} · P2 {p2[:16]}"), ev, ok


# ------------------------------------------------------------------ B01
def _run_as(uid: int, argv: list[str], env: dict, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(SETPRIV + [f"--reuid={uid}", f"--regid={uid}", "env", *[f"{k}={v}" for k, v in env.items()],
                                     *argv], capture_output=True, text=True, timeout=timeout)


def _mkdir_owned(path: str, uid: int, mode: int) -> None:
    os.makedirs(path, exist_ok=True)
    os.chown(path, uid, uid)
    os.chmod(path, mode)


def b01(scratch: str):
    precond = {"euid": os.geteuid(), "setpriv": shutil.which("setpriv"), "cap_eff": hex(caps_eff()),
               "cap_setuid": bool(caps_eff() & (1 << 7)), "cap_setgid": bool(caps_eff() & (1 << 6)),
               "cap_chown": bool(caps_eff() & (1 << 0))}
    root = os.path.join(STATE_DIR, "pb01")
    shutil.rmtree(root, ignore_errors=True)
    can = precond["euid"] == 0 and precond["setpriv"] and precond["cap_setuid"] and precond["cap_setgid"] and precond["cap_chown"]
    if not can:
        ev = evidence("B01", "privilege_boundary_uid", {"precondition": precond, "status": "BLOCKED",
                                                        "reason_code": "BLOCKED_ENVIRONMENT",
                                                        "requirement_verified": False})
        raise gate_report.GateBlocked("BLOCKED_ENVIRONMENT",
                                      f"l'ambiente non consente UID distinti (euid={precond['euid']}, setpriv={precond['setpriv']}, "
                                      f"caps={precond['cap_eff']}): P-B01 non verificabile qui, nessun PASS simulato", ev)
    # ---- layout: ogni dominio nel suo UID; il socket in una dir dello spender, traversabile ----
    spender = os.path.join(root, "spender")
    ipc = os.path.join(root, "ipc")
    orch = os.path.join(root, "orch")
    _mkdir_owned(root, 0, 0o755)
    _mkdir_owned(spender, UID_SPENDER, 0o700)
    _mkdir_owned(ipc, UID_SPENDER, 0o755)
    _mkdir_owned(orch, UID_ORCH, 0o700)
    db = os.path.join(spender, "store.db")
    secret_dir = os.path.join(spender, "secret")
    sock = os.path.join(ipc, "spender.sock")
    ready = os.path.join(ipc, "ready.json")
    common_env = {"PYTHONDONTWRITEBYTECODE": "1", "RUNTIME_GATE_ROOT": GATE01, "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                  "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"}
    daemon_log = open(os.path.join(RAW_DIR, "B01_spender_daemon.log"), "w", encoding="utf-8")
    daemon = subprocess.Popen(
        SETPRIV + [f"--reuid={UID_SPENDER}", f"--regid={UID_SPENDER}", "env", *[f"{k}={v}" for k, v in common_env.items()],
                   f"HOME={spender}", sys.executable, os.path.join(BUNDLE, "pbgate", "spender_daemon.py"),
                   "--socket", sock, "--db", db, "--secret-dir", secret_dir, "--core", CORE_PATH,
                   "--canary-home", os.path.join(spender, "canary"), "--allowed-peer-uid", str(UID_ORCH),
                   "--ready-file", ready], stdout=daemon_log, stderr=subprocess.STDOUT)
    info = None
    try:
        for _ in range(300):
            if os.path.exists(ready):
                info = json.load(open(ready, encoding="utf-8"))
                break
            if daemon.poll() is not None:
                break
            time.sleep(0.1)
        if info is None:
            daemon_log.close()
            log = open(os.path.join(RAW_DIR, "B01_spender_daemon.log"), encoding="utf-8").read()
            ev = evidence("B01", "privilege_boundary_uid", {"precondition": precond, "daemon_failed": True, "log": log})
            return f"daemon spender non avviato (uid {UID_SPENDER}): {log[-300:]}", ev, False
        probe_argv = [sys.executable, os.path.join(BUNDLE, "pbgate", "orchestrator_probe.py"), "--socket", sock,
                      "--secret-path", info["secret_path"], "--db", db, "--core", CORE_PATH,
                      "--spender-pid", str(info["pid"]), "--own-db", os.path.join(orch, "own.db"),
                      "--worker-code", os.path.join(GATE01, "tests", "boundary_mock.py"),
                      os.path.join(BUNDLE, "pbgate", "spender_daemon.py"), os.path.join(GATE01, "runtime", "go_candidate.py")]
        r_full = _run_as(UID_ORCH, probe_argv + ["--mode", "full"], {**common_env, "HOME": orch})
        r_other = _run_as(UID_OTHER, probe_argv + ["--mode", "peer_only"], {**common_env, "HOME": os.path.join(scratch, "other_home")})
        r_stop = _run_as(UID_ORCH, probe_argv + ["--mode", "stop"], {**common_env, "HOME": orch})
        daemon.wait(60)
    finally:
        if daemon.poll() is None:
            daemon.terminate()
            daemon.wait(10)
        daemon_log.close()

    def parse(r):
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:                                                       # noqa: BLE001
            return {"parse_error": True, "stdout": r.stdout[-2000:], "stderr": r.stderr[-2000:], "rc": r.returncode}
    full, other, stop = parse(r_full), parse(r_other), parse(r_stop)
    # ---- verifiche lato operatore (root): stato reale nello store dello spender ----
    rows = pb_worker._rows(db) if os.path.exists(db) else []
    st_secret = os.stat(info["secret_path"])
    st_db = os.stat(db)
    snap_dir = db + ".snapshots"
    snapshots = sorted(os.listdir(snap_dir)) if os.path.isdir(snap_dir) else []
    attempts = full.get("attempts", {})
    same_uid = (full.get("uid") == info["uid"])
    status, reason = gate_report.t29_status(same_uid, attempts)
    P = full.get("protocol", {}) if isinstance(full.get("protocol"), dict) else {}
    extra = full.get("extra_probes", {})
    checks = {
        "uids_distinct": full.get("uid") == UID_ORCH and info["uid"] == UID_SPENDER and other.get("uid") == UID_OTHER,
        "orchestrator_no_caps": full.get("caps", {}).get("CapEff") == "0000000000000000" and full.get("no_new_privs") == "1",
        "secret_owned_by_spender_0600": st_secret.st_uid == UID_SPENDER and stat.S_IMODE(st_secret.st_mode) == 0o600,
        "store_owned_by_spender": st_db.st_uid == UID_SPENDER,
        "t29_canonical_probes_all_blocked": status == "PASS",
        "extra_probes_blocked": all(str(extra.get(k, "")).startswith("BLOCKED") for k in
                                    ("issue_quote_on_worker_store", "kill_spender", "read_spender_proc_environ",
                                     "list_secret_dir", "read_snapshot_ledger")),
        "own_store_spend_is_not_spender_account": (extra.get("own_store_dispatch", {}).get("state") == "SUCCEEDED"
                                                    and extra.get("own_store_dispatch", {}).get("provider_account") != info["account_id"]),
        "protocol_first_spend_governed": (P.get("first", {}).get("state") == "SUCCEEDED"
                                          and P.get("first", {}).get("provider_account") == info["account_id"]
                                          and P.get("first", {}).get("governance") == "GOVERNED_LAB"
                                          and (P.get("first", {}).get("payload_snapshot") or {}).get("send_verified") is True),
        "protocol_resume_no_new_submit": P.get("resume", {}).get("outcome") == "RESUMED/SUCCEEDED" and P.get("resume", {}).get("submits") == 1,
        "protocol_refusals": (str(P.get("no_intent", {}).get("refused", "")).startswith("PROTOCOL: INTENT_REQUIRED")
                              and str(P.get("amount_from_client", {}).get("refused", "")).startswith("PROTOCOL")
                              and str(P.get("shell", {}).get("refused", "")).startswith("PROTOCOL")),
        "whoami_peer_authenticated": P.get("whoami", {}).get("uid") == UID_SPENDER and P.get("whoami", {}).get("peer_uid") == UID_ORCH,
        "third_uid_refused": (other.get("protocol") or [{}])[0].get("refused") == "PEER_UID_NOT_AUTHORIZED",
        "secret_never_in_channel": full.get("secret_in_channel") is False and "FAKE_SPENDER_SECRET" not in json.dumps([full, other, stop]),
        "sentinel_zero_violations": (stop.get("protocol") or [{}])[0].get("violations") == [],
        "spender_store_one_succeeded_row": len(rows) == 1 and rows[0]["state"] == "SUCCEEDED" and rows[0]["provider_account"] == info["account_id"],
        "snapshot_ledger_in_spender_domain": bool(snapshots) and os.stat(snap_dir).st_uid == UID_SPENDER,
    }
    ok = all(checks.values())
    ev = evidence("B01", "privilege_boundary_uid", {
        "precondition": precond, "uids": {"orchestrator": UID_ORCH, "spender": UID_SPENDER, "other": UID_OTHER},
        "daemon": info, "probe_full": full, "probe_other_uid": other, "stop": stop,
        "spender_store_rows": rows, "spender_snapshot_ledger": snapshots,
        "secret_stat": {"uid": st_secret.st_uid, "mode": oct(stat.S_IMODE(st_secret.st_mode))},
        "attempts": attempts, "t29_status": {"status": status, "reason_code": reason, "same_uid": same_uid},
        "checks": checks, "status": "PASS" if ok else "FAIL", "requirement_verified": ok,
        "scope_note": "confine LAB con segreto fittizio e FakeAdapter; kernel DAC fra UID non privilegiati; "
                      "il gate (operatore) gira come root: e' il ruolo dell'installatore, non dell'orchestrator"})
    failed = [k for k, v in checks.items() if not v]
    return (f"uid orchestrator {full.get('uid')} (caps {full.get('caps', {}).get('CapEff')}, nnp={full.get('no_new_privs')}) vs spender {info['uid']} · "
            f"probe canoniche: {attempts} -> {status}/{reason} · terzo uid -> {(other.get('protocol') or [{}])[0].get('refused')} · "
            f"prima spesa via socket -> {P.get('first', {}).get('state')} conto {P.get('first', {}).get('provider_account')} · "
            f"resume -> {P.get('resume', {}).get('outcome')} · check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ B02
def b02():
    all_blocked = {k: "BLOCKED (PermissionError)" for k in gate_report.T29_EXPECTED_ATTEMPT_KEYS}
    all_bypass = {k: "BYPASS_POSSIBLE" for k in gate_report.T29_EXPECTED_ATTEMPT_KEYS}
    three = dict(list(all_blocked.items())[:3])
    d = {"same_uid_all_blocked": gate_report.t29_status(True, all_blocked),
         "same_uid_all_bypass": gate_report.t29_status(True, all_bypass),
         "distinct_uid_all_blocked": gate_report.t29_status(False, all_blocked),
         "distinct_uid_three_of_four": gate_report.t29_status(False, three),
         "distinct_uid_one_bypass": gate_report.t29_status(False, {**all_blocked, "read_worker_secret": "BYPASS_POSSIBLE"})}
    hist = json.load(open(os.path.join(GATE01, "evidence", "T29_boundary_privilege_isolation.json"), encoding="utf-8"))
    d["historic_T29"] = {"status": hist.get("status"), "reason_code": hist.get("reason_code"), "uids": hist.get("uids")}
    reg = SHARED.get("regression_T29")
    d["regression_T29_this_phase"] = reg
    ok = (d["same_uid_all_blocked"] == ("BLOCKED", "BLOCKED_ENVIRONMENT") and d["same_uid_all_bypass"] == ("BLOCKED", "BLOCKED_ENVIRONMENT")
          and d["distinct_uid_all_blocked"] == ("PASS", "VERIFIED") and d["distinct_uid_three_of_four"][0] == "FAIL"
          and d["distinct_uid_one_bypass"][0] == "FAIL" and hist.get("reason_code") == "BLOCKED_ENVIRONMENT"
          and (reg is None or (reg.get("status") == "BLOCKED" and reg.get("reason_code") == "BLOCKED_ENVIRONMENT")))
    ev = evidence("B02", "same_uid_control", d)
    return (f"same-uid -> BLOCKED_ENVIRONMENT qualunque probe · uid distinti: 4/4 BLOCKED -> PASS, 3/4 o 1 bypass -> FAIL · "
            f"T29 storico {hist.get('reason_code')} · T29 regressione {reg and reg.get('reason_code')}"), ev, ok


# ------------------------------------------------------------------ B03 / B04
def _reconcile_call_sites() -> list:
    """Chiamate REALI a `.reconcile(` in runtime/ (AST: i docstring non contano), con la
    funzione che le contiene. Ordinate, deduplicate."""
    import ast
    sites = set()
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
                        and node.func.attr == "reconcile":
                    sites.add((name, fn.name))
    return sorted(sites)


def _unknown_job(db: str, prompt: str, op: str) -> dict:
    r = in_process(pb_worker.go_governed, db, CORE_PATH, prompt, op, adapter_kind="submit_unknown")
    row = next((x for x in pb_worker._rows(db) if x["operation_id"] == op), None)
    return {"go": r, "row": row}


def _fields(row: dict, **over) -> dict:
    f = dict(attempt_token=row["attempt_token"], payload_digest=row["payload_digest"],
             operation_id=row["operation_id"], job_id=row["job_id"])
    f.update(over)
    return f


def b03():
    db = db_for("b03")
    secret = "LAB_SPENDER_SECRET_b03"
    u1 = _unknown_job(db, "b03 unknown 1", "T31:b03a")
    u2 = _unknown_job(db, "b03 unknown 2", "T31:b03b")
    r1, r2 = u1["row"], u2["row"]
    assert r1 and r1["state"] == "SUBMIT_UNKNOWN" and r2 and r2["state"] == "SUBMIT_UNKNOWN", (u1, u2)
    mk = lambda **kw: in_process(pb_worker.make_report, secret, "fake", "fake_acct_a", **kw)     # noqa: E731
    rec = lambda rep, **kw: in_process(pb_worker.reconcile, db, CORE_PATH, secret, rep, **kw)   # noqa: E731
    C = {}
    # controprove sul job u2 (deve restare SUBMIT_UNKNOWN dopo ognuna)
    C["wrong_account_signed_by_owner"] = rec(mk(fields=_fields(r2, provider_account="acct_stranger")), job_id=r2["job_id"])
    C["wrong_account_key"] = rec(mk(fields=_fields(r2), sign_with={"secret": secret, "provider": "fake", "account": "acct_stranger"}), job_id=r2["job_id"])
    C["wrong_provider_in_report"] = rec(mk(fields=_fields(r2, provider="higgsfield")), job_id=r2["job_id"])
    C["wrong_provider_adapter"] = rec(mk(fields=_fields(r2)), job_id=r2["job_id"], adapter_name="fake_b", key_provider="fake")
    C["wrong_provider_adapter_own_key"] = rec(mk(fields=_fields(r2)), job_id=r2["job_id"], adapter_name="fake_b")
    C["wrong_adapter_account"] = rec(mk(fields=_fields(r2)), job_id=r2["job_id"], adapter_account="fake_acct_b", key_account="fake_acct_a")
    C["wrong_job_unknown"] = rec(mk(fields=_fields(r2, job_id="res_nonexistent_1")), job_id="res_nonexistent_1")
    C["wrong_job_other_job_token"] = rec(mk(fields=_fields(r2, attempt_token=r1["attempt_token"])), job_id=r2["job_id"])
    C["wrong_attempt_token"] = rec(mk(fields=_fields(r2, attempt_token="att_bogus")), job_id=r2["job_id"])
    C["wrong_payload_digest"] = rec(mk(fields=_fields(r2, payload_digest="0" * 64)), job_id=r2["job_id"])
    C["wrong_operation"] = rec(mk(fields=_fields(r2, operation_id="T31:other")), job_id=r2["job_id"])
    C["unauthenticated_no_signature"] = rec(mk(fields=_fields(r2), tamper={"signature": ""}), job_id=r2["job_id"])
    C["unauthenticated_wrong_key"] = rec(mk(fields=_fields(r2), sign_with={"secret": "NOT_THE_SECRET", "provider": "fake", "account": "fake_acct_a"}), job_id=r2["job_id"])
    C["tampered_after_signing"] = rec(mk(fields=_fields(r2), tamper={"state": "FAILED"}), job_id=r2["job_id"])
    C["target_state_not_reportable"] = rec(mk(fields=_fields(r2, state="RESERVED")), job_id=r2["job_id"])
    C["malformed_report"] = rec({"source": "x", "remote_ref": "y"}, job_id=r2["job_id"])
    expected = {"wrong_account_signed_by_owner": "ACCOUNT_MISMATCH", "wrong_account_key": "UNAUTHENTICATED",
                "wrong_provider_in_report": "PROVIDER_MISMATCH", "wrong_provider_adapter": "ADAPTER_NOT_OWNER",
                "wrong_provider_adapter_own_key": "UNAUTHENTICATED",
                "wrong_adapter_account": "ADAPTER_NOT_OWNER", "wrong_job_unknown": "JOB_UNKNOWN",
                "wrong_job_other_job_token": "ATTEMPT_TOKEN_MISMATCH", "wrong_attempt_token": "ATTEMPT_TOKEN_MISMATCH",
                "wrong_payload_digest": "PAYLOAD_DIGEST_MISMATCH", "wrong_operation": "OPERATION_MISMATCH",
                "unauthenticated_no_signature": "UNAUTHENTICATED", "unauthenticated_wrong_key": "UNAUTHENTICATED",
                "tampered_after_signing": "UNAUTHENTICATED", "target_state_not_reportable": "TARGET_STATE_NOT_ALLOWED",
                "malformed_report": "REPORT_MALFORMED"}
    codes = {k: v.get("code") for k, v in C.items()}
    unchanged = {k: v.get("journal_unchanged") for k, v in C.items()}
    # happy path su u1: report valido -> SUCCEEDED, provider_job_id scoperto, evidenza registrata
    happy = rec(mk(fields=_fields(r1)), job_id=r1["job_id"])
    recon_anoms = [a for a in happy.get("anomalies", []) if a["kind"] == "RECONCILIATION"]
    # dopo il rifiuto di tutte le controprove, u2 e' ancora riconciliabile con un report valido
    happy2 = rec(mk(fields=_fields(r2, state="FAILED")), job_id=r2["job_id"])
    ok = (codes == expected and all(unchanged.values())
          and happy.get("ok") and happy.get("state") == "SUCCEEDED" and happy["after"]["provider_job_id"] == "pv_remote_1"
          and recon_anoms and recon_anoms[-1]["detail"]["evidence"].get("signature_verified") is True
          and recon_anoms[-1]["detail"]["evidence"].get("source") == "LAB_AUTHENTICATED_PROVIDER_REPORT"
          and happy2.get("ok") and happy2.get("state") == "FAILED")
    ev = evidence("B03", "reconciliation_authenticated", {"jobs": {"u1": u1, "u2": u2}, "counterproofs": C, "codes": codes,
                                                          "expected_codes": expected, "journal_unchanged": unchanged,
                                                          "happy": happy, "happy_after_refusals": happy2})
    pb_worker.cleanup_db(db)
    mism = {k: (codes[k], expected[k]) for k in expected if codes.get(k) != expected[k]}
    return (f"{len(expected)} controprove fail-closed (journal invariato: {all(unchanged.values())}) · "
            f"scarti: {mism or 'nessuno'} · report valido -> {happy.get('state')} (provider_job_id {happy.get('after', {}).get('provider_job_id')}, "
            f"evidenza firmata registrata) · u2 dopo i rifiuti -> {happy2.get('state')}"), ev, ok


def b04():
    db = db_for("b04")
    secret = "LAB_SPENDER_SECRET_b04"
    u3 = _unknown_job(db, "b04 unknown 3", "T31:b04c")
    u4 = _unknown_job(db, "b04 unknown 4", "T31:b04d")
    r3, r4 = u3["row"], u4["row"]
    assert r3 and r4, (u3, u4)
    mk = lambda **kw: in_process(pb_worker.make_report, secret, "fake", "fake_acct_a", **kw)     # noqa: E731
    rec = lambda rep, **kw: in_process(pb_worker.reconcile, db, CORE_PATH, secret, rep, **kw)   # noqa: E731
    D = {}
    # 1. replay: report N1 -> RUNNING; poll successivo riporta incertezza; stesso report -> REPLAY
    n1 = mk(fields=_fields(r3, state="RUNNING"))
    D["first_apply"] = rec(n1, job_id=r3["job_id"])
    D["back_to_unknown"] = in_process(pb_worker.put_state, db, CORE_PATH, r3["job_id"], "SUBMIT_UNKNOWN")
    D["replay_same_nonce"] = rec(n1, job_id=r3["job_id"])
    D["fresh_report_after_replay"] = rec(mk(fields=_fields(r3, state="SUCCEEDED")), job_id=r3["job_id"])
    # 2. risposta VALIDA ma di un'altra operazione/job: firmata correttamente per u4, applicata a... u4 e' la
    #    destinazione dichiarata dal chiamante? no: il chiamante vuole riconciliare u3 -> JOB_MISMATCH
    valid_u4 = mk(fields=_fields(r4))
    D["valid_report_other_job_applied_to_u3"] = rec(valid_u4, job_id=r3["job_id"])
    # 3. audit snapshot P-B04: job creato bypassando il runtime (nessuno snapshot) -> SNAPSHOT_AUDIT_FAILED
    raw = in_process(worker.store_call, db, CORE_PATH, "reserve_or_get_live_by_prompt_op", "b04 raw", "T31:raw")
    raw_row = next((x for x in pb_worker._rows(db) if x["operation_id"] == "T31:raw"), None)
    D["raw_reserved_no_intent"] = rec(mk(fields=_fields(raw_row, attempt_token="att_x", payload_digest="1" * 64)), job_id=raw_row["job_id"]) if raw_row else {"error": "no raw row"}
    # 3b. job con intento ma snapshot rimosso dopo l'invio -> audit fallisce
    snap_dir = db + ".snapshots"
    removed = []
    for f in os.listdir(snap_dir):
        if r4["attempt_token"] in f and f.endswith(".bind.json"):
            os.remove(os.path.join(snap_dir, f))
            removed.append(f)
    D["snapshot_bind_removed_then_reconcile"] = rec(mk(fields=_fields(r4)), job_id=r4["job_id"])
    D["same_without_snapshot_audit"] = rec(mk(fields=_fields(r4)), job_id=r4["job_id"], with_snapshot=False)
    # 4. controprova storica: il percorso raw del Core resta accettante (e' il gap riprodotto), ma il runtime non lo usa
    D["raw_core_reconcile_still_permissive"] = in_process(pb_worker.raw_reconcile_unauthenticated, db, CORE_PATH,
                                                           raw_row["job_id"], "FAILED") if raw_row else None
    runtime_callers = _reconcile_call_sites()
    # Invariante: nel runtime `reconcile` e' chiamato SOLO dai due percorsi con provenance
    # esplicita e dichiarata (report autenticato P-B02; rifiuto pre-submit NG-03).
    expected_callers = [("go_candidate.py", "_refuse_pre_submit"), ("reconciliation.py", "reconcile_authenticated")]
    ok = (D["first_apply"].get("state") == "RUNNING" and D["back_to_unknown"].get("state") == "SUBMIT_UNKNOWN"
          and D["replay_same_nonce"].get("code") == "REPLAY" and D["replay_same_nonce"].get("journal_unchanged")
          and D["fresh_report_after_replay"].get("state") == "SUCCEEDED"
          and D["valid_report_other_job_applied_to_u3"].get("code") == "JOB_MISMATCH"
          and D["raw_reserved_no_intent"].get("code") == "OWNERSHIP_INCOMPLETE"
          and D["snapshot_bind_removed_then_reconcile"].get("code") == "SNAPSHOT_AUDIT_FAILED"
          and D["same_without_snapshot_audit"].get("ok") is True
          and runtime_callers == expected_callers)
    ev = evidence("B04", "reconciliation_replay_cross_operation", {"jobs": {"u3": u3, "u4": u4, "raw": raw_row}, "steps": D,
                                                                   "removed_snapshot_files": removed,
                                                                   "runtime_reconcile_call_sites": runtime_callers,
                                                                   "expected_call_sites": expected_callers})
    pb_worker.cleanup_db(db)
    return (f"N1 -> {D['first_apply'].get('state')} · incertezza -> replay N1 -> {D['replay_same_nonce'].get('code')} · nuovo report -> "
            f"{D['fresh_report_after_replay'].get('state')} · report valido di altro job -> {D['valid_report_other_job_applied_to_u3'].get('code')} · "
            f"RESERVED senza intento -> {D['raw_reserved_no_intent'].get('code')} · snapshot bind rimosso -> "
            f"{D['snapshot_bind_removed_then_reconcile'].get('code')} · chiamanti runtime di reconcile (AST): {runtime_callers}"), ev, ok


# ------------------------------------------------------------------ B05 / B06
def b05():
    db = db_for("b05")
    first = in_process(pb_worker.go_governed, db, CORE_PATH, "b05 bytes", "T32:b05")
    insp = in_process(pb_worker.ledger_inspect, db, CORE_PATH, "b05 bytes", first.get("job_id"))
    listing_after_first = in_process(pb_worker.ledger_listing, db)
    resume = in_process(pb_worker.resume_only, db, CORE_PATH, "b05 bytes", "T32:b05")
    listing_after_resume = in_process(pb_worker.ledger_listing, db)
    api = in_process(pb_worker.ledger_api_counterproofs, db, CORE_PATH, "b05 bytes", first.get("job_id"))
    snap = first.get("payload_snapshot") or {}
    ok = (first.get("state") == "SUCCEEDED" and first.get("transport_sent_count") == 1
          and first.get("transport_guarded") == "SnapshotGuardedTransport"
          and snap.get("send_verified") is True and snap.get("digest") == first["persisted"]["payload_digest"]
          and insp.get("ok") and insp["persisted_equals_recomputed_canonical"] and insp["sha256_of_persisted_equals_job_digest"]
          and insp["persisted_mode"] == "0o444" and insp["seal"]["operation_id"] == "T32:b05"
          and insp["seal"]["provider"] == "fake" and insp["seal"]["provider_account"] == "fake_acct_a"
          and insp["bind"]["job_id"] == first["job_id"] and insp["bind"]["attempt_token"] == first["persisted"]["attempt_token"]
          and insp["send_attestation"] and insp["send_attestation"]["exact_bytes_equal"] is True
          and insp["audit"]["ok"] and insp["audit"]["send_attested"]
          and resume.get("outcome") == "RESUMED/SUCCEEDED" and resume.get("submits") == 0
          and listing_after_resume["files"] == listing_after_first["files"] and len(listing_after_first["files"]) == 4
          and api.get("ok") and api["overwrite_bin_write_once"]["refused"] and api["seal_idempotent_same_context"]["refused"] is False
          and api["other_operation_seal_missing"].get("code") == "SEAL_MISSING"
          and api["wrong_attempt_token"].get("code") == "ATTEMPT_NOT_BOUND"
          and api["second_send_same_attempt"].get("code") == "SEND_ALREADY_ATTESTED"
          and api["reordered_bytes"].get("code") == "SNAPSHOT_MISSING"
          and api["seal_conflict_other_spec_key"].get("code") == "SEAL_CONFLICT"
          and api["audit_other_operation"]["ok"] is False)
    ev = evidence("B05", "snapshot_exact_byte", {"first": first, "inspect": insp, "listing_after_first": listing_after_first,
                                                 "resume": resume, "listing_after_resume": listing_after_resume, "api_counterproofs": api})
    pb_worker.cleanup_db(db)
    return (f"go -> {first.get('state')} (1 invio, trasporto {first.get('transport_guarded')}) · byte persistiti == canonici ricalcolati: "
            f"{insp.get('persisted_equals_recomputed_canonical')} · sha256(file)==digest job: {insp.get('sha256_of_persisted_equals_job_digest')} · "
            f"mode {insp.get('persisted_mode')} · seal/bind/send presenti ({len(listing_after_first.get('files') or [])} file) · resume: 0 nuovi file · "
            f"API: overwrite rifiutato, altra op -> {api.get('other_operation_seal_missing', {}).get('code')}, token errato -> "
            f"{api.get('wrong_attempt_token', {}).get('code')}, 2o invio -> {api.get('second_send_same_attempt', {}).get('code')}, reorder -> "
            f"{api.get('reordered_bytes', {}).get('code')}"), ev, ok


def b06():
    db = db_for("b06")
    R = {}
    for kind, op in (("drift_nested", "T32:nested"), ("drift_top", "T32:drift"), ("reorder", "T32:reorder"),
                     ("substitute", "T32:subst"), ("snapshot_missing", "T32:missing"), ("snapshot_corrupt", "T32:corrupt")):
        R[kind] = in_process(pb_worker.go_governed, db, CORE_PATH, f"b06 {kind}", op, adapter_kind=kind)
    state = pb_worker.read_state(db)
    rows = {r["operation_id"]: r for r in state["rows"]}
    anoms = {}
    for a in state["anomalies"]:
        anoms.setdefault(a["job_id"], []).append(a["kind"])
    ledger = {}
    for e in state["ledger"]:
        ledger.setdefault(e["job_id"], []).append((e["kind"], e["units"], e["source"]))

    # NG-03 (HUMAN REVIEW 01): la provenance del settlement 0 dipende da CHI ha attestato che
    # nessun invio e' avvenuto. Rifiuto a mark_submitting -> verifica del runtime; rifiuto dentro
    # adapter.submit con marcatore invariato -> attestazione del trasporto letta dal Core.
    # Il dettaglio della provenance pre-submit e' verificato da B12.
    PRE_SUBMIT = "RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED"
    TRANSPORT = "TRANSPORT_ATTESTED_NOT_SENT"

    def refused_before_send(kind, op, expect_anomaly, source=TRANSPORT):
        r, row = R[kind], rows.get(op)
        if not row:
            return False
        return (r.get("ok") is False and r.get("transport_sent_count") == 0
                and row["state"] == "FAILED" and row["settled_units"] == 0
                and row["settlement_source"] == source
                and expect_anomaly in anoms.get(row["job_id"], [])
                and any(k == "SETTLE" and u == 0 and src == source
                        for k, u, src in ledger.get(row["job_id"], [])))
    checks = {
        "nested_mutation_refused_pre_submit": refused_before_send("drift_nested", "T32:nested", "SNAPSHOT_REFUSED_PRE_SUBMIT", PRE_SUBMIT)
                                              and "SERIALIZATION_DRIFT" in str(R["drift_nested"].get("message")),
        "serialization_drift_refused_pre_submit": refused_before_send("drift_top", "T32:drift", "SNAPSHOT_REFUSED_PRE_SUBMIT", PRE_SUBMIT),
        "field_reorder_refused_before_send": refused_before_send("reorder", "T32:reorder", "REFUSED_BEFORE_SEND")
                                             and "SNAPSHOT_MISSING" in str(R["reorder"].get("message")),
        "substituted_after_authorization_refused_before_send": refused_before_send("substitute", "T32:subst", "REFUSED_BEFORE_SEND")
                                                                and "SNAPSHOT_MISSING" in str(R["substitute"].get("message")),
        "snapshot_missing_refused_before_send": refused_before_send("snapshot_missing", "T32:missing", "REFUSED_BEFORE_SEND")
                                                and "SNAPSHOT_MISSING" in str(R["snapshot_missing"].get("message")),
        "digest_mismatch_refused_before_send": refused_before_send("snapshot_corrupt", "T32:corrupt", "REFUSED_BEFORE_SEND")
                                               and "DIGEST_MISMATCH" in str(R["snapshot_corrupt"].get("message")),
        "no_submit_unknown_anywhere": all(r["state"] != "SUBMIT_UNKNOWN" for r in state["rows"]),
        "drift_cases_never_bound": all(not any(f.endswith(".bind.json") and rows[op]["attempt_token"] and rows[op]["attempt_token"] in f
                                               for f in os.listdir(db + ".snapshots")) for op in ("T32:nested", "T32:drift") if rows.get(op)),
    }
    # controllo positivo: dopo tutti i rifiuti, un adapter corretto sulla stessa spec spende normalmente
    R["control_ok"] = in_process(pb_worker.go_governed, db, CORE_PATH, "b06 drift_top", "T32:control")
    checks["control_correct_adapter_succeeds"] = R["control_ok"].get("state") == "SUCCEEDED" and R["control_ok"].get("transport_sent_count") == 1
    pre = json.load(open(os.path.join(EVIDENCE_DIR, "pre_fix", "reproduction_baseline.json"), encoding="utf-8"))["P-B04"]["drift_case"]
    checks["pre_fix_same_case_reached_send_marker"] = pre["transport_sent_count"] == 1 and pre["job"]["state"] == "SUBMIT_UNKNOWN"
    checks["drift_cases_never_claim_transport_attestation"] = all(
        TRANSPORT not in json.dumps(anoms.get(rows[op]["job_id"], [])) and rows[op]["settlement_source"] == PRE_SUBMIT
        for op in ("T32:nested", "T32:drift") if rows.get(op))
    ok = all(checks.values())
    ev = evidence("B06", "snapshot_counterproofs", {"results": R, "rows": state["rows"], "anomalies": state["anomalies"],
                                                    "ledger": state["ledger"], "checks": checks,
                                                    "pre_fix_reference": pre})
    pb_worker.cleanup_db(db)
    failed = [k for k, v in checks.items() if not v]
    return (f"6 controprove: tutte rifiutate PRIMA del marcatore (sent_count 0), FAILED con settlement 0 · "
            f"provenance: drift -> {PRE_SUBMIT} (verifica runtime), reorder/sostituzione/missing/corrupt -> {TRANSPORT} (Core) · "
            f"pre-fix lo stesso caso 'substitute' raggiungeva l'invio (sent_count {pre['transport_sent_count']}, {pre['job']['state']}) · "
            f"adapter corretto dopo i rifiuti -> {R['control_ok'].get('state')} · check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ B07
def _static_inventory() -> dict:
    """Ricerca REALE (testo + AST) dei punti che possono produrre submit/spend nel repository."""
    import ast
    import re
    inv = []
    pats = {"run_job_call": re.compile(r"\brun_job\("), "adapter_submit": re.compile(r"\.submit\("),
            "subprocess": re.compile(r"\bsubprocess\.(run|Popen|call|check_output)\("),
            "higgsfield_cli": re.compile(r"\bhiggsfield\b"), "go_candidate_go": re.compile(r"go_candidate\.go\(|\bgo\(inputs"),
            "reserve_or_get_live": re.compile(r"reserve_or_get_live\("), "reconcile": re.compile(r"\.reconcile\(")}
    roots = [os.path.join(GATE01, "runtime"), os.path.join(GATE01, "tests"), os.path.join(BUNDLE, "pbgate"),
             os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "P2_RUNTIME"),
             os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "LAB")]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for f in sorted(os.listdir(root)):
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            src = open(path, encoding="utf-8").read()
            hits = {}
            for name, pat in pats.items():
                lines = [i for i, line in enumerate(src.splitlines(), 1)
                         if pat.search(line) and not line.strip().startswith("#")]
                if lines:
                    hits[name] = lines
            if hits:
                inv.append({"file": os.path.relpath(path, REPO), "hits": hits, "sha256": sha256_file(path)[:16]})
    core_hits = []
    for rel in ("transport/pipeline.py", "adapters/fake.py", "registry/reservations.py"):
        src = open(os.path.join(CORE_PATH, rel), encoding="utf-8").read()
        core_hits.append({"file": f"creative-os/{rel}",
                          "defines": [n.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)
                                      and n.name in ("run_job", "resume_job", "submit", "send", "reconcile", "reserve_or_get_live")]})
    return {"repo_hits": inv, "core_primitives": core_hits}


def b07():
    canary = os.path.join(tempfile.gettempdir(), "pb07_canary")
    D = {"static": _static_inventory()}
    D["legacy_enabled"] = in_process(pb_worker.legacy_go_disabled, db_for("b07a"), CORE_PATH, "b07 legacy", "lab:b07 legacy", disable=False)
    D["legacy_disabled"] = in_process(pb_worker.legacy_go_disabled, db_for("b07b"), CORE_PATH, "b07 legacy", "lab:b07 legacy", disable=True)
    dbg = db_for("b07c")
    os.environ["CREATIVE_OS_LEGACY_LAB_SPEND_PATH"] = "disabled"
    try:
        D["governed_with_legacy_disabled"] = in_process(pb_worker.go_governed, dbg, CORE_PATH, "b07 governed", "T31:b07")
        D["hf_batch_legacy_disabled"] = in_process(pb_worker.hf_batch_paths, db_for("b07d"), CORE_PATH, canary, disable_legacy=True, adapter=True)
    finally:
        os.environ.pop("CREATIVE_OS_LEGACY_LAB_SPEND_PATH", None)
    D["hf_batch_legacy_enabled"] = in_process(pb_worker.hf_batch_paths, db_for("b07e"), CORE_PATH, canary, disable_legacy=False, adapter=True)
    D["hf_batch_no_adapter_as_main"] = in_process(pb_worker.hf_batch_paths, db_for("b07f"), CORE_PATH, canary, disable_legacy=False, adapter=False)
    # __main__ reale di hf_batch_runtime.py: senza lock si ferma prima di qualunque go; lock/quote -> REAL_PROVIDER_DISABLED
    spec = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "SPECS", "spec_motion_B1_B4C.json")
    mains = {}
    for verb in ("go", "lock", "quote"):
        r = subprocess.run([sys.executable, os.path.join(GATE01, "runtime", "hf_batch_runtime.py"), spec, verb],
                           capture_output=True, text=True, timeout=120, env={**os.environ, "HOME": canary})
        mains[verb] = {"rc": r.returncode, "stdout": r.stdout[-400:], "stderr": r.stderr[-600:]}
    D["hf_batch_runtime_main"] = mains
    p2 = open(P2_PATH, encoding="utf-8").read()
    D["p2_frozen"] = {"sha256": sha256_file(P2_PATH), "has_real_cli_submit": 'subprocess.run(["higgsfield", "generate", "create"' in p2 or "higgsfield" in p2,
                      "imported_by_runtime": any("hf_batch_ORIGINAL" in open(os.path.join(GATE01, "runtime", f), encoding="utf-8").read()
                                                 or "P2_RUNTIME" in open(os.path.join(GATE01, "runtime", f), encoding="utf-8").read()
                                                 for f in os.listdir(os.path.join(GATE01, "runtime")) if f.endswith(".py"))}
    le, ld, gv = D["legacy_enabled"], D["legacy_disabled"], D["governed_with_legacy_disabled"]
    checks = {
        "legacy_enabled_reaches_adapter_gate_only": le.get("error") == "RealProviderDisabled" and le.get("switch_state") == "ENABLED_LAB_ONLY",
        "legacy_disabled_before_core_import": ld.get("error") == "LEGACY_SPEND_PATH_DISABLED" and ld.get("core_imported_after") is False
                                              and ld.get("store_created") is False and ld.get("switch_state") == "DISABLED",
        "governed_unaffected_by_switch": gv.get("state") == "SUCCEEDED" and gv.get("transport_sent_count") == 1,
        "hf_batch_legacy_disabled_zero_submits": D["hf_batch_legacy_disabled"].get("error") == "LEGACY_SPEND_PATH_DISABLED"
                                                 and D["hf_batch_legacy_disabled"].get("submits") == 0,
        "hf_batch_legacy_enabled_marked": (D["hf_batch_legacy_enabled"].get("ok") is True
                                          and D["hf_batch_legacy_enabled"].get("governance") == ["LEGACY_LAB", "LEGACY_LAB"]
                                          and D["hf_batch_legacy_enabled"].get("legacy_resume_as_start") == [True, True]),
        "hf_batch_no_adapter_real_provider_disabled": D["hf_batch_no_adapter_as_main"].get("error") == "REAL_PROVIDER_DISABLED"
                                                      and D["hf_batch_no_adapter_as_main"].get("lock") == "REAL_PROVIDER_DISABLED"
                                                      and D["hf_batch_no_adapter_as_main"].get("quote") == "REAL_PROVIDER_DISABLED",
        "hf_batch_main_never_reaches_provider": (mains["go"]["rc"] != 0 and "NO LOCK" in (mains["go"]["stdout"] + mains["go"]["stderr"])
                                                 and "REAL_PROVIDER_DISABLED" in mains["lock"]["stderr"]
                                                 and "REAL_PROVIDER_DISABLED" in mains["quote"]["stderr"]),
        "sentinel_zero_violations": all(D[k].get("violations") == [] for k in ("hf_batch_legacy_disabled", "hf_batch_legacy_enabled", "hf_batch_no_adapter_as_main")),
        "p2_frozen_not_imported_by_runtime": D["p2_frozen"]["sha256"] == CANON["p2_sha256"] and D["p2_frozen"]["imported_by_runtime"] is False,
    }
    ok = all(checks.values())
    D["checks"] = checks
    ev = evidence("B07", "legacy_spend_paths", D)
    for n in ("b07a", "b07b", "b07c", "b07d", "b07e", "b07f"):
        pb_worker.cleanup_db(os.path.join(STATE_DIR, f"pb_{n}.db"))
    failed = [k for k, v in checks.items() if not v]
    return (f"inventario statico: {len(D['static']['repo_hits'])} file con hit · legacy aperto -> {le.get('error')} (solo FakeAdapter) · "
            f"legacy chiuso -> {ld.get('error')} (Core importato: {ld.get('core_imported_after')}, store creato: {ld.get('store_created')}) · "
            f"governato con legacy chiuso -> {gv.get('state')} · hf_batch legacy chiuso -> {D['hf_batch_legacy_disabled'].get('error')} "
            f"({D['hf_batch_legacy_disabled'].get('submits')} submit) · __main__ go/lock/quote -> NO LOCK / REAL_PROVIDER_DISABLED ×2 · "
            f"P2 frozen non importato · check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ B08
def b08():
    db = db_for("b08")
    sc = in_process(pb_worker.orphan_scenario, db, CORE_PATH, "LAB_SPENDER_SECRET_b08")
    q = CTX.Queue()
    p = CTX.Process(target=pb_worker._entry, args=(q, pb_worker.crash_after_send, (db, CORE_PATH), {}))
    p.start()
    p.join(120)
    crash_exit = p.exitcode
    cls = in_process(pb_worker.classify_all, db, CORE_PATH, ["ORPH:a", "ORPH:crash"])
    inv = {x["operation_id"]: x for x in cls.get("inventory", [])}
    ok = (sc.get("ok") and sc["classify_no_intent"]["class"] == "RESERVED_NO_INTENT" and sc["classify_no_intent"]["exits_available"] == []
          and sc["resume"]["outcome"] == "EXISTING_LIVE_JOB/reserved-no-dispatch" and sc["resume"]["submits"] == 0
          and sc["new_attempt_same_operation"] == {"accepted": False, "code": "LIVE_OR_UNCERTAIN_ATTEMPT"}
          and sc["recover_orphaned_submits"] == [] and sc["due_for_reconcile"] == [sc["reservation"]["job_id"]]
          and sc["reconcile_orphan"] == {"accepted": False, "code": "OWNERSHIP_INCOMPLETE"}
          and sc["reclaim_policy"] == "NOT_AUTHORIZED"
          and crash_exit == 4 and inv.get("ORPH:crash", {}).get("class") == "RESERVED_WITH_INTENT"
          and [x["state"] for x in cls.get("recovered", [])] == ["SUBMIT_UNKNOWN"]
          and inv.get("ORPH:a", {}).get("class") == "RESERVED_NO_INTENT")
    ev = evidence("B08", "orphan_reserved_lease", {"scenario": sc, "crash_after_send_exit": crash_exit, "classification": cls,
                                                   "gap_status": "STILL_OPEN",
                                                   "why_open": "nessuna lease authority (finestra, attore, evidenza) definita in Core o Runtime; "
                                                               "una reclaim senza authority sarebbe una policy arbitraria (vietata dal mandato)"})
    pb_worker.cleanup_db(db)
    return (f"orfana senza intento: classe {sc.get('classify_no_intent', {}).get('class')}, uscite {sc.get('classify_no_intent', {}).get('exits_available')} · "
            f"resume -> {sc.get('resume', {}).get('outcome')} (0 submit) · new_attempt -> {sc.get('new_attempt_same_operation', {}).get('code')} · "
            f"recover -> [] · reconcile autenticata -> {sc.get('reconcile_orphan', {}).get('code')} · con intento (crash exit {crash_exit}) -> "
            f"RESERVED_WITH_INTENT -> recover SUBMIT_UNKNOWN · reclaim: {sc.get('reclaim_policy')} · GAP: STILL_OPEN"), ev, ok


# ------------------------------------------------------------------ B09
def b09():
    from runtime.authorization import DEFAULT_LAB_AUTHORIZATION, LAB_PRICE_TABLE, LAB_QUOTE_UNIT
    b01 = next((r for r in RESULTS if r["id"] == "B01"), None)
    d = {"authority": {"label": DEFAULT_LAB_AUTHORIZATION.label, "envelope_by_scope": dict(DEFAULT_LAB_AUTHORIZATION.envelope_by_scope),
                       "price_table": dict(LAB_PRICE_TABLE), "unit": LAB_QUOTE_UNIT},
         "real_provider_authorization": "NOT_VERIFIED", "real_pricing": "NOT_VERIFIED",
         "claim": "LAB_ONLY: nessun valore reale di credito, nessuna policy tenant, nessun Human Authorization system"}
    if b01 is None or b01["status"] != "PASS":
        ev = evidence("B09", "authority_lab_state", {**d, "status": "BLOCKED", "reason_code": "BLOCKED_ENVIRONMENT",
                                                     "note": "la separazione dell'autorita' dall'orchestrator e' dimostrabile solo con B01"})
        raise gate_report.GateBlocked("BLOCKED_ENVIRONMENT", "B01 non verificato: autorita' non separabile dall'orchestrator in questo ambiente", ev)
    b01ev = json.load(open(os.path.join(BUNDLE, b01["evidence"]), encoding="utf-8"))
    extra = b01ev["probe_full"].get("extra_probes", {})
    P = b01ev["probe_full"].get("protocol", {})
    d["orchestrator_issue_quote_on_spender_store"] = extra.get("issue_quote_on_worker_store")
    d["orchestrator_write_spender_store"] = b01ev["attempts"].get("write_worker_store")
    d["client_amount_refused"] = P.get("amount_from_client", {}).get("refused")
    d["quote_issued_by_spender"] = {k: P.get("quote", {}).get(k) for k in ("amount", "envelope_id", "price_source", "sku")}
    ok = (str(d["orchestrator_issue_quote_on_spender_store"]).startswith("BLOCKED") and str(d["orchestrator_write_spender_store"]).startswith("BLOCKED")
          and str(d["client_amount_refused"]).startswith("PROTOCOL") and d["quote_issued_by_spender"]["price_source"] == "LAB_PRICE_TABLE"
          and LAB_PRICE_TABLE.get("fake_model_v1") == 10)
    ev = evidence("B09", "authority_lab_state", d)
    return (f"autorita' LAB (listino {LAB_PRICE_TABLE}, envelope per scope) vive nello spender · orchestrator: quote sullo store spender -> "
            f"{d['orchestrator_issue_quote_on_spender_store']}, scrittura store -> {d['orchestrator_write_spender_store']}, importo dal client -> "
            f"{str(d['client_amount_refused'])[:30]} · real authorization/pricing: NOT_VERIFIED"), ev, ok


# ------------------------------------------------------------------ B10
def b10():
    log_path = os.path.join(REGRESSION_DIR, "r0_r1_run_gate_post_fix.log")
    with open(log_path, "w", encoding="utf-8") as log:
        r = subprocess.run([sys.executable, os.path.join(GATE01, "tests", "run_gate.py")], cwd=GATE01, stdout=log,
                           stderr=subprocess.STDOUT, text=True, timeout=1800,
                           env={**os.environ, "CREATIVE_OS_CORE_PATH": CORE_PATH, "PYTHONDONTWRITEBYTECODE": "1"})
        log.write(f"\nEXIT={r.returncode}\n")
    res = json.load(open(os.path.join(GATE01, "evidence", "RESULTS.json"), encoding="utf-8"))
    shutil.copy(os.path.join(GATE01, "evidence", "RESULTS.json"), os.path.join(REGRESSION_DIR, "r0_r1_RESULTS_post_fix.json"))
    shutil.copy(os.path.join(GATE01, "TEST_RESULTS.md"), os.path.join(REGRESSION_DIR, "r0_r1_TEST_RESULTS_post_fix.md"))
    # il gate storico riscrive evidence/, state/, TEST_RESULTS.md tracciati: si ripristina la baseline (materiale storico)
    subprocess.run(["git", "-C", REPO, "checkout", "--", "RUNTIME_INTEGRATION_GATE_01/evidence", "RUNTIME_INTEGRATION_GATE_01/state",
                    "RUNTIME_INTEGRATION_GATE_01/TEST_RESULTS.md"], check=True)
    subprocess.run(["git", "-C", REPO, "clean", "-fq", "RUNTIME_INTEGRATION_GATE_01/state"], check=True)
    for f in os.listdir(STATE_DIR):
        if f.endswith((".snapshots", ".reconciliation")):
            shutil.rmtree(os.path.join(STATE_DIR, f), ignore_errors=True)
    s = res["summary"]
    by_id = {x["id"]: x for x in res["results"]}
    SHARED["regression_T29"] = {"status": by_id.get("T29", {}).get("status"), "reason_code": by_id.get("T29", {}).get("reason_code")}
    ok = (r.returncode == 0 and s["fail"] == 0 and s["pass"] == 36 and s["inventory"]["valid"] and s["total"] == 37
          and [b["id"] + "/" + b["reason_code"] for b in s["blocked_tests"]] == ["T29/BLOCKED_ENVIRONMENT"]
          and by_id["T19"]["status"] == "PASS" and by_id["T16"]["status"] == "PASS" and by_id["T17"]["status"] == "PASS")
    ev = evidence("B10", "regression_r0_r1", {"runner_exit": r.returncode, "summary": s,
                                              "per_test": {k: {"status": v["status"], "reason_code": v["reason_code"]} for k, v in by_id.items()},
                                              "artifacts": ["regression/r0_r1_run_gate_post_fix.log", "regression/r0_r1_RESULTS_post_fix.json",
                                                            "regression/r0_r1_TEST_RESULTS_post_fix.md"],
                                              "historic_tracked_files_restored": True})
    return (f"run_gate.py: exit {r.returncode} · {s['pass']}/{s['total']} PASS · BLOCKED {[b['id'] + '/' + b['reason_code'] for b in s['blocked_tests']]} · "
            f"FAIL {s['fail_ids']} · inventario valido {s['inventory']['valid']} · T19 statico {by_id['T19']['status']}"), ev, ok


# ------------------------------------------------------------------ B11
def b11():
    p2_after = sha256_file(P2_PATH)
    core_head = git("rev-parse", "HEAD")
    core_status = git("status", "--porcelain", "--untracked-files=all")
    st = static_checks.run(CORE_PATH)
    lab_orig = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "LAB", "hf_batch_ORIGINAL.py")
    d = {"p2_before": SHARED.get("p2_before"), "p2_after": p2_after, "p2_lab_original": sha256_file(lab_orig),
         "core_head_after": core_head, "core_status_after": core_status, "static_checks": st}
    ok = (p2_after == CANON["p2_sha256"] == SHARED.get("p2_before") == d["p2_lab_original"] and core_head == CANON["core_sha"]
          and core_status == "" and st["ok"])
    ev = evidence("B11", "p2_freeze_core_pin_after", d)
    return (f"P2 before {str(SHARED.get('p2_before'))[:16]} == after {p2_after[:16]} == canonico · Core {core_head[:12]} clean={core_status == ''} · "
            f"static checks ok={st['ok']} ({len(st['findings'])} findings)"), ev, ok


# ------------------------------------------------------------------ B12 (corrective delta)
def b12():
    """NG-03: la provenance del settlement zero deve corrispondere all'evidenza realmente prodotta.
    A = rifiuto a mark_submitting (pre-authorize, pre-send): provenance del RUNTIME.
    B = rifiuto dentro adapter.submit con marcatore invariato: attestazione del TRASPORTO (Core)."""
    from runtime.payload_snapshot import PRE_SUBMIT_REFUSAL_REMOTE_REF, PRE_SUBMIT_REFUSAL_SOURCE
    TRANSPORT = "TRANSPORT_ATTESTED_NOT_SENT"
    db = db_for("b12")
    R, S = {}, {}
    # --- 1/2: rifiuti a mark_submitting (SERIALIZATION_DRIFT, IDENTITY_DRIFT)
    for kind, op in (("drift_nested", "T32:b12ser"), ("identity_drift", "T32:b12id")):
        R[kind] = in_process(pb_worker.go_governed, db, CORE_PATH, f"b12 {kind}", op, adapter_kind=kind)
        S[kind] = pb_worker.read_state(db)
    # --- 3: rifiuto DENTRO adapter.submit, marcatore invariato -> attestazione del trasporto
    R["reorder"] = in_process(pb_worker.go_governed, db, CORE_PATH, "b12 reorder", "T32:b12tr", adapter_kind="reorder")
    # --- 4: invio avvenuto ed esito incerto -> nessun settlement, SUBMIT_UNKNOWN
    R["submit_unknown"] = in_process(pb_worker.go_governed, db, CORE_PATH, "b12 unknown", "T32:b12unk",
                                     adapter_kind="submit_unknown")
    state = pb_worker.read_state(db)
    rows = {r["operation_id"]: r for r in state["rows"]}
    anoms: dict = {}
    for a in state["anomalies"]:
        anoms.setdefault(a["job_id"], []).append(a)
    ledger: dict = {}
    for e in state["ledger"]:
        ledger.setdefault(e["job_id"], []).append((e["kind"], e["units"], e["source"]))
    # --- 5: race / stale write
    race = in_process(pb_worker.pre_submit_race, db_for("b12race"), CORE_PATH, "b12 race", "T32:b12race")

    def recon_sources(job_id):
        return [a["detail"]["evidence"]["source"] for a in anoms.get(job_id, []) if a["kind"] == "RECONCILIATION"]

    def pre_submit_case(op, expected_code):
        r = rows.get(op)
        if not r:
            return False, {"missing_row": op}
        jid = r["job_id"]
        kinds = [a["kind"] for a in anoms.get(jid, [])]
        pre = next((a["detail"] for a in anoms.get(jid, []) if a["kind"] == "SNAPSHOT_REFUSED_PRE_SUBMIT"), {})
        obs = pre.get("observed", {})
        d = {"state": r["state"], "settled_units": r["settled_units"], "settlement_source": r["settlement_source"],
             "anomaly_kinds": kinds, "reconciliation_sources": recon_sources(jid),
             "ledger": ledger.get(jid), "refusal_code": pre.get("code"), "observed": obs,
             "not_dispatched_provable": pre.get("not_dispatched_provable"),
             "terminalized": pre.get("terminalized"), "settled": pre.get("settled")}
        ok = (r["state"] == "FAILED" and r["settled_units"] == 0
              and r["settlement_source"] == PRE_SUBMIT_REFUSAL_SOURCE
              and r["settlement_source"] != TRANSPORT                      # provenance NON falsificata
              and recon_sources(jid) == [PRE_SUBMIT_REFUSAL_SOURCE]
              and TRANSPORT not in json.dumps(anoms.get(jid, []))          # in nessun punto dell'evidenza
              and "SNAPSHOT_REFUSED_PRE_SUBMIT" in kinds
              and "PRE_SUBMIT_REFUSAL_NOT_PROVABLE" not in kinds
              and pre.get("code") == expected_code and pre.get("not_dispatched_provable") is True
              and pre.get("terminalized") is True and pre.get("settled") is True
              # fatti osservati, non dichiarati
              and obs.get("transport_sent_count_unchanged") is True
              and obs.get("sealed_digest_authorized_in_transport") is False
              and obs.get("core_digest_authorized_in_transport") is False
              and obs.get("guard_armed_for_this_attempt") is False
              and obs.get("send_attestation_present") is False
              # ledger: esposizione prenotata e regolata a 0 con la stessa provenance
              and ("SETTLE", 0, PRE_SUBMIT_REFUSAL_SOURCE) in (ledger.get(jid) or [])
              and not any(src == TRANSPORT for _, _, src in (ledger.get(jid) or [])))
        return ok, d
    ok_ser, d_ser = pre_submit_case("T32:b12ser", "SERIALIZATION_DRIFT")
    ok_id, d_id = pre_submit_case("T32:b12id", "IDENTITY_DRIFT")
    # 3: il percorso attestato dal trasporto resta invariato
    tr = rows.get("T32:b12tr", {})
    tr_jid = tr.get("job_id")
    ok_tr = (R["reorder"].get("transport_sent_count") == 0 and tr.get("state") == "FAILED"
             and tr.get("settled_units") == 0 and tr.get("settlement_source") == TRANSPORT
             and recon_sources(tr_jid) == [TRANSPORT]
             and "REFUSED_BEFORE_SEND" in [a["kind"] for a in anoms.get(tr_jid, [])]
             and ("SETTLE", 0, TRANSPORT) in (ledger.get(tr_jid) or []))
    # 4: invio avvenuto, esito incerto -> nessun settlement, nessun terminale
    unk = rows.get("T32:b12unk", {})
    unk_jid = unk.get("job_id")
    ok_unk = (R["submit_unknown"].get("transport_sent_count") == 1 and unk.get("state") == "SUBMIT_UNKNOWN"
              and unk.get("settled_units") is None and unk.get("settlement_source") is None
              and not any(k == "SETTLE" for k, _, _ in (ledger.get(unk_jid) or []))
              and PRE_SUBMIT_REFUSAL_SOURCE not in json.dumps(anoms.get(unk_jid, []))
              and TRANSPORT not in json.dumps(anoms.get(unk_jid, [])))
    # 5: race — la seconda terminalizzazione (revisione obsoleta) e' rifiutata dal Core, nessun doppio SETTLE
    rc = race if race.get("ok") else {}
    r_end = rc.get("state_end", {})
    settles = [e for e in (r_end.get("ledger") or []) if e["kind"] == "SETTLE"]
    ok_race = (race.get("ok") is True
               and rc.get("first", {}).get("report", {}).get("terminalized") is True
               and rc.get("first", {}).get("report", {}).get("settled") is True
               and rc.get("second_stale", {}).get("refused") is True
               and rc.get("second_stale", {}).get("report", {}).get("terminalized") is False
               and "StaleWrite" in str(rc.get("second_stale", {}).get("report", {}).get("terminalize_error"))
               and rc.get("second_stale", {}).get("report", {}).get("settled") is False
               and len(settles) == 1 and settles[0]["units"] == 0
               and settles[0]["source"] == PRE_SUBMIT_REFUSAL_SOURCE
               and rc.get("settle_same_amount_again", {}).get("duplicate") is True
               and rc.get("settle_same_amount_again", {}).get("applied") is False
               and rc.get("settle_other_amount", {}).get("error") == "SettlementConflict"
               and (r_end.get("rows") or [{}])[0].get("settled_units") == 0
               and (r_end.get("rows") or [{}])[0].get("state") == "FAILED"
               and "PRE_SUBMIT_TERMINALIZE_REFUSED" in [a["kind"] for a in (r_end.get("anomalies") or [])])
    # confronto con il difetto riprodotto pre-fix
    pre_fix = json.load(open(os.path.join(EVIDENCE_DIR, "pre_fix", "reproduction_ng03.json"), encoding="utf-8"))
    ok_regressed = (pre_fix["case_A_refusal_at_mark_submitting"]["row"]["settlement_source"] == TRANSPORT
                    and pre_fix["case_B_control_refusal_inside_adapter_submit"]["row"]["settlement_source"] == TRANSPORT)
    checks = {"serialization_drift_truthful_provenance": ok_ser, "identity_drift_truthful_provenance": ok_id,
              "transport_attested_path_unchanged": ok_tr, "uncertain_send_not_settled": ok_unk,
              "race_no_double_settlement": ok_race, "pre_fix_defect_documented": ok_regressed,
              "provenances_are_distinct": PRE_SUBMIT_REFUSAL_SOURCE != TRANSPORT}
    ok = all(checks.values())
    ev = evidence("B12", "pre_submit_provenance", {
        "sources": {"pre_submit_runtime": PRE_SUBMIT_REFUSAL_SOURCE, "remote_ref": PRE_SUBMIT_REFUSAL_REMOTE_REF,
                    "transport_attested": TRANSPORT},
        "case_1_serialization_drift": d_ser, "case_2_identity_drift": d_id,
        "case_3_transport_attested": {"go": R["reorder"], "row": tr, "reconciliation_sources": recon_sources(tr_jid),
                                      "ledger": ledger.get(tr_jid)},
        "case_4_uncertain_send": {"go": R["submit_unknown"], "row": unk, "ledger": ledger.get(unk_jid),
                                  "anomalies": [a["kind"] for a in anoms.get(unk_jid, [])]},
        "case_5_race_stale_write": race, "rows": state["rows"], "anomalies": state["anomalies"],
        "pre_fix_reference": pre_fix, "checks": checks,
        "scope_note": "il rifiuto pre-submit usa i percorsi espliciti del Core (reconcile + settle) con "
                      "provenance del runtime; nessuna API additiva del Core e' stata richiesta"})
    pb_worker.cleanup_db(db)
    pb_worker.cleanup_db(os.path.join(STATE_DIR, "pb_b12race.db"))
    failed = [k for k, v in checks.items() if not v]
    return (f"SERIALIZATION_DRIFT e IDENTITY_DRIFT -> FAILED settlement 0 con provenance {PRE_SUBMIT_REFUSAL_SOURCE} "
            f"(TRANSPORT_ATTESTED_NOT_SENT assente da riga, evidenza e ledger; fatti osservati: sent_count invariato, "
            f"digest non autorizzati, guard non armato, nessuna attestazione) · rifiuto dentro submit -> {tr.get('settlement_source')} "
            f"(invariato) · invio incerto -> {unk.get('state')} senza settlement · race: seconda terminalizzazione "
            f"{'StaleWrite' if ok_race else 'NON rifiutata'}, un solo SETTLE, settle idempotente, importo diverso -> SettlementConflict · "
            f"check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ B13 (HUMAN REVIEW 02)
def b13():
    """REPORTING: "tutti i test PASS" e "tutti i requisiti chiusi" sono due affermazioni diverse.
    Le cinque controprove richieste dal review, piu' l'invariante che rende impossibile affermarle insieme."""
    from pbgate import make_manifest
    PR = phase_readiness
    # report REALE proiettato: i test gia' eseguiti piu' questo, assunto PASS
    projected = list(RESULTS) + [{"id": "B13", "status": "PASS", "reason_code": "VERIFIED", "title": "reporting",
                                  "expected": "", "actual": "", "evidence": "", "diagnostic_exit": 0, "pass": True}]
    suite = gate_report.summarize(projected, policy=POLICY, expected_ids=EXPECTED_IDS)
    real = PR.build(projected, suite)
    rp, rt = real["phase_readiness"], real["test_suite"]
    req = {r["id"]: r for r in rp["requirements"]}

    def synth(states: dict, all_pass: bool = True) -> dict:
        """Report sintetico: registro dei requisiti sostituito, per provare i casi limite."""
        saved = PR.REQUIREMENTS
        PR.REQUIREMENTS = tuple({"id": k, "scope": v[0], "evidence_tests": (), "declared": v[1],
                                 "fallback": v[1], "title": k, "note": ""} for k, v in states.items())
        try:
            results = [{"id": i, "status": "FAIL" if (not all_pass and i == "B05") else "PASS",
                        "reason_code": "ASSERTION_FAILED" if (not all_pass and i == "B05") else "VERIFIED"}
                       for i in sorted(EXPECTED_IDS)]
            return PR.build(results, gate_report.summarize(results, policy=POLICY, expected_ids=EXPECTED_IDS))
        finally:
            PR.REQUIREMENTS = saved

    c1 = synth({"ORPHAN_RESERVED_LEASE": ("this_phase", PR.STILL_OPEN), "X_OK": ("this_phase", PR.VERIFIED_LAB)})
    c2 = synth({"LEGACY_SPEND_PATHS_PROVIDER_GATE": ("future_gate", PR.BLOCKED_PROVIDER_GATE),
                "Y_OK": ("this_phase", PR.VERIFIED_LAB)})
    c3 = synth({"P_B02_BINDING_AUTHENTICATION": ("this_phase", PR.VERIFIED_LAB),
                "P_B02_P_B01_COMPOSITION": ("this_phase", PR.NOT_VERIFIED)})
    c4 = synth({"ONLY_OK": ("this_phase", PR.VERIFIED_LAB)})
    c4b = synth({"ONLY_OK": ("this_phase", PR.VERIFIED_LAB)}, all_pass=False)

    forged = json.loads(json.dumps(c1))
    forged["phase_readiness"]["all_requirements_verified"] = True
    try:
        PR.validate(forged)
        forged_refused = False
    except PR.ReportingInconsistent:
        forged_refused = True

    con = PR.console(real)
    mdl = "\n".join(PR.markdown(real))
    man = make_manifest.build_manifest(real, runtime_code_sha="0" * 40, bundle_version="test")
    gaps = PR.machine_readable_gaps(real)
    av = str(rp["all_requirements_verified"]).lower()
    coherent = {
        "console_shows_both": (f"all_tests_passed = {str(rt['all_tests_passed']).lower()}" in con
                               and f"all_requirements_verified = {av}" in con
                               and rp["phase_gate_decision"] in con),
        "markdown_shows_both": (f"`all_requirements_verified = {av}`" in mdl
                                and f"`phase_gate_decision = {rp['phase_gate_decision']}`" in mdl
                                and f"**{str(rt['all_tests_passed']).lower()}**" in mdl),
        "manifest_matches": (man["phase_readiness"]["all_requirements_verified"] == rp["all_requirements_verified"]
                             and man["phase_readiness"]["phase_gate_decision"] == rp["phase_gate_decision"]
                             and man["test_suite"]["all_tests_passed"] == rt["all_tests_passed"]
                             and man["test_suite"]["pass"] == rt["pass"] and man["gap_status"] == gaps),
        "manifest_never_claims_all_verified": ('"all_requirements_verified": true' not in json.dumps(man, ensure_ascii=False)
                                               if not rp["all_requirements_verified"] else True),
        "counts_match": man["test_suite"]["total"] == rt["total"] == len(projected),
    }
    checks = {
        "c1_tests_green_orphan_open": (c1["test_suite"]["all_tests_passed"] is True
                                       and c1["phase_readiness"]["all_requirements_verified"] is False
                                       and c1["phase_readiness"]["phase_gate_decision"] == PR.PHASE_COMPLETE_WITH_OPEN_GAPS
                                       and c1["phase_readiness"]["open_requirements_this_phase"] == ["ORPHAN_RESERVED_LEASE"]),
        "c2_tests_green_legacy_blocked_provider_gate": (c2["test_suite"]["all_tests_passed"] is True
                                                        and c2["phase_readiness"]["all_requirements_verified"] is False
                                                        and c2["phase_readiness"]["open_requirements_future_gate"] == ["LEGACY_SPEND_PATHS_PROVIDER_GATE"]
                                                        and c2["phase_readiness"]["open_requirements_blocking_all_verified"] == ["LEGACY_SPEND_PATHS_PROVIDER_GATE"]),
        "c3_pb02_not_globally_verified": (c3["phase_readiness"]["all_requirements_verified"] is False
                                          and "P_B02_BINDING_AUTHENTICATION" in c3["phase_readiness"]["verified_requirements"]
                                          and "P_B02_P_B01_COMPOSITION" in c3["phase_readiness"]["open_requirements_this_phase"]),
        "c4_no_open_requirements_allows_all_verified": (c4["phase_readiness"]["all_requirements_verified"] is True
                                                        and c4["phase_readiness"]["phase_gate_decision"] == PR.PHASE_COMPLETE_ALL_VERIFIED),
        "c4b_failing_test_blocks_all_verified": (c4b["phase_readiness"]["all_requirements_verified"] is False
                                                 and c4b["phase_readiness"]["phase_gate_decision"] == PR.PHASE_NOT_FAVORABLE),
        "c5_console_json_markdown_manifest_coherent": all(coherent.values()),
        "forged_report_refused": forged_refused,
        "real_tests_all_pass": rt["all_tests_passed"] is True and rt["test_suite_decision"] == PR.TEST_SUITE_ALL_PASS,
        "real_requirements_not_all_verified": rp["all_requirements_verified"] is False,
        "real_decision_with_open_gaps": rp["phase_gate_decision"] == PR.PHASE_COMPLETE_WITH_OPEN_GAPS,
        "real_max_state_still_reachable": rp["max_state"] == PR.MAX_STATE,
        "real_required_open_ids_present": {"ORPHAN_RESERVED_LEASE", "LEGACY_SPEND_PATHS_PROVIDER_GATE",
                                           "P_B02_P_B01_COMPOSITION", "RECONCILIATION_FRESHNESS_NG04"}
                                          <= set(rp["open_requirements_blocking_all_verified"]),
        "real_ng05_conservative_limitation": req["NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY"]["state"] == PR.OPEN_CONSERVATIVE_LIMITATION,
        "real_pb02_binding_only": (req["P_B02_BINDING_AUTHENTICATION"]["state"] == PR.VERIFIED_LAB
                                   and req["P_B02_P_B01_COMPOSITION"]["state"] == PR.NOT_VERIFIED
                                   and req["REAL_PROVIDER_RECONCILIATION"]["state"] == PR.NOT_VERIFIED),
        "real_orphan_open_despite_b08_pass": (req["ORPHAN_RESERVED_LEASE"]["state"] == PR.STILL_OPEN
                                              and "B08" in rt["pass_ids"]),
    }
    ok = all(checks.values())
    ev = evidence("B13", "reporting_phase_readiness", {
        "real_report": real,
        "synthetic_cases": {"c1_orphan_open": c1, "c2_legacy_blocked": c2, "c3_pb02_composition": c3,
                            "c4_no_open": c4, "c4b_failing_test": c4b},
        "forged_report_refused": forged_refused, "coherence": coherent, "machine_readable_gaps": gaps,
        "manifest_preview": man, "checks": checks,
        "note": "il report reale e' proiettato con B13 assunto PASS; RESULTS.json e' costruito dalla "
                "STESSA funzione (phase_readiness.build) al termine dell'esecuzione."})
    failed = [k for k, v in checks.items() if not v]
    return (f"A: {rt['pass']}/{rt['total']} PASS, all_tests_passed={rt['all_tests_passed']} ({rt['test_suite_decision']}) · "
            f"B: all_requirements_verified={rp['all_requirements_verified']} ({rp['phase_gate_decision']}), aperti bloccanti "
            f"{rp['open_requirements_blocking_all_verified']}, stato massimo "
            f"{rp['max_state']} · controprove: orphan aperto con test verdi, legacy BLOCKED_PROVIDER_GATE, P-B02 non globalmente "
            f"verificata, ALL_VERIFIED solo senza aperti, test FAIL -> mai ALL_VERIFIED, report forgiato rifiutato, "
            f"console/JSON/Markdown/MANIFEST coerenti · check falliti: {failed or 'nessuno'}"), ev, ok


# ------------------------------------------------------------------ report (authority unica)
def build_report() -> dict:
    """UNA sola classificazione: da `gate_report.summarize` si prendono SOLO i fatti sui test,
    la readiness di fase la decide `pbgate/phase_readiness.py`."""
    suite = gate_report.summarize(RESULTS, policy=POLICY, expected_ids=EXPECTED_IDS)
    return phase_readiness.build(RESULTS, suite)


def write_results(report: dict) -> dict:
    """RESULTS.json, TEST_RESULTS.md e il blocco di stato del README derivano dallo STESSO report;
    alla fine i file vengono riletti e confrontati (fail-closed)."""
    payload = {"schema": "provider-boundary-gate-results/2", "required_core_sha": REQUIRED_CORE_SHA,
               "canonical": CANON, "results": RESULTS, "report": report}
    with open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    lines = ["# TEST_RESULTS — PROVIDER / EXECUTION BOUNDARY GATE 01", "",
             f"Core canonical: `{REQUIRED_CORE_SHA}` · Runtime baseline: `{CANON['runtime_main_sha']}` · provider: FakeAdapter only · "
             "crediti spesi: 0 · rete generativa: nessuna · credenziali reali: nessuna", "",
             "Due domande distinte, due risposte distinte (Human Review 02): **A** dice se i test hanno prodotto "
             "l'esito atteso; **B** se i requisiti della fase sono chiusi. Un test PASS su un requisito aperto "
             "verifica che quel requisito resta aperto: non lo chiude.", "",
             "### Esito per test", "",
             "Tri-state: PASS = esito atteso prodotto · FAIL = esito atteso NON prodotto · BLOCKED = non verificabile "
             "nell'ambiente corrente (NON superato).", "",
             "| TEST | TITLE | EXPECTED | ACTUAL | STATUS | REASON_CODE | EXIT | EVIDENCE |", "|---|---|---|---|---|---|---|---|"]
    for r in RESULTS:
        lines.append(f"| {r['id']} | {r['title']} | {r['expected']} | {r['actual']} | **{r['status']}** | `{r['reason_code']}` | {r['diagnostic_exit']} | `{r['evidence']}` |")
    lines += [""] + phase_readiness.markdown(report) + [
        f"runner exit {report['runner_exit']}: {report['runner_exit_meaning']}", ""]
    with open(os.path.join(BUNDLE, "TEST_RESULTS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    readme_path = os.path.join(BUNDLE, "README.md")
    if os.path.exists(readme_path):
        src = open(readme_path, encoding="utf-8").read()
        block = phase_readiness.readme_block(report)
        if phase_readiness.README_BEGIN in src and phase_readiness.README_END in src:
            head, rest = src.split(phase_readiness.README_BEGIN, 1)
            _, tail = rest.split(phase_readiness.README_END, 1)
            src = head + block + tail
        else:
            src = src.rstrip() + "\n\n" + block + "\n"
        with open(readme_path, "w", encoding="utf-8") as fh:
            fh.write(src)
    cross_check_written_files(report)
    return report


def cross_check_written_files(report: dict) -> dict:
    """Authority unica verificata sui FILE: divergenza -> ReportingInconsistent (fail-closed)."""
    pr, ts = report["phase_readiness"], report["test_suite"]
    js = json.load(open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), encoding="utf-8"))["report"]
    if (js["phase_readiness"]["all_requirements_verified"] != pr["all_requirements_verified"]
            or js["phase_readiness"]["phase_gate_decision"] != pr["phase_gate_decision"]
            or js["test_suite"]["all_tests_passed"] != ts["all_tests_passed"]):
        raise phase_readiness.ReportingInconsistent("RESULTS.json diverge dal report")
    need = [f"`all_requirements_verified = {str(pr['all_requirements_verified']).lower()}`",
            f"`phase_gate_decision = {pr['phase_gate_decision']}`"]
    for name in ("TEST_RESULTS.md", "README.md"):
        doc = open(os.path.join(BUNDLE, name), encoding="utf-8").read()
        for token in need:
            if token not in doc:
                raise phase_readiness.ReportingInconsistent(f"{name}: manca {token}")
        if pr["all_requirements_verified"] is False and "all_requirements_verified = true" in doc.lower():
            raise phase_readiness.ReportingInconsistent(f"{name}: afferma anche all_requirements_verified true")
    return {"RESULTS.json": True, "TEST_RESULTS.md": True, "README.md": True}


def main() -> int:
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(REGRESSION_DIR, exist_ok=True)
    print(f"PROVIDER / EXECUTION BOUNDARY GATE 01 — Core {CORE_PATH} @ {git('rev-parse', 'HEAD')[:12]} (required {REQUIRED_CORE_SHA[:12]})", flush=True)
    scratch = tempfile.mkdtemp(prefix="pbgate_")
    os.chmod(scratch, 0o755)
    try:
        record("B00", "Reality Lock", "Core HEAD canonico e pulito; Runtime origin/main canonico; pin; P2 frozen", b00)
        record("B10", "R0-R1 regression (run_gate.py T01-T37) on hardened runtime", "36 PASS, T29 BLOCKED_ENVIRONMENT, 0 FAIL, inventario 37/37", b10)
        record("B01", "P-B01 real privilege boundary (distinct UIDs)", "orchestrator uid != spender uid, 0 caps, no_new_privs; 4 probe canoniche BLOCKED; peer uid autenticato; spesa governata via socket; segreto mai nel canale",
               lambda: b01(scratch))
        record("B02", "P-B01 same-UID control stays BLOCKED", "t29_status(same_uid) -> BLOCKED_ENVIRONMENT; T29 storico e di regressione BLOCKED", b02)
        record("B03", "P-B02 authenticated reconciliation: binding fail-closed", "16 controprove rifiutate con journal invariato; report valido -> stato scoperto con evidenza firmata", b03)
        record("B04", "P-B02 replay / other operation / snapshot audit", "replay -> REPLAY; report valido di altro job -> JOB_MISMATCH; RESERVED senza intento -> OWNERSHIP_INCOMPLETE; snapshot mancante -> SNAPSHOT_AUDIT_FAILED", b04)
        record("B05", "P-B04 exact-byte snapshot", "byte persistiti == canonici; sha256(file) == digest job; 0444; seal/bind/send; resume 0 file; API write-once/altra op/token/2o invio rifiutati", b05)
        record("B06", "P-B04 counterproofs refused before send", "nested/drift/reorder/sostituzione/missing/corrupt -> sent_count 0, FAILED settlement 0, nessun SUBMIT_UNKNOWN; pre-fix raggiungeva l'invio", b06)
        record("B07", "Legacy spend paths inventory + fail-closed switch", "interruttore chiuso -> LEGACY_SPEND_PATH_DISABLED prima di import/store; governato invariato; hf_batch legacy 0 submit; __main__ mai al provider; P2 frozen non importato", b07)
        record("B08", "Orphan RESERVED lease: reproduction + classification", "RESERVED_NO_INTENT senza uscite; 0 submit; new_attempt rifiutato; recover ignora; reconcile OWNERSHIP_INCOMPLETE; con intento -> SUBMIT_UNKNOWN; reclaim NOT_AUTHORIZED", b08)
        record("B09", "Authorization / pricing authority (LAB state)", "autorita' LAB nello spender; orchestrator non emette quote ne' scrive lo store; importo dal client rifiutato; real: NOT_VERIFIED", b09)
        record("B12", "NG-03 truthful pre-submit settlement provenance",
               "rifiuto a mark_submitting -> FAILED settlement 0 con provenance RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED "
               "e fatti osservati; rifiuto dentro submit -> TRANSPORT_ATTESTED_NOT_SENT invariato; invio incerto -> "
               "SUBMIT_UNKNOWN senza settlement; race -> StaleWrite, nessun doppio settlement", b12)
        record("B11", "P2 freeze after + Core pin/tree + static checks", "P2 before == after == canonico; Core HEAD canonico pulito; static checks 0 findings", b11)
        record("B13", "Reporting: test-suite result vs phase readiness (HUMAN REVIEW 02)",
               "all_tests_passed e all_requirements_verified separati e coerenti; requisiti aperti elencati; "
               "ALL_VERIFIED solo senza aperti; report incoerente rifiutato; console/JSON/Markdown/MANIFEST allineati", b13)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(os.path.join(STATE_DIR, "pb01"), ignore_errors=True)
    report = write_results(build_report())
    print(phase_readiness.console(report), flush=True)
    print("crediti spesi: 0 · provider reali: 0 · rete generativa: 0 · credenziali reali: 0", flush=True)
    return report["runner_exit"]


if __name__ == "__main__":
    sys.exit(main())
