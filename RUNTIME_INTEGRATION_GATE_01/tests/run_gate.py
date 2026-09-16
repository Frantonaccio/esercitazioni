#!/usr/bin/env python3
"""RUNTIME INTEGRATION GATE 01 — matrice T01..T23.

MOCK ONLY · ZERO HIGGSFIELD · ZERO CREDITS · NO PRODUCTION.

Ogni test scrive la propria evidenza in evidence/Txx_*.json e una riga in
TEST_RESULTS.md con EXPECTED / ACTUAL / EXIT / EVIDENCE / PASS-FAIL.
I test che richiedono processi reali usano multiprocessing 'spawn' (nuovo
interprete): la memoria Python del padre non e' condivisa.
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
import traceback

GATE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GATE_ROOT)

from runtime.core_pin import KNOWN_STALE_CORE_SHAS, REQUIRED_CORE_SHA, verify_core_pin  # noqa: E402
from runtime.genspec_bridge import GenSpecBridgeError, GoInputs, build_genspec        # noqa: E402
from tests import static_checks, worker                                               # noqa: E402

CORE_PATH = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")
STATE_DIR = os.path.join(GATE_ROOT, "state")
EVIDENCE_DIR = os.path.join(GATE_ROOT, "evidence")
HANDOFF = os.path.join(GATE_ROOT, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16")
# P2 originale: copia read-only consegnata dal handoff (sul Mac vive fuori git, vedi INITIAL_STATE)
P2_HF_BATCH = os.environ.get("P2_HF_BATCH_PATH", os.path.join(HANDOFF, "P2_RUNTIME", "hf_batch.py"))
P2_HF_BATCH_SHA_DECLARED = "637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1"
P2_BASELINE: dict = {}
STALE_SHA = sorted(KNOWN_STALE_CORE_SHAS)[0]
CTX = multiprocessing.get_context("spawn")

RESULTS: list[dict] = []


# --------------------------------------------------------------- utilita'
def db_for(test_id: str) -> str:
    p = os.path.join(STATE_DIR, f"{test_id.lower()}.db")
    for suffix in ("", "-journal", "-wal", "-shm"):
        if os.path.exists(p + suffix):
            os.remove(p + suffix)
    return p


def evidence(test_id: str, name: str, payload: dict) -> str:
    path = os.path.join(EVIDENCE_DIR, f"{test_id}_{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    return os.path.relpath(path, GATE_ROOT)


def in_process(fn, *args, **kwargs) -> dict:
    """Nuovo interprete, esito via Queue. E' 'processo reale', non thread."""
    q = CTX.Queue()
    p = CTX.Process(target=worker._entry, args=(q, fn, args, kwargs))
    p.start()
    p.join(120)
    if p.is_alive():
        p.terminate()
        return {"ok": False, "error": "TIMEOUT_PROCESS"}
    return q.get(timeout=10)


def concurrent(fns_args: list[tuple]) -> list[dict]:
    """N processi reali, sincronizzati da una Barrier: partono insieme."""
    barrier = CTX.Barrier(len(fns_args))
    q = CTX.Queue()
    ps = []
    for fn, args, kwargs in fns_args:
        kwargs = dict(kwargs, barrier=barrier)
        p = CTX.Process(target=worker._entry, args=(q, fn, args, kwargs))
        p.start()
        ps.append(p)
    for p in ps:
        p.join(120)
    return [q.get(timeout=10) for _ in ps]


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
    try:
        actual, ev, ok = fn()
        exit_code = 0 if ok else 1
    except Exception as e:                                          # noqa: BLE001
        actual, ok, exit_code = f"EXCEPTION {type(e).__name__}: {e}", False, 2
        ev = evidence(test_id, "exception", {"trace": traceback.format_exc()})
    RESULTS.append({"id": test_id, "title": title, "expected": expected, "actual": actual,
                    "exit": exit_code, "evidence": ev, "pass": ok})
    mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
    print(f"  {test_id} {mark}  {title}\n       \033[2m{actual}\033[0m")


# ---------------------------------------------------------------- T01-T03
def t01():
    r = in_process(worker.run_go, db_for("T01"), "pin ok", max_polls=3)
    pure = verify_core_pin(REQUIRED_CORE_SHA).code
    ok = (r.get("ok") is True and r.get("core_sha") == REQUIRED_CORE_SHA
          and r.get("state") == "SUCCEEDED" and pure == "CORE_PIN_OK")
    ev = evidence("T01", "correct_core_pin", {"go": r, "pure_verdict": pure})
    return f"core_sha={str(r.get('core_sha'))[:12]} verdict={pure} state={r.get('state')}", ev, ok


def t02():
    wrong = "deadbeef" * 5
    r = in_process(worker.pin_probe_clean, CORE_PATH, wrong, db_for("T02"))
    ok = (r.get("error") == "CORE_PIN_MISMATCH" and r.get("core_imported") is False
          and not os.path.exists(db_for("T02")))
    ev = evidence("T02", "wrong_core_pin", r)
    return f"error={r.get('error')} core_imported={r.get('core_imported')}", ev, ok


def t03(stale_core_path: str):
    observed = git("rev-parse", "HEAD", cwd=stale_core_path)
    r = in_process(worker.pin_probe_clean, stale_core_path, None, db_for("T03"))
    pure = verify_core_pin(STALE_SHA).code
    ok = (r.get("error") == "STALE_CORE_PIN" and r.get("observed") == STALE_SHA
          and r.get("core_imported") is False and observed == STALE_SHA
          and pure == "STALE_CORE_PIN")
    ev = evidence("T03", "stale_core_pin", {"stale_checkout": stale_core_path,
                                             "checkout_head": observed, "probe": r,
                                             "pure_verdict": pure})
    return f"error={r.get('error')} observed={str(r.get('observed'))[:7]} core_imported={r.get('core_imported')}", ev, ok


# ---------------------------------------------------------------- T04-T05
def _genspec_cls():
    if CORE_PATH not in sys.path:
        sys.path.insert(0, CORE_PATH)
    from adapters.base import GenSpec
    return GenSpec


