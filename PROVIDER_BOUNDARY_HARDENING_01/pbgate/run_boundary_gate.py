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
from pbgate import pb_worker                                         # noqa: E402

CANON = {"core_sha": "740ee979300fe20a9382992528604dee70cb2fcf",
         "runtime_main_sha": "39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e",
         "p2_sha256": "637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1"}
P2_PATH = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "P2_RUNTIME", "hf_batch.py")
EXPECTED_IDS = frozenset(f"B{i:02d}" for i in range(0, 12))
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
    runtime_callers = [f for f in os.listdir(os.path.join(GATE01, "runtime")) if f.endswith(".py")
                       and "store.reconcile(" in open(os.path.join(GATE01, "runtime", f), encoding="utf-8").read()]
    ok = (D["first_apply"].get("state") == "RUNNING" and D["back_to_unknown"].get("state") == "SUBMIT_UNKNOWN"
          and D["replay_same_nonce"].get("code") == "REPLAY" and D["replay_same_nonce"].get("journal_unchanged")
          and D["fresh_report_after_replay"].get("state") == "SUCCEEDED"
          and D["valid_report_other_job_applied_to_u3"].get("code") == "JOB_MISMATCH"
          and D["raw_reserved_no_intent"].get("code") == "OWNERSHIP_INCOMPLETE"
          and D["snapshot_bind_removed_then_reconcile"].get("code") == "SNAPSHOT_AUDIT_FAILED"
          and D["same_without_snapshot_audit"].get("ok") is True
          and runtime_callers == ["reconciliation.py"])
    ev = evidence("B04", "reconciliation_replay_cross_operation", {"jobs": {"u3": u3, "u4": u4, "raw": raw_row}, "steps": D,
                                                                   "removed_snapshot_files": removed,
                                                                   "runtime_callers_of_store_reconcile": runtime_callers})
    pb_worker.cleanup_db(db)
    return (f"N1 -> {D['first_apply'].get('state')} · incertezza -> replay N1 -> {D['replay_same_nonce'].get('code')} · nuovo report -> "
            f"{D['fresh_report_after_replay'].get('state')} · report valido di altro job -> {D['valid_report_other_job_applied_to_u3'].get('code')} · "
            f"RESERVED senza intento -> {D['raw_reserved_no_intent'].get('code')} · snapshot bind rimosso -> "
            f"{D['snapshot_bind_removed_then_reconcile'].get('code')} · unico chiamante runtime di store.reconcile: {runtime_callers}"), ev, ok


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

    def refused_before_send(kind, op, expect_anomaly):
        r, row = R[kind], rows.get(op)
        if not row:
            return False
        return (r.get("ok") is False and r.get("transport_sent_count") == 0
                and row["state"] == "FAILED" and row["settled_units"] == 0
                and row["settlement_source"] == "TRANSPORT_ATTESTED_NOT_SENT"
                and expect_anomaly in anoms.get(row["job_id"], [])
                and any(k == "SETTLE" and u == 0 for k, u, _ in ledger.get(row["job_id"], [])))
    checks = {
        "nested_mutation_refused_before_send": refused_before_send("drift_nested", "T32:nested", "SNAPSHOT_REFUSED_BEFORE_SEND")
                                               and "SERIALIZATION_DRIFT" in str(R["drift_nested"].get("message")),
        "serialization_drift_refused_before_send": refused_before_send("drift_top", "T32:drift", "SNAPSHOT_REFUSED_BEFORE_SEND"),
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
    ok = all(checks.values())
    ev = evidence("B06", "snapshot_counterproofs", {"results": R, "rows": state["rows"], "anomalies": state["anomalies"],
                                                    "ledger": state["ledger"], "checks": checks,
                                                    "pre_fix_reference": pre})
    pb_worker.cleanup_db(db)
    failed = [k for k, v in checks.items() if not v]
    return (f"6 controprove: tutte rifiutate PRIMA del marcatore (sent_count 0), FAILED con settlement 0 attestato, nessun SUBMIT_UNKNOWN · "
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


# ------------------------------------------------------------------ report
def write_results() -> dict:
    s = gate_report.summarize(RESULTS, policy=POLICY, expected_ids=EXPECTED_IDS)
    passed = set(s["pass_ids"])
    s["readiness"] = {"lab_mock": s["gate_decision"] in (gate_report.GATE_COMPLETE_ALL_VERIFIED, gate_report.GATE_COMPLETE_WITH_ALLOWED_BLOCKED),
                      "real_provider": "NOT_DECLARED", "production": "NOT_DECLARED",
                      "security_boundary_p_b01": "LAB_VERIFIED_UID_BOUNDARY" if "B01" in passed else "NOT_VERIFIED",
                      "p_b02_authenticated_reconciliation": "LAB_VERIFIED" if {"B03", "B04"} <= passed else "NOT_VERIFIED",
                      "p_b04_exact_byte_snapshot": "LAB_VERIFIED" if {"B05", "B06"} <= passed else "NOT_VERIFIED",
                      "legacy_spend_paths": "INVENTORIED_SWITCH_VERIFIED_RESIDUAL_BLOCKED_PROVIDER_GATE" if "B07" in passed else "NOT_VERIFIED",
                      "orphan_reserved_lease": "STILL_OPEN (riprodotto, classificato, nessuna reclaim)",
                      "authorization_pricing": "LAB_ONLY" if "B09" in passed else "NOT_VERIFIED",
                      "max_state": "PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW"
                      if s["gate_decision"] == gate_report.GATE_COMPLETE_ALL_VERIFIED else "NOT_READY"}
    with open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": "provider-boundary-gate-results/1", "required_core_sha": REQUIRED_CORE_SHA, "canonical": CANON,
                   "results": RESULTS, "summary": s}, fh, indent=2, ensure_ascii=False, default=str)
    lines = ["# TEST_RESULTS — PROVIDER / EXECUTION BOUNDARY GATE 01", "",
             f"Core canonical: `{REQUIRED_CORE_SHA}` · Runtime baseline: `{CANON['runtime_main_sha']}` · provider: FakeAdapter only · "
             "crediti spesi: 0 · rete generativa: nessuna · credenziali reali: nessuna", "",
             "Stato per test (authority unica, tri-state): PASS = requisito verificato in LAB · FAIL = requisito NON superato · "
             "BLOCKED = requisito NON verificabile nell'ambiente corrente (NON superato).", "",
             "| TEST | TITLE | EXPECTED | ACTUAL | STATUS | REASON_CODE | EXIT | EVIDENCE |", "|---|---|---|---|---|---|---|---|"]
    for r in RESULTS:
        lines.append(f"| {r['id']} | {r['title']} | {r['expected']} | {r['actual']} | **{r['status']}** | `{r['reason_code']}` | {r['diagnostic_exit']} | `{r['evidence']}` |")
    lines += ["", f"**Totale: {s['pass']}/{s['total']} PASS · BLOCKED: {[b['id'] + '/' + b['reason_code'] for b in s['blocked_tests']] or 'nessuno'} · FAIL: {s['fail_ids'] or 'nessuno'}**",
              "", f"**GATE_DECISION: `{s['gate_decision']}`** · runner exit {s['runner_exit']}: {s['runner_exit_meaning']}", "",
              f"Inventario: {s['inventory']['observed_count']}/{s['inventory']['expected_count']} · valido: {s['inventory']['valid']}", "",
              "Readiness:", ""] + [f"- {k}: `{v}`" for k, v in s["readiness"].items()] + [
              "", "Nulla di quanto sopra significa provider ready, production ready, credenziali autorizzate, spend autorizzato, merge autorizzato o R2 autorizzato.", ""]
    with open(os.path.join(BUNDLE, "TEST_RESULTS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return s


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
        record("B11", "P2 freeze after + Core pin/tree + static checks", "P2 before == after == canonico; Core HEAD canonico pulito; static checks 0 findings", b11)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(os.path.join(STATE_DIR, "pb01"), ignore_errors=True)
    s = write_results()
    print(gate_report.console_summary(s), flush=True)
    print("crediti spesi: 0 · provider reali: 0 · rete generativa: 0 · credenziali reali: 0", flush=True)
    return s["runner_exit"]


if __name__ == "__main__":
    sys.exit(main())