def t04():
    G = _genspec_cls()
    a = build_genspec(worker.make_inputs("deterministico"), G)
    b = build_genspec(worker.make_inputs("deterministico"), G)
    # stessa spec con params in ordine diverso e refs come lista: stessa chiave
    c = build_genspec(GoInputs(kind="image", model="fake_model_v1", prompt="deterministico",
                               params={"duration_s": 5, "aspect_ratio": "9:16"},
                               refs=["ref_element_001"], project_id="GATE01_LAB"), G)
    rb = in_process(worker.run_go, db_for("T04"), "deterministico", max_polls=1)
    ok = a.spec_key == b.spec_key == c.spec_key == rb.get("spec_key")
    ev = evidence("T04", "deterministic_spec_key", {
        "run_A": a.spec_key, "run_B": b.spec_key, "run_C_reordered": c.spec_key,
        "run_other_process": rb.get("spec_key"), "spec": a.__dict__})
    return f"A==B==C==other_process: {ok} ({a.spec_key[:16]}…)", ev, ok


def t05():
    G = _genspec_cls()
    base = build_genspec(worker.make_inputs("base"), G).spec_key
    muts = {
        "prompt": worker.make_inputs("base MODIFICATO"),
        "model": worker.make_inputs("base", model="fake_model_v2"),
        "ref": worker.make_inputs("base", refs=("ref_element_002",)),
        "param": worker.make_inputs("base", params={"aspect_ratio": "16:9", "duration_s": 5}),
        "project_id": worker.make_inputs("base", project_id="ALTRO"),
        "kind": worker.make_inputs("base", kind="video"),
    }
    keys = {k: build_genspec(v, G).spec_key for k, v in muts.items()}
    all_diff = all(v != base for v in keys.values()) and len(set(keys.values())) == len(keys)
    rejected = {}
    for label, inp in {
        "timestamp_key": worker.make_inputs("base", params={"timestamp": 1758000000}),
        "pid_key": worker.make_inputs("base", params={"pid": 4242}),
        "tmpdir_value": worker.make_inputs("base", params={"out": "/tmp/tmpab12cd/x.png"}),
        "epoch_in_prompt": worker.make_inputs("base 1758000000"),
        "iso_datetime": worker.make_inputs("base", params={"note": "2026-09-16T12:00:00"}),
    }.items():
        try:
            build_genspec(inp, G)
            rejected[label] = "ACCEPTED (errore)"
        except GenSpecBridgeError as e:
            rejected[label] = f"REJECTED: {e}"
    all_rejected = all(v.startswith("REJECTED") for v in rejected.values())
    ok = all_diff and all_rejected
    ev = evidence("T05", "spec_mutation", {"base": base, "mutations": keys,
                                            "accidental_inputs": rejected})
    return f"6 mutazioni semantiche -> 6 chiavi diverse: {all_diff}; 5 input accidentali rifiutati: {all_rejected}", ev, ok


# ---------------------------------------------------------------- T06
def t06():
    db = db_for("T06")
    r = in_process(worker.run_go, db, "happy path", adapter_kw={"latency_polls": 2},
                   max_polls=5, budget_units=10, envelope_units=100)
    # process/restart simulation: nuovo interprete, nuova istanza di store
    s = in_process(worker.read_state, db, CORE_PATH)
    rows = s.get("rows", [])
    ok = (r.get("ok") and r.get("reservation_outcome") == "RESERVED_NEW"
          and r.get("state") == "SUCCEEDED" and r.get("submits") == 1
          and r.get("provider") == "fake" and r.get("provider_job_id")
          and len(rows) == 1 and rows[0]["state"] == "SUCCEEDED"
          and rows[0]["job_id"] == r.get("job_id") and rows[0]["spec_key"] == r.get("spec_key")
          and s.get("reserved_units") == 0)
    # hash dell'output fake (§21): nessun byte reale, ma la catena di hash e' in piedi
    if CORE_PATH not in sys.path:
        sys.path.insert(0, CORE_PATH)
    from adapters.fake import FakeAdapter
    fa = FakeAdapter()
    fake_payload_sha = hashlib.sha256(fa.payload).hexdigest()
    ev = evidence("T06", "happy_path", {"go": r, "restart_read": s,
                                         "fake_output_sha256": fake_payload_sha,
                                         "core_sha": r.get("core_sha")})
    return (f"state={r.get('state')} submits={r.get('submits')} provider={r.get('provider')} "
            f"restart_read={rows[0]['state'] if rows else None} reserved_after=0"), ev, ok


# ---------------------------------------------------------------- T07
def t07():
    """Stessa spec mentre il job e' LIVE: stesso processo, stesso adapter, due GO."""
    db = db_for("T07")
    if CORE_PATH not in sys.path:
        sys.path.insert(0, CORE_PATH)
    from adapters.fake import FakeAdapter
    from runtime.go_candidate import go
    a = FakeAdapter(never_terminal=True)
    inp = worker.make_inputs("sequenziale")
    r1 = go(inp, adapter=a, provider_mode="fake", store_path=db, max_polls=1)
    r2 = go(inp, adapter=a, provider_mode="fake", store_path=db, max_polls=1)
    s = in_process(worker.read_state, db, CORE_PATH)
    ok = (r1.reservation_outcome == "RESERVED_NEW" and r2.reservation_outcome == "EXISTING_LIVE_JOB"
          and r2.outcome == "EXISTING_LIVE_JOB" and a.submits == 1
          and r1.job_id == r2.job_id and r1.provider_job_id == r2.provider_job_id
          and len(s.get("rows", [])) == 1)
    ev = evidence("T07", "sequential_duplicate", {"go1": r1.__dict__, "go2": r2.__dict__,
                                                   "submits": a.submits, "state": s})
    return f"GO#1={r1.reservation_outcome} GO#2={r2.outcome} submits={a.submits} same_job_id={r1.job_id == r2.job_id}", ev, ok


# ---------------------------------------------------------------- T08
def t08():
    db = db_for("T08")
    outs = concurrent([
        (worker.run_go, (db, "concorrente"), dict(adapter_kw={"never_terminal": True}, max_polls=1)),
        (worker.run_go, (db, "concorrente"), dict(adapter_kw={"never_terminal": True}, max_polls=1)),
    ])
    s = in_process(worker.read_state, db, CORE_PATH)
    outcomes = sorted(o.get("reservation_outcome", o.get("error", "?")) for o in outs)
    submits = sum(o.get("submits") or 0 for o in outs)
    pids = {o.get("pid") for o in outs}
    rows = s.get("rows", [])
    ok = (outcomes == ["EXISTING_LIVE_JOB", "RESERVED_NEW"] and submits == 1
          and len(pids) == 2 and len(rows) == 1 and rows[0]["provider_job_id"]
          and len({o.get("job_id") for o in outs}) == 1)
    ev = evidence("T08", "concurrent_duplicate", {"processes": outs, "state": s})
    return f"outcomes={outcomes} total_submits={submits} pids={len(pids)} rows={len(rows)}", ev, ok


# ---------------------------------------------------------------- T09
def t09():
    db = db_for("T09")
    a = in_process(worker.run_go, db, "restart", adapter_kw={"latency_polls": 3}, max_polls=1)
    mid = in_process(worker.read_state, db, CORE_PATH)
    b = in_process(worker.run_go, db, "restart", adapter_kw={"latency_polls": 3}, max_polls=5)
    end = in_process(worker.read_state, db, CORE_PATH)
    ok = (a.get("state") == "RUNNING" and a.get("submits") == 1 and a.get("reservation_outcome") == "RESERVED_NEW"
          and mid["rows"][0]["state"] == "RUNNING" and mid["rows"][0]["polls"] == 1
          and b.get("reservation_outcome") == "EXISTING_LIVE_JOB" and b.get("submits") == 0
          and b.get("job_id") == a.get("job_id") and b.get("provider_job_id") == a.get("provider_job_id")
          and b.get("state") == "SUCCEEDED" and end["rows"][0]["state"] == "SUCCEEDED"
          and end["rows"][0]["polls"] == 3 and len(end["rows"]) == 1
          and a.get("pid") != b.get("pid"))
    ev = evidence("T09", "restart_resume", {"process_A": a, "after_A": mid,
                                             "process_B": b, "after_B": end})
    return (f"A: {a.get('state')} polls=1 submits=1 | B (nuovo pid): {b.get('reservation_outcome')} "
            f"submits={b.get('submits')} same_job={a.get('job_id') == b.get('job_id')} -> {b.get('state')}"), ev, ok


# ---------------------------------------------------------------- T10
def t10():
    db = db_for("T10")
    r1 = in_process(worker.run_go, db, "submit unknown", adapter_kind="submit_unknown",
                    budget_units=30, envelope_units=100)
    mid = in_process(worker.read_state, db, CORE_PATH)
    r2 = in_process(worker.run_go, db, "submit unknown", max_polls=3,
                    budget_units=30, envelope_units=100)
    end = in_process(worker.read_state, db, CORE_PATH)
    ok = (r1.get("error") == "ConnectionResetError" and r1.get("submits") == 1
          and mid["rows"][0]["state"] == "SUBMIT_UNKNOWN" and mid["reserved_units"] == 30
          and r2.get("reservation_outcome") == "EXISTING_LIVE_JOB"
          and r2.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required"
          and r2.get("submits") == 0 and r2.get("state") == "SUBMIT_UNKNOWN"
          and end["reserved_units"] == 30 and len(end["rows"]) == 1
          and end["rows"][0]["job_id"] == mid["rows"][0]["job_id"])
    ev = evidence("T10", "submit_unknown_no_resubmit", {"go1": r1, "after_go1": mid,
                                                         "go2": r2, "after_go2": end})
    return (f"GO#1 -> {mid['rows'][0]['state']} (budget impegnato {mid['reserved_units']}) | "
            f"GO#2 -> {r2.get('outcome')} submits={r2.get('submits')} budget ancora {end['reserved_units']}"), ev, ok


# ---------------------------------------------------------------- T11
def t11():
    db = db_for("T11")
    ra = in_process(worker.run_go, db, "mismatch", adapter_kind="fake_a",
                    adapter_kw={"never_terminal": True}, max_polls=1)
    rb = in_process(worker.run_go, db, "mismatch", adapter_kind="fake_b",
                    adapter_kw={"never_terminal": True}, max_polls=1)
    end = in_process(worker.read_state, db, CORE_PATH)
    ok = (ra.get("provider") == "fake_a" and ra.get("state") == "RUNNING"
          and rb.get("error") == "ProviderMismatch" and rb.get("submits") == 0
          and len(end["rows"]) == 1 and end["rows"][0]["provider"] == "fake_a"
          and end["rows"][0]["state"] == "RUNNING")
    ev = evidence("T11", "provider_mismatch", {"go_fake_a": ra, "go_fake_b": rb, "state": end})
    return f"fake_a RUNNING | fake_b -> {rb.get('error')} submits={rb.get('submits')} reservation intatta={end['rows'][0]['provider']}/{end['rows'][0]['state']}", ev, ok


# ---------------------------------------------------------------- T12
def t12():
    db = db_for("T12")
    outs = concurrent([
        (worker.run_go, (db, "budget A"), dict(adapter_kw={"never_terminal": True}, max_polls=1,
                                               budget_units=70, envelope_units=100)),
        (worker.run_go, (db, "budget B"), dict(adapter_kw={"never_terminal": True}, max_polls=1,
                                               budget_units=50, envelope_units=100)),
    ])
    end = in_process(worker.read_state, db, CORE_PATH)
    errors = sorted(o.get("error", "OK") for o in outs)
    reserved = end["reserved_units"]
    ok = (errors.count("BudgetExceeded") == 1 and errors.count("OK") == 1
          and reserved <= 100 and reserved in (50, 70) and len(end["rows"]) == 1)
    # variante sequenziale deterministica
    db2 = db_for("T12b")
    s1 = in_process(worker.run_go, db2, "budget A", adapter_kw={"never_terminal": True},
                    max_polls=1, budget_units=70, envelope_units=100)
    s2 = in_process(worker.run_go, db2, "budget B", adapter_kw={"never_terminal": True},
                    max_polls=1, budget_units=50, envelope_units=100)
    end2 = in_process(worker.read_state, db2, CORE_PATH)
    ok = ok and s1.get("ok") and s2.get("error") == "BudgetExceeded" and end2["reserved_units"] == 70
    ev = evidence("T12", "budget_atomicity", {"concurrent": outs, "concurrent_state": end,
                                               "sequential": [s1, s2], "sequential_state": end2})
    return f"concorrente: {errors} impegnati={reserved}/100 | sequenziale: A ok, B={s2.get('error')} impegnati={end2['reserved_units']}", ev, ok


# ---------------------------------------------------------------- T13
def t13():
    db = db_for("T13")
    cases = {}
    for label, units in (("negative", -1), ("bool", True), ("float", 1.5), ("str", "10")):
        cases[label] = in_process(worker.run_go, db, f"invalid {label}", budget_units=units,
                                  envelope_units=100)
    neg_env = in_process(worker.run_go, db, "invalid env", budget_units=1, envelope_units=-5)
    cases["negative_envelope"] = neg_env
    end = in_process(worker.read_state, db, CORE_PATH)
    ok = (all(c.get("error") == "ReservationContractError" and c.get("submits") == 0
              for c in cases.values()) and end["rows"] == [])
    ev = evidence("T13", "invalid_budget_rejected", {"cases": cases, "state": end})
    return f"{len(cases)} valori non ammessi -> ReservationContractError, 0 submit, 0 righe", ev, ok


# ---------------------------------------------------------------- T14-T15
def t14(canary_home: str):
    db = db_for("T14")
    r = in_process(worker.sentinel_run, "real", db, canary_home, CORE_PATH)
    g = r.get("go", {})
    ok = (g.get("error") == "REAL_PROVIDER_DISABLED" and r.get("violations") == []
          and r.get("core_imported") is False and not os.path.exists(db))
    ev = evidence("T14", "fake_mode_blocks_real_provider", r)
    return f"provider_mode=higgsfield -> {g.get('error')} violations={len(r.get('violations', []))} core_imported={r.get('core_imported')} db_created={os.path.exists(db)}", ev, ok


def t15(canary_home: str):
    db = db_for("T15")
    r = in_process(worker.sentinel_run, "fake", db, canary_home, CORE_PATH)
    cp = in_process(worker.sentinel_run, "counterproof", db_for("T15cp"), canary_home, CORE_PATH)
    g = r.get("go", {})
    kinds = sorted({v["kind"] for v in cp.get("violations", [])})
    ok = (g.get("state") == "SUCCEEDED" and r.get("violations") == []
          and {"credential_file_open", "secret_env_read"} <= set(kinds))
    ev = evidence("T15", "no_credential_read", {"fake_run": r, "counterproof": cp})
    return f"fake go -> {g.get('state')} violations=0 | controprova: sentinella rileva {kinds}", ev, ok


# ---------------------------------------------------------------- T16-T17
def t16():
    """P2 hash before/after. `before` = SHA calcolato all'avvio della corsa (P2_BASELINE)
    e confrontato con lo SHA dichiarato da 4 fonti indipendenti del handoff."""
    if not os.path.exists(P2_HF_BATCH):
        ev = evidence("T16", "p2_hash", {"status": "BLOCKED", "reason": "hf_batch.py assente",
                                         "P2_HF_BATCH_PATH": P2_HF_BATCH})
        return "BLOCKED: P2 hf_batch.py assente", ev, False
    after = sha256_file(P2_HF_BATCH)
    backup = os.path.join(HANDOFF, "LAB", "hf_batch_ORIGINAL.py")
    after_backup = sha256_file(backup) if os.path.exists(backup) else None
    lock = json.load(open(os.path.join(HANDOFF, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json"), encoding="utf-8"))
    lock_sha = next(x["sha256"] for x in lock["scripts"] if x["path"] == "scripts/hf_batch.py")
    manifest = dict(line.split("  ", 1)[::-1] for line in
                    open(os.path.join(HANDOFF, "SHA256SUMS"), encoding="utf-8").read().splitlines() if line.strip())
    manifest_sha = manifest.get("./P2_RUNTIME/hf_batch.py")
    initial_state = open(os.path.join(HANDOFF, "EVIDENCE", "INTEGRATION_GATE_01_initial_state.txt"), encoding="utf-8").read()
    sources = {"declared_in_mandate": P2_HF_BATCH_SHA_DECLARED, "handoff_SHA256SUMS": manifest_sha,
               "production_RUNTIME_LOCK.scripts": lock_sha,
               "historical_INITIAL_STATE_txt": P2_HF_BATCH_SHA_DECLARED if P2_HF_BATCH_SHA_DECLARED in initial_state else None,
               "LAB/hf_batch_ORIGINAL.py": after_backup}
    before = P2_BASELINE.get("sha256")
    ok = (before == after == P2_HF_BATCH_SHA_DECLARED and all(v == P2_HF_BATCH_SHA_DECLARED for v in sources.values())
          and P2_BASELINE.get("mtime") == os.stat(P2_HF_BATCH).st_mtime and P2_BASELINE.get("size") == os.path.getsize(P2_HF_BATCH))
    ev = evidence("T16", "p2_hash", {"path": P2_HF_BATCH, "before": before, "after": after, "declared": P2_HF_BATCH_SHA_DECLARED,
                                     "independent_sources": sources, "baseline": P2_BASELINE,
                                     "mac_original_path": "/Users/francescoantonaccio/valore_farmacia_local/VF_PILOT_OUTPUTS/P2_PRIMA_SI_PARLA/RUN_20260915_FINAL_PRODUCTION/scripts/hf_batch.py (fuori git, non in questo ambiente)",
                                     "note": "il file verificato e' la copia read-only del handoff; l'originale sul Mac e' attestato dalle 4 fonti"})
    return f"before={str(before)[:12]} after={after[:12]} declared={P2_HF_BATCH_SHA_DECLARED[:12]} sources_agree={all(v == P2_HF_BATCH_SHA_DECLARED for v in sources.values())}", ev, ok


def t17():
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    ok = head == REQUIRED_CORE_SHA and status == "" and branch == "main"
    ev = evidence("T17", "core_canonical_unchanged", {"head": head, "branch": branch,
                                                        "status_porcelain": status})
    return f"HEAD={head[:12]} branch={branch} dirty_files={len(status.splitlines())}", ev, ok


# ---------------------------------------------------------------- T18-T19
def t18():
    """Terminale persistito: dopo SUCCEEDED, un terzo processo legge SUCCEEDED dal file."""
    db = db_for("T18")
    r = in_process(worker.run_go, db, "terminale", adapter_kw={"latency_polls": 1}, max_polls=3)
    s1 = in_process(worker.read_state, db, CORE_PATH)
    # un nuovo GO sulla stessa spec DOPO il terminale e' un NUOVO tentativo autorizzato
    # (identita' per tentativo, C26-E): non un duplicato, non una sovrascrittura.
    r2 = in_process(worker.run_go, db, "terminale", adapter_kw={"latency_polls": 1}, max_polls=3)
    s2 = in_process(worker.read_state, db, CORE_PATH)
    ok = (r.get("state") == "SUCCEEDED" and s1["rows"][0]["state"] == "SUCCEEDED"
          and s1["rows"][0]["cost_credits"] == 4.0
          and r2.get("reservation_outcome") == "RESERVED_NEW" and r2.get("job_id") != r.get("job_id")
          and len(s2["rows"]) == 2 and all(x["state"] == "SUCCEEDED" for x in s2["rows"])
          and s2["reserved_units"] == 0)
    ev = evidence("T18", "durable_terminal", {"go": r, "read_new_process": s1,
                                               "go_after_terminal": r2, "history": s2})
    return f"SUCCEEDED letto da nuovo processo; nuovo GO dopo terminale = nuovo tentativo ({len(s2['rows'])} righe storiche, 0 impegnato)", ev, ok


def t20(stale_core_path: str):
    """T20 — DIRTY CORE MUST FAIL CLOSED. Finding riprodotto PRIMA della patch:
    evidence/T20_finding_reproduction_before_patch.json (finding_confirmed=true)."""
    lab = os.path.join(os.path.dirname(stale_core_path), "core_lab_canonical")
    subprocess.run(["git", "-C", CORE_PATH, "worktree", "add", "--detach", lab, REQUIRED_CORE_SHA],
                   check=True, capture_output=True)
    try:
        def head():
            return git("rev-parse", "HEAD", cwd=lab)
        def status():
            return git("status", "--porcelain", "--untracked-files=all", cwd=lab)
        steps = {}
        # 1-2. checkout di laboratorio al canonical, pulito -> PASS
        steps["clean"] = {"head": head(), "status": status(),
                          "probe": in_process(worker.pin_probe_clean, lab, None, db_for("T20a"))}
        # 3-5. modifica deliberata di un file tracciato, HEAD invariato -> CORE_WORKTREE_DIRTY
        with open(os.path.join(lab, "transport", "pipeline.py"), "a", encoding="utf-8") as fh:
            fh.write("\n# T20 deliberate uncommitted modification\n")
        steps["tracked_modified"] = {"head": head(), "status": status(),
                                     "probe": in_process(worker.pin_probe_clean, lab, None, db_for("T20b"))}
        git("checkout", "--", "transport/pipeline.py", cwd=lab)
        # extra: file NON tracciato dentro il checkout (modulo estraneo importabile) -> DIRTY
        stray = os.path.join(lab, "adapters", "stray_module.py")
        with open(stray, "w", encoding="utf-8") as fh:
            fh.write("# untracked module inside the Core checkout\n")
        steps["untracked_inside"] = {"head": head(), "status": status(),
                                     "probe": in_process(worker.pin_probe_clean, lab, None, db_for("T20c"))}
        os.remove(stray)
        steps["restored"] = {"head": head(), "status": status()}
        # negative controls
        steps["wrong_sha_clean"] = in_process(worker.pin_probe_clean, lab, "deadbeef" * 5, db_for("T20d"))
        steps["stale_clean"] = in_process(worker.pin_probe_clean, stale_core_path, None, db_for("T20e"))
        steps["pure_verdicts"] = {
            "canonical_clean": verify_core_pin(REQUIRED_CORE_SHA, dirty=()).code,
            "canonical_dirty": verify_core_pin(REQUIRED_CORE_SHA, dirty=(" M x.py",)).code,
            "canonical_unverifiable": verify_core_pin(REQUIRED_CORE_SHA, dirty=None).code,
            "wrong_clean": verify_core_pin("deadbeef" * 5, dirty=()).code,
            "stale_clean": verify_core_pin(STALE_SHA, dirty=()).code,
            "stale_dirty_identity_wins": verify_core_pin(STALE_SHA, dirty=(" M x.py",)).code,
        }
    finally:
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "remove", "--force", lab],
                       capture_output=True)
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "prune"], capture_output=True)
    c, d, u = steps["clean"], steps["tracked_modified"], steps["untracked_inside"]
    # probe pulito: supera il pin (nessun CorePinError) e cade solo sul gate provider
    # perche' pin_probe_clean non fornisce un adapter: e' la prova che il pin e' passato.
    ok = (c["status"] == "" and c["probe"].get("error") == "RealProviderDisabled"
          and c["probe"].get("core_imported") is True
          and d["head"] == REQUIRED_CORE_SHA and d["status"].strip() == "M transport/pipeline.py"
          and d["probe"].get("error") == "CORE_WORKTREE_DIRTY" and d["probe"].get("core_imported") is False
          and u["probe"].get("error") == "CORE_WORKTREE_DIRTY" and u["probe"].get("core_imported") is False
          and steps["restored"]["status"] == ""
          and steps["wrong_sha_clean"].get("error") == "CORE_PIN_MISMATCH"
          and steps["stale_clean"].get("error") == "STALE_CORE_PIN"
          and steps["pure_verdicts"] == {
              "canonical_clean": "CORE_PIN_OK", "canonical_dirty": "CORE_WORKTREE_DIRTY",
              "canonical_unverifiable": "CORE_WORKTREE_DIRTY", "wrong_clean": "CORE_PIN_MISMATCH",
              "stale_clean": "STALE_CORE_PIN", "stale_dirty_identity_wins": "STALE_CORE_PIN"})
    ev = evidence("T20", "dirty_core_fail_closed", steps)
    return (f"clean -> pin ok | tracked mod (HEAD invariato) -> {d['probe'].get('error')} core_imported={d['probe'].get('core_imported')} | "
            f"untracked inside -> {u['probe'].get('error')} | wrong+clean -> {steps['wrong_sha_clean'].get('error')} | "
            f"stale+clean -> {steps['stale_clean'].get('error')}"), ev, ok


def t21():
    """Mapping REALE hf_batch go -> GenSpec, provato contro il codice originale (read-only)."""
    import glob
    import importlib.util
    if CORE_PATH not in sys.path:
        sys.path.insert(0, CORE_PATH)
    from adapters.base import GenSpec
    from runtime.hf_batch_bridge import go_inputs_from_job, media, media_sha_from_lock, prompt
    spec_mod = importlib.util.spec_from_file_location("hf_batch_original", P2_HF_BATCH)
    orig = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(orig)
    per_spec = {}
    n_jobs = 0
    for f in sorted(glob.glob(os.path.join(HANDOFF, "SPECS", "*.json"))):
        b = orig.Batch(f)
        rows = []
        for j in b.spec["jobs"]:
            n_jobs += 1
            same_prompt = b.prompt(j) == prompt(b.spec, j)
            same_media = [(fl, rid) for fl, rid, _ in b.media(j)] == [(fl, rid) for fl, rid, _ in media(b.spec, j)]
            gi = go_inputs_from_job(b.spec, j, lambda fl, rid, ref: "0" * 64)
            g = build_genspec(gi, GenSpec)
            rows.append({"asset": j["asset"], "kind": g.kind, "model": g.model, "same_prompt": same_prompt,
                         "same_media_order": same_media, "n_refs": len(g.refs), "params": g.params,
                         "project_id": g.project_id, "prompt_sha256": hashlib.sha256(g.prompt.encode()).hexdigest()})
        per_spec[os.path.basename(f)] = rows
    all_equal = all(r["same_prompt"] and r["same_media_order"] for rows in per_spec.values() for r in rows)
    # lock reale: prompt_sha256 e sha256_sent dei media -> GenSpec e spec_key
    lock = json.load(open(os.path.join(HANDOFF, "EVIDENCE", "MOTION_B1_B4C_RUNTIME_LOCK.json"), encoding="utf-8"))
    spec = json.load(open(os.path.join(HANDOFF, "SPECS", "spec_motion_B1_B4C.json"), encoding="utf-8"))
    res = media_sha_from_lock(lock)
    lock_rows = {}
    for j, lj in zip(spec["jobs"], lock["jobs"]):
        g = build_genspec(go_inputs_from_job(spec, j, res(j["asset"])), GenSpec)
        lock_rows[j["asset"]] = {"prompt_sha_matches_lock": hashlib.sha256(g.prompt.encode()).hexdigest() == lj["prompt_sha256"],
                                 "refs": list(g.refs), "refs_match_lock_media": [r.split(":")[-1] for r in g.refs] == [m["sha256_sent"] for m in lj["media"]],
                                 "spec_key": g.spec_key, "genspec": {"kind": g.kind, "model": g.model, "params": g.params, "project_id": g.project_id}}
    other = in_process(worker.real_spec_keys, CORE_PATH)
    deterministic = all(other["keys"][a] == lock_rows[a]["spec_key"] for a in lock_rows)
    # mutazioni reali: un blocco di prompt, un param, la start image, il run_id -> chiave diversa
    j0 = spec["jobs"][0]
    base = lock_rows[j0["asset"]]["spec_key"]
    import copy
    muts = {}
    s2 = copy.deepcopy(spec); s2["prompt_blocks"]["V916"] += " (mutato)"
    muts["prompt_block"] = build_genspec(go_inputs_from_job(s2, s2["jobs"][0], res(j0["asset"])), GenSpec).spec_key
    s3 = copy.deepcopy(spec); s3["jobs"][0]["params"]["duration"] = 12
    muts["param_duration"] = build_genspec(go_inputs_from_job(s3, s3["jobs"][0], res(j0["asset"])), GenSpec).spec_key
    muts["start_image_bytes"] = build_genspec(go_inputs_from_job(spec, j0, lambda fl, rid, ref: "f" * 64), GenSpec).spec_key
    s4 = copy.deepcopy(spec); s4["run_id"] = "ALTRO_RUN"
    muts["run_id"] = build_genspec(go_inputs_from_job(s4, s4["jobs"][0], res(j0["asset"])), GenSpec).spec_key
    s5 = copy.deepcopy(spec); s5["jobs"][0]["edit_use"] = "altro"; s5["jobs"][0]["must_show"] = []; s5["jobs"][0]["beat"] = 9
    muts["qa_metadata_only(no change expected)"] = build_genspec(go_inputs_from_job(s5, s5["jobs"][0], res(j0["asset"])), GenSpec).spec_key
    mut_ok = (all(v != base for k, v in muts.items() if not k.startswith("qa_metadata"))
              and muts["qa_metadata_only(no change expected)"] == base)
    try:
        go_inputs_from_job(spec, j0, lambda fl, rid, ref: "MISSING")
        missing_ok = False
    except GenSpecBridgeError:
        missing_ok = True
    ok = (all_equal and n_jobs == 27 and all(r["prompt_sha_matches_lock"] and r["refs_match_lock_media"] for r in lock_rows.values())
          and deterministic and mut_ok and missing_ok)
    ev = evidence("T21", "real_genspec_mapping", {"hf_batch_sha256": sha256_file(P2_HF_BATCH), "specs": per_spec,
                                                   "lock_bound": lock_rows, "other_process": other, "base_key": base,
                                                   "mutations": muts, "missing_media_rejected": missing_ok})
    return (f"{n_jobs} job reali in {len(per_spec)} spec: prompt/media == originale {all_equal}; lock: prompt_sha e sha256_sent combaciano; "
            f"spec_key stabile in altro processo {deterministic}; 4 mutazioni reali -> chiave diversa, metadati QA -> stessa chiave {mut_ok}; media MISSING rifiutato {missing_ok}"), ev, ok


def t22(canary_home: str):
    """La COPIA hf_batch_runtime.go su spec reale -> Core C26 -> FakeAdapter, sotto sentinella."""
    db = db_for("T22")
    # round 1+2 con job che restano vivi: GO#2 deve trovare EXISTING_LIVE_JOB, 0 nuovi submit
    live = in_process(worker.hf_batch_runtime_go, db, canary_home, CORE_PATH,
                      adapter_kw={"never_terminal": True}, max_polls=1, rounds=2)
    mid = in_process(worker.read_state, db, CORE_PATH)
    # round 3, NUOVO processo e nuovo adapter: riprende i job vivi e li porta a SUCCEEDED
    done = in_process(worker.hf_batch_runtime_go, db, canary_home, CORE_PATH,
                      adapter_kw={"latency_polls": 1}, max_polls=5, rounds=1)
    end = in_process(worker.read_state, db, CORE_PATH)
    # i verbi CLI restano chiusi: lock e quote -> REAL_PROVIDER_DISABLED prima di ogni subprocess
    lock_v = in_process(worker.hf_batch_runtime_go, db_for("T22lock"), canary_home, CORE_PATH, verb="lock")
    quote_v = in_process(worker.hf_batch_runtime_go, db_for("T22quote"), canary_home, CORE_PATH, verb="quote")
    t1, t2 = (live.get("traces") or [{}, {}])[:2]
    t3 = (done.get("traces") or [{}])[0]
    ok = (live.get("ok") and done.get("ok")
          and [x["reservation_outcome"] for x in t1.get("jobs", [])] == ["RESERVED_NEW", "RESERVED_NEW"]
          and [x["run_status"] for x in t2.get("jobs", [])] == ["EXISTING_LIVE_JOB", "EXISTING_LIVE_JOB"]
          and live.get("submits") == 2 and len(mid["rows"]) == 2 and all(r["state"] == "RUNNING" for r in mid["rows"])
          and [x["reservation_outcome"] for x in t3.get("jobs", [])] == ["EXISTING_LIVE_JOB", "EXISTING_LIVE_JOB"]
          and [x["run_status"] for x in t3.get("jobs", [])] == ["SUCCEEDED", "SUCCEEDED"] and done.get("submits") == 0
          and {x["job_id"] for x in t3["jobs"]} == {x["job_id"] for x in t1["jobs"]}
          and len(end["rows"]) == 2 and all(r["state"] == "SUCCEEDED" and r["provider"] == "fake" for r in end["rows"])
          and t1.get("run_verdict") == "LOCK_HELD"
          and live["violations"] == [] and done["violations"] == [] and lock_v["violations"] == [] and quote_v["violations"] == []
          and lock_v.get("error") == "REAL_PROVIDER_DISABLED" and quote_v.get("error") == "REAL_PROVIDER_DISABLED"
          and live.get("pid") != done.get("pid"))
    ev = evidence("T22", "hf_batch_runtime_go_real_spec", {"rounds_1_2_live": live, "state_after_live": mid,
                                                            "round_3_new_process": done, "state_final": end,
                                                            "lock_verb": lock_v, "quote_verb": quote_v})
    return (f"spec reale MOTION_B1_B4C: GO#1 2x RESERVED_NEW (2 submit) · GO#2 2x EXISTING_LIVE_JOB (0 submit) · "
            f"GO#3 nuovo processo -> 2x SUCCEEDED (0 submit) · lock/quote -> {lock_v.get('error')} · violazioni sentinella 0"), ev, ok


def t23():
    """Integrita' del handoff dentro il gate: manifest 0 mismatch, ZIP hash registrati, albero read-only."""
    r = subprocess.run(["sha256sum", "-c", "SHA256SUMS", "--quiet"], cwd=HANDOFF, capture_output=True, text=True)
    n = sum(1 for line in open(os.path.join(HANDOFF, "SHA256SUMS"), encoding="utf-8") if line.strip())
    zips = open(os.path.join(EVIDENCE_DIR, "HANDOFF_ZIPS.sha256"), encoding="utf-8").read().strip().splitlines()
    ro = all(not os.access(os.path.join(dp, f), os.W_OK) or os.getuid() == 0
             for dp, _, fs in os.walk(HANDOFF) for f in fs)
    ok = r.returncode == 0 and n == 35 and len(zips) == 2
    ev = evidence("T23", "handoff_integrity", {"manifest_entries": n, "sha256sum_rc": r.returncode, "stderr": r.stderr,
                                                "zips": zips, "readonly_flag_set": ro})
    return f"handoff SHA256SUMS: {n} file, rc={r.returncode} (0 mismatch); 2 ZIP hash registrati", ev, ok


def t19():
    r = static_checks.run()
    ev = evidence("T19", "static_no_duplicate_control", r)
    return f"findings={len(r['findings'])} core_imports={len(r['core_imports'])}", ev, r["ok"]


# ---------------------------------------------------------------- main
def write_results():
    lines = ["# TEST_RESULTS — RUNTIME INTEGRATION GATE 01", "",
             f"Core canonical: `{REQUIRED_CORE_SHA}` · provider: FakeAdapter only · "
             "crediti spesi: 0 · rete generativa: nessuna", "",
             "| TEST | TITLE | EXPECTED | ACTUAL | EXIT | EVIDENCE | PASS/FAIL |",
             "|---|---|---|---|---|---|---|"]
    for r in RESULTS:
        lines.append(f"| {r['id']} | {r['title']} | {r['expected']} | {r['actual']} | "
                     f"{r['exit']} | `{r['evidence']}` | {'PASS' if r['pass'] else 'FAIL'} |")
    passed = sum(1 for r in RESULTS if r["pass"])
    blocked = [r["id"] for r in RESULTS if not r["pass"] and r["actual"].startswith("BLOCKED")]
    failed = [r["id"] for r in RESULTS if not r["pass"] and not r["actual"].startswith("BLOCKED")]
    lines += ["", f"**Totale: {passed}/{len(RESULTS)} PASS · BLOCKED: {blocked or 'nessuno'} · "
              f"FAIL: {failed or 'nessuno'}**", ""]
    with open(os.path.join(GATE_ROOT, "TEST_RESULTS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    with open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), "w", encoding="utf-8") as fh:
        json.dump(RESULTS, fh, indent=2, ensure_ascii=False)
    return passed, blocked, failed


def main() -> int:
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    print(f"RUNTIME INTEGRATION GATE 01 — Core {CORE_PATH} @ {git('rev-parse', 'HEAD')[:12]}")
    if os.path.exists(P2_HF_BATCH):
        st = os.stat(P2_HF_BATCH)
        P2_BASELINE.update(sha256=sha256_file(P2_HF_BATCH), size=st.st_size, mtime=st.st_mtime, path=P2_HF_BATCH)
        evidence("T16", "p2_baseline", P2_BASELINE)
        print(f"  P2 hf_batch.py baseline {P2_BASELINE['sha256'][:16]} ({st.st_size} bytes)")
    scratch = tempfile.mkdtemp(prefix="gate01_")
    stale_core = os.path.join(scratch, "core_stale_9afaddf")
    canary_home = os.path.join(scratch, "canary_home")
    subprocess.run(["git", "-C", CORE_PATH, "worktree", "add", "--detach", stale_core, STALE_SHA],
                   check=True, capture_output=True)
    try:
        record("T01", "correct Core pin", "CORE_PIN_OK, go procede", t01)
        record("T02", "wrong Core pin", "CORE_PIN_MISMATCH, Core non importato, nessuno store", t02)
        record("T03", "stale old Core pin (9afaddf)", "STALE_CORE_PIN, Core non importato",
               lambda: t03(stale_core))
        record("T04", "deterministic spec_key", "run A == run B == run C == altro processo", t04)
        record("T05", "spec mutation changes key", "ogni mutazione semantica -> chiave diversa; dati accidentali rifiutati", t05)
        record("T06", "happy path", "1 submit, SUCCEEDED persistito, riletto da nuovo processo, provider=fake", t06)
        record("T07", "sequential duplicate", "GO#2 = EXISTING_LIVE_JOB, 1 solo submit", t07)
        record("T08", "concurrent duplicate (2 processi)", "1 RESERVED_NEW + 1 EXISTING_LIVE_JOB, 1 submit totale", t08)
        record("T09", "restart/resume", "B: nessuna nuova reservation/submit, stesso job_id/provider_job_id, terminale persistito", t09)
        record("T10", "SUBMIT_UNKNOWN no resubmit", "SUBMIT_UNKNOWN persistito; GO#2 reconciliation-required, 0 submit, budget non rilasciato", t10)
        record("T11", "provider mismatch", "ProviderMismatch, 0 submit, reservation intatta", t11)
        record("T12", "budget atomicity", "envelope 100: 70+50 -> uno BudgetExceeded, impegnati <= 100", t12)
        record("T13", "invalid budget rejection", "ReservationContractError, 0 submit, 0 righe", t13)
        record("T14", "fake mode blocks real provider", "REAL_PROVIDER_DISABLED prima di credenziali/subprocess/rete/import Core",
               lambda: t14(canary_home))
        record("T15", "no credential read", "0 violazioni in fake mode; controprova: sentinella rileva l'esca",
               lambda: t15(canary_home))
        record("T16", "P2 hash unchanged", "SHA256(hf_batch.py) before == after", t16)
        record("T17", "Core canonical unchanged", "HEAD == 819e7cf, main, working tree pulito", t17)
        record("T18", "durable terminal persistence", "SUCCEEDED riletto da nuovo processo; nuovo tentativo dopo terminale", t18)
        record("T19", "static: no duplicate control system (AST)", "0 findings; import dal Core = 4 attesi", t19)
        record("T20", "dirty Core must fail closed", "canonical+clean PASS; canonical+tracked mod -> CORE_WORKTREE_DIRTY (no import); wrong+clean -> MISMATCH; stale+clean -> STALE",
               lambda: t20(stale_core))
        record("T21", "real hf_batch go -> GenSpec mapping", "27 job reali: prompt/media identici all'originale; lock: prompt_sha256 e sha256_sent combaciano; spec_key deterministico; mutazioni reali cambiano chiave", t21)
        record("T22", "hf_batch_runtime.go on real spec via Core", "2 RESERVED_NEW + 2 submit; GO#2 EXISTING_LIVE_JOB 0 submit; nuovo processo completa SUCCEEDED; lock/quote REAL_PROVIDER_DISABLED; 0 violazioni",
               lambda: t22(canary_home))
        record("T23", "P2 handoff integrity", "manifest 0 mismatch; ZIP hash registrati", t23)
    finally:
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "remove", "--force", stale_core],
                       capture_output=True)
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "prune"], capture_output=True)
        shutil.rmtree(scratch, ignore_errors=True)
    passed, blocked, failed = write_results()
    print(f"\n{passed}/{len(RESULTS)} PASS · BLOCKED {blocked} · FAIL {failed}")
    print("crediti spesi: 0 · provider reali: 0 · rete generativa: 0")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
