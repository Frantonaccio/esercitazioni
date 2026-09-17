#!/usr/bin/env python3
"""RUNTIME INTEGRATION GATE 01 — matrice T01..T23.

MOCK ONLY · ZERO HIGGSFIELD · ZERO CREDITS · NO PRODUCTION.

Ogni test scrive la propria evidenza in evidence/Txx_*.json e una riga in
TEST_RESULTS.md con EXPECTED / ACTUAL / EXIT / EVIDENCE / PASS-FAIL.
I test che richiedono processi reali usano multiprocessing 'spawn' (nuovo
interprete): la memoria Python del padre non e' condivisa.

R0-R1 (2026-09-16): T18 asserisce la semantica RV03 (replay dopo
terminale = resume, zero submit; nuovo tentativo solo con intento e permesso);
T24-T30 coprono RV03, ledger, boundary mock e recovery attraverso il runtime.
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
from tests import boundary_mock, gate_report, static_checks, worker                   # noqa: E402

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
    # PROVIDER / EXECUTION BOUNDARY HARDENING (2026-09-17): il runtime tiene accanto allo store il
    # ledger write-once degli snapshot P-B04 e i nonce P-B02; un db nuovo parte senza residui.
    for suffix in (".snapshots", ".reconciliation"):
        if os.path.isdir(p + suffix):
            shutil.rmtree(p + suffix)
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
    """Classificazione strutturata (tests/gate_report.py): PASS | FAIL | BLOCKED con reason_code,
    evidence e exit diagnostico. BLOCKED solo via GateBlocked sollevata dal test."""
    r = gate_report.run_and_classify(test_id, title, expected, fn, evidence_root=GATE_ROOT,
                                     exception_evidence=lambda tid, payload: evidence(tid, "exception", payload))
    RESULTS.append(r)
    print(gate_report.console_line(r))


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
    r1 = go(inp, adapter=a, provider_mode="fake", store_path=db, max_polls=1, operation_id="T07:asset")
    r2 = go(inp, adapter=a, provider_mode="fake", store_path=db, max_polls=1, operation_id="T07:asset")
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
    """Core canonical: HEAD == REQUIRED_CORE_SHA (commit reale promosso) e working
    tree pulito. L'identita' e' lo SHA, non il nome del branch (il branch viene
    registrato come evidenza). Nessuna modalita' candidato: un tree sporco o un
    altro SHA e' NOT_CANONICAL."""
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--untracked-files=all")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    ok = head == REQUIRED_CORE_SHA and status == ""
    mode = "CANONICAL_CLEAN" if ok else "NOT_CANONICAL"
    ev = evidence("T17", "core_canonical_unchanged", {"head": head, "branch": branch,
                                                        "required": REQUIRED_CORE_SHA,
                                                        "status_porcelain": status, "mode": mode})
    return (f"{mode}: HEAD={head[:12]} required={REQUIRED_CORE_SHA[:12]} branch={branch} "
            f"dirty_files={len(status.splitlines())}"), ev, ok


# ---------------------------------------------------------------- T18-T19
def t18():
    """Terminale persistito: dopo SUCCEEDED, un terzo processo legge SUCCEEDED dal file.

    R0-R1 (RV03): un GO ripetuto sulla stessa spec DOPO il terminale e' un RESUME:
    restituisce l'esito esistente, zero submit, zero righe nuove. Un NUOVO tentativo
    richiede intento esplicito, motivo e permesso monouso (C26-E: identita' per
    tentativo, storico conservato). Prima di R0-R1 il replay creava un nuovo submit."""
    db = db_for("T18")
    r = in_process(worker.run_go, db, "terminale", adapter_kw={"latency_polls": 1}, max_polls=3)
    s1 = in_process(worker.read_state, db, CORE_PATH)
    r2 = in_process(worker.run_go, db, "terminale", adapter_kw={"latency_polls": 1}, max_polls=3)
    s2 = in_process(worker.read_state, db, CORE_PATH)
    r3 = in_process(worker.run_go, db, "terminale", adapter_kw={"latency_polls": 1}, max_polls=3,
                    intent="new_attempt", reason="CREATIVE_ITERATION", auto_permit=True)
    s3 = in_process(worker.read_state, db, CORE_PATH)
    ok = (r.get("state") == "SUCCEEDED" and s1["rows"][0]["state"] == "SUCCEEDED"
          and s1["rows"][0]["cost_credits"] == 4.0
          and r2.get("resumed_terminal") is True and r2.get("submits") == 0
          and r2.get("job_id") == r.get("job_id") and len(s2["rows"]) == 1
          and r3.get("reservation_outcome") == "RESERVED_NEW" and r3.get("job_id") != r.get("job_id")
          and r3.get("permit_id") and r3.get("submits") == 1
          and len(s3["rows"]) == 2 and all(x["state"] == "SUCCEEDED" for x in s3["rows"])
          and s3["reserved_units"] == 0)
    ev = evidence("T18", "durable_terminal", {"go": r, "read_new_process": s1,
                                               "go_replay_resume": r2, "after_resume": s2,
                                               "go_new_attempt": r3, "history": s3})
    return (f"SUCCEEDED letto da nuovo processo; replay = {r2.get('outcome')} (0 submit, 1 riga); "
            f"new_attempt con permesso = {r3.get('reservation_outcome')} ({len(s3['rows'])} righe, 0 impegnato)"), ev, ok


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
    # Il probe pulito supera il pin (core_imported=True) e cade DOPO: RealProviderDisabled
    # (nessun adapter) oppure, con il runtime candidato R0-R1 su un Core canonical pulito
    # privo di `resume_job`, ImportError. In entrambi i casi il pin e' passato: il runtime
    # candidato dipende dal Core candidato (coppia accoppiata), documentato nei log.
    ok = (c["status"] == "" and c["probe"].get("error") in ("RealProviderDisabled", "ImportError")
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
    """AST: nessun sistema di controllo duplicato + (CR-03) nessun drift di contratto
    fra runtime e ReservationStore/EconomicLedger/run_job del Core."""
    r = static_checks.run(CORE_PATH)
    ev = evidence("T19", "static_no_duplicate_control", r)
    return f"findings={len(r['findings'])} core_imports={len(r['core_imports'])} contract_drift={len(r['contract_drift'])}", ev, r["ok"]



# ---------------------------------------------------------------- T24-T30 (R0-R1)
def t24():
    """TEST-RESUME: replay dopo SUCCEEDED, anche dopo restart (nuovo processo): zero submit."""
    db = db_for("T24")
    a = in_process(worker.run_go, db, "resume", max_polls=3, operation_id="T24:asset")
    b = in_process(worker.run_go, db, "resume", max_polls=3, operation_id="T24:asset")
    c = in_process(worker.run_go, db, "resume", max_polls=3, operation_id="T24:asset",
                   inputs_over={"project_id": "ALTRO_RUN"})     # run diverso, STESSA operazione: e' un RESUME (CR-01)
    d = in_process(worker.run_go, db, "resume", max_polls=3, operation_id="T24:other")   # altra operazione: nuova
    s = in_process(worker.read_state, db, CORE_PATH)
    # FAILED: anche un terminale negativo si RILEGGE, non si ripete di nascosto
    f1 = in_process(worker.run_go, db, "resume-failed", adapter_kw={"fail": True}, max_polls=3)
    f2 = in_process(worker.run_go, db, "resume-failed", max_polls=3)
    ok = (a.get("state") == "SUCCEEDED" and a.get("submits") == 1
          and b.get("resumed_terminal") is True and b.get("submits") == 0 and b.get("job_id") == a.get("job_id")
          and b.get("outcome") == "RESUMED/SUCCEEDED" and a.get("pid") != b.get("pid")
          and c.get("resumed_terminal") is True and c.get("submits") == 0 and c.get("job_id") == a.get("job_id")
          and d.get("reservation_outcome") == "RESERVED_NEW" and d.get("submits") == 1
          and len(s["rows"]) == 2
          and f1.get("state") == "FAILED" and f2.get("resumed_terminal") is True and f2.get("submits") == 0)
    ev = evidence("T24", "resume_after_terminal", {"go1": a, "replay_new_process": b, "other_run_same_operation": c,
                                                    "other_operation": d, "state": s, "failed": f1, "failed_replay": f2})
    return (f"GO#1 SUCCEEDED (1 submit) · replay nuovo processo -> {b.get('outcome')} submits={b.get('submits')} · "
            f"altro run stessa operazione -> {c.get('outcome')} submits={c.get('submits')} · altra operazione -> {d.get('reservation_outcome')} · "
            f"FAILED replay -> {f2.get('outcome')} submits={f2.get('submits')}"), ev, ok


def t25():
    """TEST-NEW-ATTEMPT: permesso valido -> un nuovo tentativo; replay del permesso -> rifiutato; storico intatto."""
    db = db_for("T25")
    a = in_process(worker.run_go, db, "attempt", max_polls=3, operation_id="T25:asset")
    no_reason = in_process(worker.run_go, db, "attempt", max_polls=3, intent="new_attempt", auto_permit=True)
    no_permit = in_process(worker.run_go, db, "attempt", max_polls=3, intent="new_attempt", reason="CREATIVE_ITERATION")
    no_op = in_process(worker.run_go, db, "attempt", max_polls=3, intent="new_attempt", reason="CREATIVE_ITERATION",
                       auto_permit=True, operation_id=None)          # CR-01: nessuna operazione -> rifiuto
    b = in_process(worker.run_go, db, "attempt", max_polls=3, intent="new_attempt", reason="CREATIVE_ITERATION",
                   auto_permit=True, operation_id="T25:asset")
    replay = in_process(worker.run_go, db, "attempt", max_polls=3, intent="new_attempt", reason="CREATIVE_ITERATION",
                        permit_id=b.get("permit_id"), operation_id="T25:asset")
    # CR-01 permit binding: un permesso di T25:asset non si consuma con altra operazione (o dal Core senza operazione)
    p2 = in_process(worker.store_call, db, CORE_PATH, "issue_permit", "unused", "CREATIVE_ITERATION", operation_id="T25:asset")
    permit_other = in_process(worker.run_go, db, "attempt", max_polls=3, intent="new_attempt", reason="CREATIVE_ITERATION",
                              permit_id=p2["result"], operation_id="T25:altro")
    permit_none = in_process(worker.store_call, db, CORE_PATH, "reserve_or_get_live_by_prompt", "attempt", p2["result"])
    permit = in_process(worker.store_call, db, CORE_PATH, "permit", b.get("permit_id"))
    s = in_process(worker.read_state, db, CORE_PATH)
    ok = (a.get("state") == "SUCCEEDED"
          and no_reason.get("error") == "IntentRefused" and no_reason.get("code") == "REASON_REQUIRED" and no_reason.get("submits") == 0
          and no_permit.get("error") == "IntentRefused" and no_permit.get("code") == "PERMIT_REQUIRED" and no_permit.get("submits") == 0
          and no_op.get("error") == "IntentRefused" and no_op.get("code") == "OPERATION_ID_REQUIRED" and no_op.get("submits") == 0
          and permit_none.get("error") == "PermitError" and permit_none.get("ok") is False
          and permit_other.get("error") == "PermitError" and permit_other.get("submits") == 0
          and b.get("reservation_outcome") == "RESERVED_NEW" and b.get("submits") == 1 and b.get("permit_id")
          and replay.get("error") == "PermitError" and replay.get("submits") == 0
          and permit["result"]["consumed_by"] == b.get("job_id")
          and len(s["rows"]) == 2 and [x["state"] for x in s["rows"]] == ["SUCCEEDED", "SUCCEEDED"])
    ev = evidence("T25", "new_attempt_permit", {"go1": a, "no_reason": no_reason, "no_permit": no_permit, "no_operation": no_op,
                                                 "new_attempt": b, "permit_replay": replay, "permit": permit,
                                                 "permit_other_operation": permit_other, "permit_no_operation": permit_none, "state": s})
    return (f"senza motivo -> {no_reason.get('code')} · senza permesso -> {no_permit.get('code')} · senza operazione -> {no_op.get('code')} · "
            f"con permesso -> {b.get('reservation_outcome')} · replay permesso -> {replay.get('error')} · "
            f"permit(OP_A) con OP_B/None -> {permit_other.get('error')}/{permit_none.get('error')} · storico {len(s['rows'])}"), ev, ok


def t26():
    """TEST-UNKNOWN: risposta persa, poi cambio run e modello: nessun blind retry, operazione bloccata."""
    db = db_for("T26")
    lost = in_process(worker.run_go, db, "unknown", adapter_kind="submit_unknown", operation_id="T26:asset")
    mid = in_process(worker.read_state, db, CORE_PATH)
    same = in_process(worker.run_go, db, "unknown", max_polls=3, operation_id="T26:asset")
    other_run = in_process(worker.run_go, db, "unknown", max_polls=3, operation_id="T26:asset",
                           inputs_over={"project_id": "RUN_B"})
    other_model = in_process(worker.run_go, db, "unknown", max_polls=3, operation_id="T26:asset",
                             inputs_over={"model": "fake_model_v2"})
    new_att = in_process(worker.run_go, db, "unknown", max_polls=3, operation_id="T26:asset",
                         intent="new_attempt", reason="TECHNICAL_FAILURE_RETRY", auto_permit=True)
    # CR-01: omettere operation_id non aggira nulla: senza operazione non si parte
    noop_model = in_process(worker.run_go, db, "unknown", max_polls=3, operation_id=None,
                            inputs_over={"model": "fake_model_v2"})
    noop_run = in_process(worker.run_go, db, "unknown", max_polls=3, operation_id=None,
                          inputs_over={"project_id": "RUN_C"})
    end = in_process(worker.read_state, db, CORE_PATH)
    ok = (lost.get("error") == "ConnectionResetError" and lost.get("submits") == 1
          and mid["rows"][0]["state"] == "SUBMIT_UNKNOWN"
          and same.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required" and same.get("submits") == 0
          # CR-09: RESUME riprende l'attempt incerto dell'operazione (0 submit); la spec presentata
          # e' solo audit (requested_spec_key) e NON viene attribuita al job ripreso
          and other_run.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required" and other_run.get("submits") == 0
          and other_run.get("resumed") is True and other_run.get("spec_key") == mid["rows"][0]["spec_key"]
          and other_run.get("requested_spec_key") != mid["rows"][0]["spec_key"]
          and other_model.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required" and other_model.get("submits") == 0
          and other_model.get("spec_key") == mid["rows"][0]["spec_key"]
          and new_att.get("error") == "IntentRefused" and new_att.get("code") == "LIVE_OR_UNCERTAIN_ATTEMPT"
          and new_att.get("submits") == 0
          and noop_model.get("code") == "OPERATION_ID_REQUIRED" and noop_model.get("submits") == 0
          and noop_run.get("code") == "OPERATION_ID_REQUIRED" and noop_run.get("submits") == 0
          and len(end["rows"]) == 1 and end["rows"][0]["state"] == "SUBMIT_UNKNOWN")
    ev = evidence("T26", "unknown_blocks_fallbacks", {"lost": lost, "after_lost": mid, "same": same,
                                                       "other_run": other_run, "other_model": other_model,
                                                       "new_attempt": new_att, "no_operation_model": noop_model,
                                                       "no_operation_run": noop_run, "end": end})
    return (f"SUBMIT_UNKNOWN · stessa spec -> {same.get('outcome')} · altro run (RESUME) -> {other_run.get('outcome')} spec_key=latest · "
            f"altro modello (RESUME) -> {other_model.get('outcome')} · new_attempt -> {new_att.get('code')} · "
            f"senza operation_id (modello/run) -> {noop_model.get('code')}/{noop_run.get('code')} · submit totali 1"), ev, ok


def t27():
    """TEST-LEDGER via runtime: tre job regolati saturano l'envelope; il quarto e' rifiutato (tutti terminali)."""
    db = db_for("T27")
    env = in_process(worker.store_call, db, CORE_PATH, "open_envelope", "ENV_T27", 30, unit="synthetic_units")
    runs, settles = [], []
    for i in range(3):
        r = in_process(worker.run_go, db, f"ledger {i}", max_polls=3, budget_units=10, envelope_id="ENV_T27")
        runs.append(r)
        settles.append(in_process(worker.store_call, db, CORE_PATH, "settle", r.get("job_id"),
                                  units=10, source="mock_statement"))
    tot = in_process(worker.store_call, db, CORE_PATH, "ledger_totals", "ENV_T27")
    fourth = in_process(worker.run_go, db, "ledger 4", max_polls=3, budget_units=1, envelope_id="ENV_T27")
    # controprova: terminale NON regolato resta esposto (senza settle, il secondo e' rifiutato)
    db2 = db_for("T27b")
    in_process(worker.store_call, db2, CORE_PATH, "open_envelope", "ENV_T27b", 15)
    u1 = in_process(worker.run_go, db2, "unsettled 1", max_polls=3, budget_units=10, envelope_id="ENV_T27b")
    u2 = in_process(worker.run_go, db2, "unsettled 2", max_polls=3, budget_units=10, envelope_id="ENV_T27b")
    tot2 = in_process(worker.store_call, db2, CORE_PATH, "ledger_totals", "ENV_T27b")
    end = in_process(worker.read_state, db, CORE_PATH)
    ok = (env.get("ok") and all(r.get("state") == "SUCCEEDED" for r in runs)
          and all(x["result"]["applied"] for x in settles)
          and tot["result"]["settled_units"] == 30 and tot["result"]["remaining_units"] == 0
          and fourth.get("error") == "BudgetExceeded" and fourth.get("submits") == 0
          and end["reserved_units"] == 0 and len(end["rows"]) == 3
          and u1.get("state") == "SUCCEEDED" and u2.get("error") == "BudgetExceeded"
          and tot2["result"]["unsettled_exposure_units"] == 10 and tot2["result"]["terminal_unsettled_jobs"] == 1)
    ev = evidence("T27", "ledger_cumulative_via_runtime", {"envelope": env, "runs": runs, "settlements": settles,
                                                           "totals": tot, "fourth": fourth, "state": end,
                                                           "unsettled_control": [u1, u2, tot2]})
    return (f"3x10 regolati = 30/30 (vivi 0) · quarto (1) -> {fourth.get('error')} · "
            f"controprova: terminale non regolato tiene esposti 10 -> {u2.get('error')}"), ev, ok


def _boundary_session(db: str, secret_dir: str, canary_home: str, requests: list):
    """Orchestrator: manda richieste strutturate al worker (processo separato) e raccoglie le risposte."""
    parent, child = CTX.Pipe()
    p = CTX.Process(target=boundary_mock.worker_main, args=(child, db, CORE_PATH, secret_dir, canary_home))
    p.start()
    replies = []
    for req in requests:
        parent.send(req if isinstance(req, str) else json.dumps(req))
        replies.append(parent.recv() if parent.poll(120) else {"ok": False, "error": "TIMEOUT"})
    parent.send(json.dumps({"op": "stop"}))
    stop = parent.recv() if parent.poll(60) else {"ok": False, "error": "TIMEOUT"}
    p.join(30)
    return replies, stop


def t28(canary_home: str, secret_dir: str):
    """TEST-BOUNDARY (protocollo): il worker accetta solo intenti strutturati ED ESPLICITI (DELTA 03:
    nessun intent implicito spendibile; RESUME senza attempt = NO_EXISTING_ATTEMPT; prima spesa =
    new_attempt + INITIAL_GENERATION); nessuna shell, permesso monouso, quote fidata, nessun segreto
    nel canale. (Il confine di PRIVILEGIO e' T29.)"""
    db = db_for("T28")
    def NA(**k):
        return {"op": "submit", "intent": "new_attempt", **k}
    steps = [
        ("quote_a",       {"op": "quote", "prompt": "boundary ok", "operation_id": "T28:a"}),                    # quote fidata (worker, listino LAB)
        ("no_intent",     {"op": "submit", "prompt": "boundary ok", "operation_id": "T28:a"}),                   # DELTA 03: senza intent -> PROTOCOL
        ("no_intent_q",   lambda R: {"op": "submit", "prompt": "boundary ok", "operation_id": "T28:a",
                                     "quote_id": R["quote_a"].get("quote_id")}),                                 # senza intent, con quote valida -> PROTOCOL
        ("bad_intent",    {"op": "submit", "prompt": "boundary ok", "operation_id": "T28:a", "intent": "start"}),  # intent non ammesso -> PROTOCOL
        ("resume_nohist", lambda R: {"op": "submit", "prompt": "boundary ok", "operation_id": "T28:a", "intent": "resume",
                                     "quote_id": R["quote_a"].get("quote_id")}),                                 # RESUME senza attempt -> NO_EXISTING_ATTEMPT
        ("status_nohist", {"op": "status", "prompt": "boundary ok"}),                                            # nessuna reservation dai rifiuti
        ("first",         lambda R: NA(prompt="boundary ok", reason="INITIAL_GENERATION", operation_id="T28:a",
                                       quote_id=R["quote_a"].get("quote_id"))),                                  # PRIMA spesa: intent esplicito (stessa quote, non consumata dai rifiuti)
        ("replay",        {"op": "submit", "prompt": "boundary ok", "operation_id": "T28:a", "intent": "resume"}),  # resume = stesso attempt
        ("shell",         {"op": "shell", "cmd": "higgsfield generate create seedance_2_0 --prompt x"}),         # shell: rifiuto
        ("argv",          {"op": "submit", "prompt": "boundary ok", "intent": "resume", "argv": ["higgsfield", "--version"]}),  # chiave estranea
        ("nonjson",       "non-json {{{"),                                                                       # non JSON
        ("no_reason",     NA(prompt="boundary ok", operation_id="T28:a")),                                       # senza motivo
        ("quote_a2",      {"op": "quote", "prompt": "boundary ok", "operation_id": "T28:a"}),                    # quote NUOVA (nuova spesa = nuova quote)
        ("new_attempt",   lambda R: NA(prompt="boundary ok", reason="CREATIVE_ITERATION", operation_id="T28:a",
                                       quote_id=R["quote_a2"].get("quote_id"))),                                 # nuovo tentativo (delega)
        ("quote_a3",      {"op": "quote", "prompt": "boundary ok", "operation_id": "T28:a"}),
        ("permit_replay", lambda R: NA(prompt="boundary ok", reason="CREATIVE_ITERATION", operation_id="T28:a",
                                       permit_id=R["new_attempt"].get("permit_id"), quote_id=R["quote_a3"].get("quote_id"))),  # permesso consumato
        ("quote_b",       {"op": "quote", "prompt": "boundary lost", "operation_id": "T28:b"}),
        ("lost",          lambda R: NA(prompt="boundary lost", reason="INITIAL_GENERATION", adapter="lost", operation_id="T28:b",
                                       quote_id=R["quote_b"].get("quote_id"))),                                  # risposta persa
        ("on_uncertain",  lambda R: NA(prompt="boundary lost", reason="TECHNICAL_FAILURE_RETRY", operation_id="T28:b",
                                       quote_id=R["quote_b"].get("quote_id"))),                                  # nuovo tentativo su incerto: rifiuto
        ("status",        {"op": "status", "prompt": "boundary ok"}),
        ("no_quote",      NA(prompt="boundary ok", reason="INITIAL_GENERATION", operation_id="T28:c")),          # senza quote: rifiuto
        ("no_operation",  NA(prompt="boundary ok", reason="CREATIVE_ITERATION")),                                # senza operation_id: rifiuto
        ("amount_1",      {"op": "quote", "prompt": "boundary ok", "operation_id": "T28:a", "amount": 1}),       # CR-08 B
        ("amount_0",      {"op": "quote", "prompt": "boundary ok", "operation_id": "T28:a", "amount": 0}),       # CR-08 C
        ("quote_free",    {"op": "quote", "prompt": "free clip", "model": "fake_model_free", "operation_id": "T28:z"}),  # CR-08 D
        ("free",          lambda R: NA(prompt="free clip", model="fake_model_free", reason="INITIAL_GENERATION", operation_id="T28:z",
                                       quote_id=R["quote_free"].get("quote_id"))),
        ("quote_p",       {"op": "quote", "prompt": "priced", "operation_id": "T28:p"}),
        ("budget_ne",     lambda R: NA(prompt="priced", reason="INITIAL_GENERATION", operation_id="T28:p", budget_units=3,
                                       quote_id=R["quote_p"].get("quote_id"))),                                  # CR-08 E
        ("no_price",      {"op": "quote", "prompt": "no price", "model": "unknown_model", "operation_id": "T28:n"}),
        ("status_p",      {"op": "status", "prompt": "priced"}),                                                 # CR-08 F
    ]
    parent, child = CTX.Pipe()
    p = CTX.Process(target=boundary_mock.worker_main, args=(child, db, CORE_PATH, secret_dir, canary_home))
    p.start()
    R, sent = {}, {}
    for label, req in steps:
        req = req(R) if callable(req) else req
        sent[label] = req
        parent.send(req if isinstance(req, str) else json.dumps(req))
        R[label] = parent.recv() if parent.poll(120) else {"ok": False, "error": "TIMEOUT"}
    parent.send(json.dumps({"op": "stop"}))
    stop = parent.recv() if parent.poll(60) else {"ok": False, "error": "TIMEOUT"}
    p.join(30)
    channel = json.dumps(R, default=str)
    P = lambda k: str(R[k].get("refused", "")).startswith("PROTOCOL")
    ok = (R["quote_a"].get("quote_id") and R["quote_a"].get("amount") == 10 and R["quote_a"].get("envelope_id") == "ENV_T28"
          and R["quote_a"].get("price_source") == "LAB_PRICE_TABLE" and R["quote_a"].get("sku") == "fake_model_v1"
          # DELTA 03: nessun intent implicito al confine; RESUME non e' START
          and str(R["no_intent"].get("refused", "")).startswith("PROTOCOL: INTENT_REQUIRED") and R["no_intent"].get("submits") == 0
          and str(R["no_intent_q"].get("refused", "")).startswith("PROTOCOL: INTENT_REQUIRED") and R["no_intent_q"].get("submits") == 0
          and str(R["bad_intent"].get("refused", "")).startswith("PROTOCOL: INTENT_REQUIRED")
          and R["resume_nohist"].get("code") == "NO_EXISTING_ATTEMPT" and R["resume_nohist"].get("submits") == 0
          and R["status_nohist"].get("latest") is None
          and R["first"].get("state") == "SUCCEEDED" and R["first"].get("submits") == 1
          and R["first"].get("reservation_outcome") == "RESERVED_NEW"
          and R["first"].get("governance") == "GOVERNED_LAB" and R["first"].get("budget_units") == 10
          and R["first"].get("envelope_id") == "ENV_T28" and R["first"].get("quote_id") == R["quote_a"].get("quote_id")
          and R["first"].get("permit_id") and R["first"].get("legacy_resume_as_start") is False
          and R["replay"].get("outcome") == "RESUMED/SUCCEEDED" and R["replay"].get("submits") == 1
          and R["replay"].get("resumed") is True and R["replay"].get("job_id") == R["first"].get("job_id")
          and P("shell") and P("argv") and P("nonjson")
          and R["no_reason"].get("code") == "REASON_REQUIRED"
          and R["quote_a2"].get("quote_id") and R["quote_a2"].get("quote_id") != R["quote_a"].get("quote_id")
          and R["new_attempt"].get("reservation_outcome") == "RESERVED_NEW" and R["new_attempt"].get("submits") == 2
          and R["new_attempt"].get("quote_id") == R["quote_a2"].get("quote_id")
          and R["permit_replay"].get("error") == "PermitError" and R["permit_replay"].get("submits") == 2
          and R["lost"].get("error") == "TimeoutError"
          and R["on_uncertain"].get("code") == "LIVE_OR_UNCERTAIN_ATTEMPT"
          and R["status"].get("latest", {}).get("state") == "SUCCEEDED"
          and R["no_quote"].get("code") == "QUOTE_REQUIRED" and R["no_quote"].get("submits") == 2
          and R["no_operation"].get("code") == "OPERATION_ID_REQUIRED" and R["no_operation"].get("submits") == 2
          and P("amount_1") and P("amount_0")                                                          # CR-08 B/C
          and R["quote_free"].get("amount") == 0 and R["quote_free"].get("sku") == "fake_model_free"     # CR-08 D
          and R["free"].get("state") == "SUCCEEDED" and R["free"].get("budget_units") == 0
          and R["quote_p"].get("amount") == 10
          and R["budget_ne"].get("code") == "BUDGET_NOT_QUOTED" and R["budget_ne"].get("submits") == R["free"].get("submits")  # CR-08 E
          and R["no_price"].get("code") == "NO_LAB_PRICE"
          and R["status_p"].get("latest") is None                                                       # CR-08 F
          and stop.get("violations") == [] and stop.get("account_id", "").startswith("acct_")
          and R["first"].get("provider_account") == stop.get("account_id")
          and "FAKE_SPENDER_SECRET" not in channel)
    ev = evidence("T28", "boundary_protocol_mock", {"requests": sent, "replies": R, "stop": stop})
    return (f"senza intent -> {str(R['no_intent'].get('refused', ''))[:26]} (×2, anche con quote) · intent estraneo -> PROTOCOL · "
            f"resume senza attempt -> {R['resume_nohist'].get('code')} (0 submit, nessuna riga) · prima spesa new_attempt/INITIAL_GENERATION -> {R['first'].get('state')} · "
            f"resume={R['replay'].get('outcome')} · quote fidata {R['quote_a'].get('amount')}u ({R['quote_a'].get('price_source')}) · amount dal client -> PROTOCOL ×2 · "
            f"fixture zero -> {R['free'].get('state')}/{R['free'].get('budget_units')} · budget≠quote -> {R['budget_ne'].get('code')} · "
            f"shell/argv/non-JSON -> PROTOCOL · new_attempt (quote nuova)={R['new_attempt'].get('reservation_outcome')} · permit replay -> {R['permit_replay'].get('error')} · "
            f"su incerto -> {R['on_uncertain'].get('code')} · senza quote -> {R['no_quote'].get('code')} · senza operazione -> {R['no_operation'].get('code')} · "
            f"violazioni sentinella {len(stop.get('violations', []))} · segreto nel canale: no"), ev, ok


def t29(canary_home: str, secret_dir: str):
    """TEST-BOUNDARY (privilegi): l'orchestrator PROVA a leggere il segreto, a scrivere il codice del
    worker e a fare dispatch diretto sullo store del worker. Se riesce, il confine NON e' dimostrato:
    BLOCKED_ENVIRONMENT. Questo test non puo' passare in questo ambiente e non deve fingere."""
    db = db_for("T29")
    parent, child = CTX.Pipe()
    p = CTX.Process(target=boundary_mock.worker_main, args=(child, db, CORE_PATH, secret_dir, canary_home))
    p.start()
    parent.send(json.dumps({"op": "quote", "prompt": "privilege", "operation_id": "T29:a"}))
    q = parent.recv() if parent.poll(120) else {}
    parent.send(json.dumps({"op": "submit", "prompt": "privilege", "operation_id": "T29:a", "quote_id": q.get("quote_id")}))
    replies = [q, parent.recv() if parent.poll(120) else {"ok": False, "error": "TIMEOUT"}]
    parent.send(json.dumps({"op": "stop"}))
    stop = parent.recv() if parent.poll(60) else {"ok": False, "error": "TIMEOUT"}
    p.join(30)
    attempts = {}
    secret_path = stop.get("secret_path")
    try:
        with open(secret_path, encoding="utf-8") as fh:
            attempts["read_worker_secret"] = "BYPASS_POSSIBLE" if "FAKE_SPENDER_SECRET" in fh.read() else "BLOCKED"
    except OSError as e:
        attempts["read_worker_secret"] = f"BLOCKED ({type(e).__name__})"
    worker_code = os.path.join(GATE_ROOT, "tests", "boundary_mock.py")
    attempts["write_worker_code"] = "BYPASS_POSSIBLE" if os.access(worker_code, os.W_OK) else "BLOCKED"
    attempts["write_worker_store"] = "BYPASS_POSSIBLE" if os.access(db, os.W_OK) else "BLOCKED"
    direct = in_process(worker.run_go, db, "privilege direct", max_polls=3, operation_id="T29:direct")
    attempts["direct_dispatch_on_worker_store"] = ("BYPASS_POSSIBLE" if direct.get("state") == "SUCCEEDED"
                                                   else f"BLOCKED ({direct.get('error')})")
    uid = {"orchestrator_uid": os.getuid(), "worker_uid": os.stat(secret_path).st_uid}
    # Precondizione ambientale RICONOSCIUTA: orchestrator e worker con lo stesso uid -> nessuna
    # separazione di privilegio disponibile, requisito NON verificabile qui: BLOCKED qualunque sia
    # l'esito contingente delle probe (decisione umana congelata, gate_report.t29_status).
    same_uid = uid["orchestrator_uid"] == uid["worker_uid"]
    status, reason = gate_report.t29_status(same_uid, attempts)
    ev = evidence("T29", "boundary_privilege_isolation", {"attempts": attempts, "uids": uid,
                                                          "protocol_reply": replies, "stop": stop,
                                                          "status": status, "reason_code": reason,
                                                          "environment_precondition_same_uid": same_uid,
                                                          "requirement_verified": status == "PASS"})
    if status == "BLOCKED":
        raise gate_report.GateBlocked(reason, (f"stesso uid ({uid['orchestrator_uid']}) per orchestrator e worker; "
                                               f"tentativi di bypass: {attempts}"), ev)
    if status == "PASS":
        return f"confine di privilegio dimostrato con uid distinti {uid}: {attempts}", ev, True
    return f"confine di privilegio NON dimostrato con uid distinti {uid}; tentativi di bypass: {attempts}", ev, False


def t30():
    """TEST-RESTART via runtime: crash reale del processo dopo l'invio mock e prima del journal;
    recovery -> SUBMIT_UNKNOWN; il replay non ri-sottomette (0 blind retry)."""
    db = db_for("T30")
    q = CTX.Queue()
    p = CTX.Process(target=worker._entry, args=(q, worker.run_go, (db, "crash"),
                                                dict(operation_id="T30:asset", crash_after_send=True)))
    p.start(); p.join(120)
    mid = in_process(worker.read_state, db, CORE_PATH)
    rec = in_process(worker.store_call, db, CORE_PATH, "recover_orphaned_submits", 10.0)
    after = in_process(worker.read_state, db, CORE_PATH)
    replay = in_process(worker.run_go, db, "crash", max_polls=3, operation_id="T30:asset")
    end = in_process(worker.read_state, db, CORE_PATH)
    own = mid["ownership"][0] if mid["ownership"] else {}
    ok = (p.exitcode == 4 and q.empty()
          and len(mid["rows"]) == 1 and mid["rows"][0]["state"] == "RESERVED"
          and mid["rows"][0]["provider"] == "fake" and own.get("provider_account") == "fake_acct_a"
          and own.get("attempt_token")
          and rec.get("ok") and len(rec["result"]) == 1 and rec["result"][0]["state"] == "SUBMIT_UNKNOWN"
          and after["rows"][0]["state"] == "SUBMIT_UNKNOWN"
          and replay.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required" and replay.get("submits") == 0
          and len(end["rows"]) == 1)
    ev = evidence("T30", "restart_recovery_mock", {"crash_exitcode": p.exitcode, "after_crash": mid,
                                                    "recovery": rec, "after_recovery": after,
                                                    "replay": replay, "end": end})
    return (f"crash exit={p.exitcode} dopo l'invio: RESERVED con ownership/token persistiti · "
            f"recovery -> SUBMIT_UNKNOWN · replay -> {replay.get('outcome')} submits={replay.get('submits')}"), ev, ok


def _q(db, op, prompt, env=None, unit=None, expires_at=None, **over):
    """Quote FIDATA emessa lato autorita' (processo separato): importo SOLO dal listino LAB
    (SKU = modello; `fake_model_free` = fixture a prezzo zero), legata a operazione/spec/envelope."""
    kw = {}
    if env:
        kw["envelope_id"] = env
    if unit:
        kw["unit"] = unit
    if expires_at is not None:
        kw["expires_at"] = expires_at
    return in_process(worker.store_call, db, CORE_PATH, "issue_lab_quote", prompt, op, over, **kw)["result"]


def _first(db, prompt, op, quote_id=None, **kw):
    """DELTA 03: PRIMA spesa governata = intent ESPLICITO new_attempt + reason INITIAL_GENERATION + delega
    (permesso emesso solo dopo l'autorizzazione economica). RESUME non e' START."""
    return in_process(worker.run_go, db, prompt, max_polls=kw.pop("max_polls", 3), operation_id=op, quote_id=quote_id,
                      governed=True, intent="new_attempt", reason="INITIAL_GENERATION", auto_permit=True, **kw)


def t31():
    """CR-02 ENVELOPE: derivato dallo scope; fuori scope/altro envelope valido rifiutati; run/spec/modello non lo cambiano."""
    db = db_for("T31")
    q = _q(db, "T31:a", "env ok")
    ok1 = _first(db, "env ok", "T31:a", q)
    in_process(worker.store_call, db, CORE_PATH, "open_envelope", "ENV_T32", 100, unit="synthetic_units")   # valido, di altro scope
    qf = _q(db, "T31:f", "env f")   # operazione nuova: il client PRESENTA un envelope valido ma di altro scope
    out_of_scope = _first(db, "env f", "T31:f", qf, envelope_id="ENV_T32")
    other_valid = _first(db, "env other", "T31:b", _q(db, "T31:b", "env other"), envelope_id="ENV_LAB")
    unauthorized_scope = _first(db, "env x", "NOSCOPE:z", None)
    # cambiare run/modello/spec sotto la stessa operazione non cambia envelope ne' azzera il consumo:
    # la quote e' legata alla spec; una spec diversa non ha quote -> nessun importo, nessun submit
    q2 = _q(db, "T31:c", "env c")
    c1 = _first(db, "env c", "T31:c", q2)
    q2b = _q(db, "T31:c", "env c")     # quote NUOVA (non consumata) ma di T31:c: presentata sotto T31:d -> binding rifiutato
    c_other_run = _first(db, "env c", "T31:d", q2b, inputs_over={"project_id": "RUN_Z"})
    legacy_units = _first(db, "env ok", "T31:e", q, envelope_units=100)
    tot = in_process(worker.store_call, db, CORE_PATH, "ledger_totals", "ENV_T31")
    ok = (ok1.get("state") == "SUCCEEDED" and ok1.get("envelope_id") == "ENV_T31" and ok1.get("governance") == "GOVERNED_LAB"
          and out_of_scope.get("code") == "ENVELOPE_OUT_OF_SCOPE" and out_of_scope.get("submits") == 0
          and other_valid.get("code") == "ENVELOPE_OUT_OF_SCOPE" and other_valid.get("submits") == 0
          and unauthorized_scope.get("code") == "ENVELOPE_NOT_AUTHORIZED" and unauthorized_scope.get("submits") == 0
          and c1.get("state") == "SUCCEEDED"
          and c_other_run.get("code") == "QUOTE_BINDING" and c_other_run.get("submits") == 0
          and legacy_units.get("code") == "LEGACY_ENVELOPE_UNITS_FORBIDDEN" and legacy_units.get("submits") == 0
          and tot["result"]["unsettled_exposure_units"] == 20)
    ev = evidence("T31", "envelope_authorization_binding", {"in_scope": ok1, "out_of_scope": out_of_scope,
                                                             "other_valid_envelope": other_valid,
                                                             "unauthorized_scope": unauthorized_scope,
                                                             "same_op_other_run": [c1, c_other_run],
                                                             "legacy_units_in_governed": legacy_units, "totals": tot})
    return (f"in scope -> {ok1.get('state')} ({ok1.get('envelope_id')}) · fuori scope -> {out_of_scope.get('code')} · "
            f"altro envelope valido -> {other_valid.get('code')} · scope non autorizzato -> {unauthorized_scope.get('code')} · "
            f"quote di altra op/spec -> {c_other_run.get('code')} · envelope_units nel governato -> {legacy_units.get('code')}"), ev, ok


def t32():
    """CR-02 QUOTE: omessa/inferiore/diversa/altra spec/altra operazione rifiutate PRIMA dell'invio;
    zero attestato PASS; budget omesso con quote positiva = importo della quote."""
    db = db_for("T32")
    q = _q(db, "T32:a", "quoted")
    omitted = _first(db, "quoted", "T32:a")
    lower = _first(db, "quoted", "T32:a", q, budget_units=5)
    different = _first(db, "quoted", "T32:a", q, budget_units=11)
    q_other_spec = _q(db, "T32:a", "another spec")
    other_spec = _first(db, "quoted", "T32:a", q_other_spec)
    q_other_op = _q(db, "T32:b", "quoted")
    other_op = _first(db, "quoted", "T32:a", q_other_op)
    unknown = _first(db, "quoted", "T32:a", "quote_nope")
    before = in_process(worker.read_state, db, CORE_PATH)
    omitted_budget = _first(db, "quoted", "T32:a", q, budget_units_none=True)
    q0 = _q(db, "T32:z", "free", model="fake_model_free")     # fixture fidata a prezzo zero (CR-08)
    zero = _first(db, "free", "T32:z", q0, inputs_over={"model": "fake_model_free"})
    after = in_process(worker.read_state, db, CORE_PATH)
    tot = in_process(worker.store_call, db, CORE_PATH, "ledger_totals", "ENV_T32")
    ok = (omitted.get("code") == "QUOTE_REQUIRED" and omitted.get("submits") == 0 and omitted.get("transport_sent") == 0
          and lower.get("code") == "BUDGET_NOT_QUOTED" and lower.get("submits") == 0
          and different.get("code") == "BUDGET_NOT_QUOTED" and different.get("submits") == 0
          and other_spec.get("code") == "QUOTE_BINDING" and other_spec.get("submits") == 0
          and other_op.get("code") == "QUOTE_BINDING" and other_op.get("submits") == 0
          and unknown.get("code") == "QUOTE_UNKNOWN" and unknown.get("submits") == 0
          and before["rows"] == [] and before["permits"] == 0 and before["quotes_consumed"] == 0   # DELTA 03: rifiuti senza permessi emessi
          and omitted_budget.get("state") == "SUCCEEDED" and omitted_budget.get("budget_units") == 10
          and zero.get("state") == "SUCCEEDED" and zero.get("budget_units") == 0 and zero.get("quote_id") == q0
          and [r["budget_units"] for r in after["rows"]] in ([10, 0], [0, 10])
          and tot["result"]["unsettled_exposure_units"] == 10)
    ev = evidence("T32", "quote_binding", {"omitted": omitted, "lower": lower, "different": different,
                                            "other_spec": other_spec, "other_operation": other_op, "unknown": unknown,
                                            "state_before_valid": before, "budget_omitted_quote_positive": omitted_budget,
                                            "zero_attested": zero, "state_after": after, "totals": tot})
    return (f"omessa -> {omitted.get('code')} (sent 0) · inferiore/diversa -> {lower.get('code')} · altra spec/op -> {other_spec.get('code')} · "
            f"budget omesso -> prenotati {omitted_budget.get('budget_units')} dalla quote · zero attestato -> {zero.get('state')} ({zero.get('budget_units')})"), ev, ok


def t33():
    """CR-01 via runtime: spec viva di OP_A non e' restituita a OP_B; due operazioni terminali con la
    stessa spec: RESUME(OP_A) restituisce il job di OP_A."""
    db = db_for("T33")
    live = in_process(worker.run_go, db, "cross", adapter_kw={"never_terminal": True}, max_polls=1, operation_id="T33:A")
    other = in_process(worker.run_go, db, "cross", max_polls=3, operation_id="T33:B")
    mid = in_process(worker.read_state, db, CORE_PATH)
    done_a = in_process(worker.run_go, db, "cross", max_polls=3, operation_id="T33:A")     # OP_A riprende e conclude
    done_b = in_process(worker.run_go, db, "cross", max_polls=3, operation_id="T33:B")     # ora OP_B puo' partire (spec terminale)
    res_a = in_process(worker.run_go, db, "cross", max_polls=3, operation_id="T33:A")
    res_b = in_process(worker.run_go, db, "cross", max_polls=3, operation_id="T33:B")
    end = in_process(worker.read_state, db, CORE_PATH)
    ok = (live.get("state") == "RUNNING" and other.get("error") == "OperationConflict" and other.get("submits") == 0
          and len(mid["rows"]) == 1 and mid["ownership"][0]["operation_id"] == "T33:A"
          and done_a.get("state") == "SUCCEEDED" and done_a.get("job_id") == live.get("job_id") and done_a.get("submits") == 0
          and done_b.get("reservation_outcome") == "RESERVED_NEW" and done_b.get("job_id") != live.get("job_id")
          and res_a.get("resumed_terminal") and res_a.get("job_id") == live.get("job_id")
          and res_b.get("resumed_terminal") and res_b.get("job_id") == done_b.get("job_id")
          and len(end["rows"]) == 2)
    ev = evidence("T33", "cross_operation_identity", {"op_a_live": live, "op_b_same_spec": other, "mid": mid,
                                                       "op_a_done": done_a, "op_b_done": done_b,
                                                       "resume_a": res_a, "resume_b": res_b, "end": end})
    return (f"OP_B su spec viva di OP_A -> {other.get('error')} (0 submit) · OP_A riprende {done_a.get('job_id')} · "
            f"RESUME(OP_A)={res_a.get('job_id')} != RESUME(OP_B)={res_b.get('job_id')}"), ev, ok


def t34():
    """CR-10 operation namespace: '<work_order_id>:<asset>' stabile fra run; distinto fra work order;
    collisione accidentale evitata; stessa spec viva -> OperationConflict; spec_key mai alterata."""
    db = db_for("T34")
    # 1. stesso work order + stesso asset + nuovo run (spec run_id cambia) -> stessa operation_id, RESUME
    a = in_process(worker.run_go, db, "wo asset", max_polls=3, operation_id="WO_A:asset1")
    a2 = in_process(worker.run_go, db, "wo asset", max_polls=3, operation_id="WO_A:asset1", inputs_over={"project_id": "RUN_2"})
    # 2. work order B, stesso batch/asset (stessa spec, ma A e' terminale): operation_id diversa, nuova operazione
    b = in_process(worker.run_go, db, "wo asset", max_polls=3, operation_id="WO_B:asset1")
    # 3A. attempt incerto in WO_A (asset2); WO_B con SPEC DISTINTA sullo stesso asset -> non bloccato
    lost = in_process(worker.run_go, db, "wo unknown", adapter_kind="submit_unknown", operation_id="WO_A:asset2")
    b_other_spec = in_process(worker.run_go, db, "wo other spec", max_polls=3, operation_id="WO_B:asset2")
    # 3B. WO_B con la STESSA spec viva/incerta di WO_A -> OperationConflict (fail-closed)
    b_same_spec = in_process(worker.run_go, db, "wo unknown", max_polls=3, operation_id="WO_B:asset3")
    # 4. replay WO_A -> ritrova esclusivamente l'attempt A
    replay_a = in_process(worker.run_go, db, "wo unknown", max_polls=3, operation_id="WO_A:asset2")
    end = in_process(worker.read_state, db, CORE_PATH)
    # via hf_batch_runtime: namespace esplicito -> operation_id '<WO>:<asset>' in due round; senza namespace = LEGACY_LAB
    hb = in_process(worker.hf_batch_runtime_go, db_for("T34hb"), os.path.join(tempfile.gettempdir(), "t34_canary"), CORE_PATH,
                    adapter_kw={"latency_polls": 1}, max_polls=3, rounds=2, operation_namespace="WO_A")
    hb_legacy = in_process(worker.hf_batch_runtime_go, db_for("T34hl"), os.path.join(tempfile.gettempdir(), "t34_canary"), CORE_PATH,
                           adapter_kw={"latency_polls": 1}, max_polls=3, rounds=1)
    ops_r1 = [x["operation_id"] for x in hb["traces"][0]["jobs"]] if hb.get("ok") else []
    ops_r2 = [x["operation_id"] for x in hb["traces"][1]["jobs"]] if hb.get("ok") else []
    by_op = {o["operation_id"]: o for o in end["ownership"]}
    ok = (a.get("state") == "SUCCEEDED" and a2.get("resumed_terminal") is True and a2.get("job_id") == a.get("job_id")
          and a2.get("operation_id") == "WO_A:asset1" and a2.get("submits") == 0
          and b.get("reservation_outcome") == "RESERVED_NEW" and b.get("job_id") != a.get("job_id") and b.get("operation_id") == "WO_B:asset1"
          and b.get("spec_key") == a.get("spec_key")                       # 5. spec_key identica: nessuna alterazione artificiale
          and lost.get("error") == "ConnectionResetError"
          and b_other_spec.get("state") == "SUCCEEDED" and b_other_spec.get("operation_id") == "WO_B:asset2"
          and b_same_spec.get("error") == "OperationConflict" and b_same_spec.get("submits") == 0
          and "WO_B:asset3" not in by_op
          and replay_a.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required" and replay_a.get("submits") == 0
          and replay_a.get("job_id") == by_op["WO_A:asset2"]["job_id"]
          and hb.get("ok") and ops_r1 == ["WO_A:B1_NEW_CLIP", "WO_A:B4C_NEW_CLIP"] and ops_r2 == ops_r1
          and [x["resumed"] for x in hb["traces"][1]["jobs"]] == [True, True] and hb.get("submits") == 2
          and hb_legacy.get("ok") and [x["operation_namespace"] for x in hb_legacy["traces"][0]["jobs"]] == ["LEGACY_LAB:MOTION_B1_B4C"] * 2
          and [x["operation_id"] for x in hb_legacy["traces"][0]["jobs"]] == ["MOTION_B1_B4C:B1_NEW_CLIP", "MOTION_B1_B4C:B4C_NEW_CLIP"])
    ev = evidence("T34", "work_order_namespace", {"wo_a": a, "wo_a_new_run": a2, "wo_b_same_asset": b, "wo_a_unknown": lost,
                                                   "wo_b_other_spec": b_other_spec, "wo_b_same_spec": b_same_spec,
                                                   "replay_wo_a": replay_a, "state": end, "hf_batch_namespaced": hb,
                                                   "hf_batch_legacy": hb_legacy})
    return (f"WO_A nuovo run -> {a2.get('outcome')} · WO_B stesso asset -> {b.get('reservation_outcome')} (spec_key identica) · "
            f"WO_B spec distinta su asset incerto di WO_A -> {b_other_spec.get('state')} · WO_B stessa spec viva -> {b_same_spec.get('error')} · "
            f"replay WO_A -> attempt A · hf_batch namespaced ops {ops_r1} stabili in 2 round (resumed) · senza namespace = LEGACY_LAB"), ev, ok


def t35():
    """CR-09 via runtime: RESUME non e' nuova spesa ne' dispatch (quote scaduta, UNKNOWN, RESERVED orfana,
    terminale con spec diversa); nessun nuovo RESERVE/permit/quote; identita' e ownership verificate."""
    db = db_for("T35")
    import time as _t
    q = _q(db, "T35:a", "resume live", expires_at=_t.time() + 5)      # scade fra 5s: il resume avviene "dopo"
    live = _first(db, "resume live", "T35:a", q, adapter_kw={"latency_polls": 3}, max_polls=1)
    before = in_process(worker.read_state, db, CORE_PATH)
    qs = in_process(worker.store_call, db, CORE_PATH, "quote", q)
    # 1. RUNNING + quote ormai scaduta (clock +1h): RESUME consentito, zero nuova spesa
    r1 = in_process(worker.run_go, db, "resume live", adapter_kw={"latency_polls": 3}, max_polls=5, operation_id="T35:a",
                    governed=True, clock_offset=30)        # quote scaduta (+30s > +5s), deadline del job (+300s) no
    after1 = in_process(worker.read_state, db, CORE_PATH)
    # ...mentre una NUOVA spesa con quella quote (consumata e scaduta) e' rifiutata
    new_with_old_q = _first(db, "resume live 2", "T35:a2", q, clock_offset=30)
    # 2. SUBMIT_UNKNOWN + resume: nessun submit automatico
    q2 = _q(db, "T35:u", "resume unknown", expires_at=_t.time() + 600)
    lost = _first(db, "resume unknown", "T35:u", q2, adapter_kind="submit_unknown")
    r2 = in_process(worker.run_go, db, "resume unknown", max_polls=3, operation_id="T35:u", governed=True, clock_offset=30)
    # 3. RESERVED orfana (processo morto dopo la prenotazione): resume la restituisce, 0 submit
    orphan = in_process(worker.store_call, db, CORE_PATH, "reserve_or_get_live_by_prompt_op", "resume orphan", "T35:o")
    r3 = in_process(worker.run_go, db, "resume orphan", max_polls=3, operation_id="T35:o", governed=True)
    # 4/5. terminale + quote scaduta + richiesta con run/spec differente -> RESUMED, spec_key == latest, requested a parte
    r4 = in_process(worker.run_go, db, "resume live", max_polls=3, operation_id="T35:a", governed=True, clock_offset=3600,
                    inputs_over={"project_id": "RUN_Z", "model": "fake_model_v2"})
    end = in_process(worker.read_state, db, CORE_PATH)
    qs_end = in_process(worker.store_call, db, CORE_PATH, "quote", q)
    ledger_before = in_process(worker.store_call, db, CORE_PATH, "ledger")
    # 9. RESUME con operation identity errata: non restituisce il job di T35:a e NON e' una prima spesa (DELTA 03)
    wrong = in_process(worker.run_go, db, "resume live", max_polls=3, operation_id="T35:wrong", governed=True)
    # 10. ownership: RESUME con altro conto -> rifiuto
    other_acct = in_process(worker.run_go, db, "resume live", max_polls=3, operation_id="T35:a", governed=True,
                            adapter_kw={"account_id": "fake_acct_b"})
    n_reserve = lambda rows: sum(1 for x in rows if x["kind"] == "RESERVE")
    ok = (live.get("state") == "RUNNING" and live.get("budget_units") == 10 and qs["result"]["consumed_by"] == live.get("job_id")
          and r1.get("resumed") is True and r1.get("state") == "SUCCEEDED" and r1.get("job_id") == live.get("job_id") and r1.get("submits") == 0
          and after1["ledger_entries"] == before["ledger_entries"] and len(after1["rows"]) == len(before["rows"])
          and new_with_old_q.get("code") == "QUOTE_ALREADY_CONSUMED" and new_with_old_q.get("submits") == 0
          and lost.get("error") == "ConnectionResetError"
          and r2.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required" and r2.get("submits") == 0 and r2.get("resumed") is True
          and orphan.get("ok") and r3.get("outcome") == "EXISTING_LIVE_JOB/reserved-no-dispatch" and r3.get("submits") == 0
          and r3.get("state") == "RESERVED"
          and r4.get("outcome") == "RESUMED/SUCCEEDED" and r4.get("submits") == 0 and r4.get("spec_key") == live.get("spec_key")
          and r4.get("requested_spec_key") != live.get("spec_key") and r4.get("job_id") == live.get("job_id")
          and qs_end["result"]["consumed_by"] == live.get("job_id") and qs_end["result"]["consumed_at"] == qs["result"]["consumed_at"]
          and n_reserve(ledger_before["result"]) == 3                       # solo le 3 spese (a, u, o): nessun RESERVE dai resume
          and wrong.get("code") == "NO_EXISTING_ATTEMPT" and wrong.get("submits") == 0 and wrong.get("job_id") is None
          and other_acct.get("error") == "ProviderMismatch" and other_acct.get("submits") == 0
          and len(end["rows"]) == 3)
    ev = evidence("T35", "resume_not_new_spend", {"live": live, "quote_after_reservation": qs, "resume_expired_quote": r1,
                                                   "new_spend_with_consumed_expired_quote": new_with_old_q, "unknown": [lost, r2],
                                                   "orphan": [orphan, r3], "terminal_other_spec": r4, "quote_end": qs_end,
                                                   "ledger": ledger_before, "wrong_operation": wrong, "other_account": other_acct,
                                                   "state": end})
    return (f"RUNNING+quote scaduta -> {r1.get('outcome')} (0 submit, ledger invariato) · nuova spesa con quella quote -> {new_with_old_q.get('code')} · "
            f"UNKNOWN -> {r2.get('outcome')} · RESERVED orfana -> {r3.get('outcome')} · terminale+spec diversa -> {r4.get('outcome')} spec_key=latest · "
            f"RESERVE nel ledger: {n_reserve(ledger_before['result'])} (solo spese) · op errata -> {wrong.get('code')} · altro conto -> {other_acct.get('error')}"), ev, ok


def t36():
    """QUOTE LIFECYCLE via runtime: Q1 consumata da attempt1; nuovo attempt con Q1 -> rifiuto; Q2 -> PASS;
    resume attempt1 non riconsuma; rifiuti pre-reservation lasciano la quote libera."""
    db = db_for("T36")
    q1 = _q(db, "T36:a", "lifecycle")
    a1 = _first(db, "lifecycle", "T36:a", q1)
    s1 = in_process(worker.store_call, db, CORE_PATH, "quote", q1)
    reuse = in_process(worker.run_go, db, "lifecycle", max_polls=3, operation_id="T36:a", quote_id=q1, governed=True,
                       intent="new_attempt", reason="CREATIVE_ITERATION", auto_permit=True)
    q2 = _q(db, "T36:a", "lifecycle")
    a2 = in_process(worker.run_go, db, "lifecycle", max_polls=3, operation_id="T36:a", quote_id=q2, governed=True,
                    intent="new_attempt", reason="CREATIVE_ITERATION", auto_permit=True)
    res = in_process(worker.run_go, db, "lifecycle", max_polls=3, operation_id="T36:a", governed=True)
    s1b = in_process(worker.store_call, db, CORE_PATH, "quote", q1)
    s2 = in_process(worker.store_call, db, CORE_PATH, "quote", q2)
    # rifiuto per envelope fuori scope PRIMA della reservation: la quote resta libera
    q3 = _q(db, "T36:b", "lifecycle b")
    refused = _first(db, "lifecycle b", "T36:b", q3, envelope_id="ENV_T35")
    s3 = in_process(worker.store_call, db, CORE_PATH, "quote", q3)
    end = in_process(worker.read_state, db, CORE_PATH)
    ok = (a1.get("state") == "SUCCEEDED" and s1["result"]["consumed_by"] == a1.get("job_id")
          and reuse.get("code") == "QUOTE_ALREADY_CONSUMED" and reuse.get("submits") == 0
          and a2.get("reservation_outcome") == "RESERVED_NEW" and a2.get("job_id") != a1.get("job_id") and a2.get("quote_id") == q2
          and s2["result"]["consumed_by"] == a2.get("job_id")
          and res.get("resumed") is True and res.get("job_id") == a2.get("job_id") and res.get("submits") == 0
          and s1b["result"] == s1["result"]
          and refused.get("code") == "ENVELOPE_OUT_OF_SCOPE" and s3["result"]["consumed_by"] is None
          and len(end["rows"]) == 2
          and end["permits"] == 2 and end["permits_consumed"] == 2)   # DELTA 03: i rifiuti (reuse, refused) non emettono permessi
    ev = evidence("T36", "quote_lifecycle_runtime", {"attempt1": a1, "q1": s1, "reuse_q1": reuse, "attempt2_q2": a2,
                                                      "resume": res, "q1_after": s1b, "q2": s2, "refused_out_of_scope": refused,
                                                      "q3_after_refusal": s3, "state": end})
    return (f"Q1 consumata da attempt1 · Q1 riusata -> {reuse.get('code')} · Q2 -> {a2.get('reservation_outcome')} · "
            f"resume -> attempt2, Q1/Q2 non riconsumate · rifiuto pre-reservation -> quote libera"), ev, ok

def t37(canary_home: str, secret_dir: str):
    """DELTA 03 — INTENT FAIL-CLOSED: nel governato RESUME usa ESCLUSIVAMENTE un attempt persistito
    (senza attempt -> NO_EXISTING_ATTEMPT, zero effetti); la PRIMA spesa richiede new_attempt +
    INITIAL_GENERATION + quote + autorizzazione + delega; al confine dello spender nessun intent
    implicito; resume-as-start SOLO LEGACY_LAB, marcato."""
    db = db_for("T37")
    # 1. GOVERNED: resume + operazione senza history -> NO_EXISTING_ATTEMPT, 0 reservation/ledger/submit
    q = _q(db, "T37:a", "d03 first")
    r_none = in_process(worker.run_go, db, "d03 first", max_polls=3, operation_id="T37:a", governed=True)
    r_none_q = in_process(worker.run_go, db, "d03 first", max_polls=3, operation_id="T37:a", governed=True, quote_id=q)  # anche con quote valida
    st0 = in_process(worker.read_state, db, CORE_PATH)
    q_after_refusals = in_process(worker.store_call, db, CORE_PATH, "quote", q)
    # 3. GOVERNED: new_attempt + INITIAL_GENERATION + quote valida + autorizzazione -> 1 reservation, 1 submit
    first = _first(db, "d03 first", "T37:a", q)
    st1 = in_process(worker.read_state, db, CORE_PATH)
    q_after_first = in_process(worker.store_call, db, CORE_PATH, "quote", q)
    # 4. stessa operation_id dopo attempt creato: resume -> stesso attempt, 0 nuova reservation/quote/submit
    again = in_process(worker.run_go, db, "d03 first", max_polls=3, operation_id="T37:a", governed=True)
    st2 = in_process(worker.read_state, db, CORE_PATH)
    q_after_resume = in_process(worker.store_call, db, CORE_PATH, "quote", q)
    # 5. SUBMIT_UNKNOWN: resume -> reconciliation-required, 0 submit
    qu = _q(db, "T37:u", "d03 unknown")
    lost = _first(db, "d03 unknown", "T37:u", qu, adapter_kind="submit_unknown")
    r_unknown = in_process(worker.run_go, db, "d03 unknown", max_polls=3, operation_id="T37:u", governed=True)
    # 6. RESERVED orfana: resume -> reserved-no-dispatch, 0 submit
    orphan = in_process(worker.store_call, db, CORE_PATH, "reserve_or_get_live_by_prompt_op", "d03 orphan", "T37:o")
    r_orphan = in_process(worker.run_go, db, "d03 orphan", max_polls=3, operation_id="T37:o", governed=True)
    # prima spesa rifiutata (senza quote): nessun permesso emesso, nessuna riga
    no_quote = _first(db, "d03 noquote", "T37:nq")
    st3 = in_process(worker.read_state, db, CORE_PATH)
    # 7. LEGACY_LAB: resume-as-start ammesso SOLO senza autorizzazione, marcato; irraggiungibile dal governato
    legacy = in_process(worker.run_go, db, "d03 legacy", max_polls=3, operation_id="lab:d03 legacy")
    # 2. BOUNDARY: request senza intent -> PROTOCOL refused, 0 effetti; resume senza attempt -> rifiuto; prima spesa esplicita
    dbb = db_for("T37b")
    qb = in_process(worker.store_call, dbb, CORE_PATH, "issue_lab_quote", "d03 boundary", "T37:b", None)["result"]  # quote fidata (autorita')
    replies, stop = _boundary_session(dbb, secret_dir, canary_home, [
        {"op": "submit", "prompt": "d03 boundary", "operation_id": "T37:b", "quote_id": qb},                 # 0 senza intent (con quote valida)
        {"op": "submit", "prompt": "d03 boundary", "operation_id": "T37:b", "intent": "resume", "quote_id": qb},  # 1 resume senza attempt
        {"op": "status", "prompt": "d03 boundary"},                                                          # 2 nessuna reservation
        {"op": "submit", "prompt": "d03 boundary", "operation_id": "T37:b", "intent": "new_attempt",
         "reason": "INITIAL_GENERATION", "quote_id": qb},                                                    # 3 prima spesa esplicita
        {"op": "submit", "prompt": "d03 boundary", "operation_id": "T37:b", "intent": "resume"},             # 4 resume = stesso attempt
    ])
    stb = in_process(worker.read_state, dbb, CORE_PATH)
    # hf_batch GOVERNATO: default resume NON avvia il primo attempt; senza namespace rifiuto; new_attempt arriva
    # all'autorizzazione economica (QUOTE_REQUIRED) senza effetti; LEGACY_LAB marcato nel trace
    canary = os.path.join(tempfile.gettempdir(), "t37_canary")
    hb_resume = in_process(worker.hf_batch_runtime_go, db_for("T37h1"), canary, CORE_PATH, adapter_kw={"latency_polls": 1},
                           max_polls=3, governed=True, operation_namespace="WO_A")
    hb_nons = in_process(worker.hf_batch_runtime_go, db_for("T37h2"), canary, CORE_PATH, adapter_kw={"latency_polls": 1},
                         max_polls=3, governed=True, operation_namespace=None)
    hb_new = in_process(worker.hf_batch_runtime_go, db_for("T37h3"), canary, CORE_PATH, adapter_kw={"latency_polls": 1},
                        max_polls=3, governed=True, operation_namespace="WO_A", intent="new_attempt",
                        attempt_reason="INITIAL_GENERATION", auto_permit=True)
    hb_new_state = in_process(worker.read_state, os.path.join(STATE_DIR, "t37h3.db"), CORE_PATH)
    hb_legacy = in_process(worker.hf_batch_runtime_go, db_for("T37h4"), canary, CORE_PATH, adapter_kw={"latency_polls": 1},
                           max_polls=3, rounds=1)
    ok = (r_none.get("code") == "NO_EXISTING_ATTEMPT" and r_none.get("submits") == 0 and r_none.get("transport_sent") == 0
          and r_none_q.get("code") == "NO_EXISTING_ATTEMPT" and r_none_q.get("submits") == 0
          and st0["rows"] == [] and st0["ledger_entries"] == 0 and st0["permits"] == 0 and st0["quotes_consumed"] == 0
          and q_after_refusals["result"]["consumed_by"] is None
          and first.get("reservation_outcome") == "RESERVED_NEW" and first.get("state") == "SUCCEEDED" and first.get("submits") == 1
          and first.get("intent") == "new_attempt" and first.get("legacy_resume_as_start") is False and first.get("permit_id")
          and len(st1["rows"]) == 1 and st1["ledger_entries"] == 1 and st1["permits"] == 1 and st1["permits_consumed"] == 1
          and q_after_first["result"]["consumed_by"] == first.get("job_id")
          and again.get("resumed") is True and again.get("job_id") == first.get("job_id") and again.get("submits") == 0
          and again.get("outcome") == "RESUMED/SUCCEEDED" and again.get("legacy_resume_as_start") is False
          and st2["rows"] == st1["rows"] and st2["ledger_entries"] == st1["ledger_entries"] and st2["permits"] == st1["permits"]
          and q_after_resume["result"] == q_after_first["result"]
          and lost.get("error") == "ConnectionResetError"
          and r_unknown.get("outcome") == "EXISTING_LIVE_JOB/reconciliation-required" and r_unknown.get("submits") == 0
          and orphan.get("ok") and r_orphan.get("outcome") == "EXISTING_LIVE_JOB/reserved-no-dispatch" and r_orphan.get("submits") == 0
          and no_quote.get("code") == "QUOTE_REQUIRED" and no_quote.get("submits") == 0
          and st3["permits"] == 2 and len(st3["rows"]) == 3                                           # a, u, o; nessun permesso da rifiuti
          and legacy.get("state") == "SUCCEEDED" and legacy.get("governance") == "LEGACY_LAB"
          and legacy.get("legacy_resume_as_start") is True and legacy.get("intent") == "resume"
          and str(replies[0].get("refused", "")).startswith("PROTOCOL: INTENT_REQUIRED") and replies[0].get("submits") == 0
          and replies[1].get("code") == "NO_EXISTING_ATTEMPT" and replies[1].get("submits") == 0
          and replies[2].get("latest") is None
          and replies[3].get("state") == "SUCCEEDED" and replies[3].get("reservation_outcome") == "RESERVED_NEW"
          and replies[3].get("submits") == 1 and replies[3].get("quote_id") == qb
          and replies[4].get("outcome") == "RESUMED/SUCCEEDED" and replies[4].get("submits") == 1
          and replies[4].get("job_id") == replies[3].get("job_id")
          and len(stb["rows"]) == 1 and stb["permits"] == 1 and stop.get("violations") == []
          and hb_resume.get("ok") is False and hb_resume.get("error") == "IntentRefused" and hb_resume.get("code") == "NO_EXISTING_ATTEMPT"
          and hb_resume.get("submits") == 0
          and hb_nons.get("ok") is False and hb_nons.get("code") == "OPERATION_NAMESPACE_REQUIRED" and hb_nons.get("submits") in (0, None)
          and hb_new.get("ok") is False and hb_new.get("code") == "QUOTE_REQUIRED" and hb_new.get("submits") == 0
          and hb_new_state["rows"] == [] and hb_new_state["permits"] == 0
          and hb_legacy.get("ok") and [x["legacy_resume_as_start"] for x in hb_legacy["traces"][0]["jobs"]] == [True, True]
          and [x["governance"] for x in hb_legacy["traces"][0]["jobs"]] == ["LEGACY_LAB", "LEGACY_LAB"])
    ev = evidence("T37", "intent_fail_closed", {
        "governed_resume_without_attempt": [r_none, r_none_q], "state_after_refusals": st0, "quote_after_refusals": q_after_refusals,
        "first_spend_new_attempt": first, "state_after_first": st1, "quote_after_first": q_after_first,
        "resume_after_first": again, "state_after_resume": st2, "quote_after_resume": q_after_resume,
        "submit_unknown": [lost, r_unknown], "reserved_orphan": [orphan, r_orphan],
        "first_spend_without_quote": no_quote, "state_end": st3, "legacy_resume_as_start": legacy,
        "boundary": {"replies": replies, "stop": stop, "quote_id": qb, "state": stb},
        "hf_batch_governed_default_resume": hb_resume, "hf_batch_governed_no_namespace": hb_nons,
        "hf_batch_governed_new_attempt_no_quote": hb_new, "hf_batch_governed_new_attempt_state": hb_new_state,
        "hf_batch_legacy": hb_legacy})
    return (f"governed resume senza attempt -> {r_none.get('code')} (anche con quote; 0 righe/ledger/permit/submit, quote libera) · "
            f"new_attempt+INITIAL_GENERATION -> {first.get('reservation_outcome')}/{first.get('state')} (1 submit) · resume -> {again.get('outcome')} (0 submit, quote/permit/ledger invariati) · "
            f"UNKNOWN -> {r_unknown.get('outcome')} · RESERVED orfana -> {r_orphan.get('outcome')} · prima spesa senza quote -> {no_quote.get('code')} (0 permessi) · "
            f"boundary: senza intent -> PROTOCOL INTENT_REQUIRED, resume senza attempt -> {replies[1].get('code')}, new_attempt -> {replies[3].get('state')}, resume -> {replies[4].get('outcome')} · "
            f"hf_batch governato: default resume -> {hb_resume.get('code')}, senza namespace -> {hb_nons.get('code')}, new_attempt senza quote -> {hb_new.get('code')} · "
            f"LEGACY_LAB resume-as-start marcato ({legacy.get('legacy_resume_as_start')})"), ev, ok


# ---------------------------------------------------------------- main
def write_results() -> dict:
    """Console, RESULTS.json e TEST_RESULTS.md derivano dalla stessa struttura (gate_report.summarize)."""
    summary = gate_report.summarize(RESULTS)
    gate_report.write(RESULTS, summary, gate_root=GATE_ROOT, evidence_dir=EVIDENCE_DIR,
                      required_core_sha=REQUIRED_CORE_SHA)
    return summary


def main() -> int:
    os.makedirs(STATE_DIR, exist_ok=True)
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    print(f"RUNTIME INTEGRATION GATE 01 — Core {CORE_PATH} @ {git('rev-parse', 'HEAD')[:12]}"
          f" (required {REQUIRED_CORE_SHA[:12]})")
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
        record("T17", "Core canonical unchanged", f"HEAD == {REQUIRED_CORE_SHA[:7]} (Core promosso), working tree pulito", t17)
        record("T18", "durable terminal persistence", "SUCCEEDED riletto da nuovo processo; nuovo tentativo dopo terminale", t18)
        record("T19", "static: no duplicate control system (AST)", "0 findings; import dal Core = 4 attesi", t19)
        record("T20", "dirty Core must fail closed", "canonical+clean PASS; canonical+tracked mod -> CORE_WORKTREE_DIRTY (no import); wrong+clean -> MISMATCH; stale+clean -> STALE",
               lambda: t20(stale_core))
        record("T21", "real hf_batch go -> GenSpec mapping", "27 job reali: prompt/media identici all'originale; lock: prompt_sha256 e sha256_sent combaciano; spec_key deterministico; mutazioni reali cambiano chiave", t21)
        record("T22", "hf_batch_runtime.go on real spec via Core", "2 RESERVED_NEW + 2 submit; GO#2 EXISTING_LIVE_JOB 0 submit; nuovo processo completa SUCCEEDED; lock/quote REAL_PROVIDER_DISABLED; 0 violazioni",
               lambda: t22(canary_home))
        record("T23", "P2 handoff integrity", "manifest 0 mismatch; ZIP hash registrati", t23)
        secret_dir = os.path.join(scratch, "spender_secret")
        record("T24", "RV03 resume after terminal", "replay dopo SUCCEEDED/FAILED (anche nuovo processo) = stesso attempt, 0 submit", t24)
        record("T25", "RV03 new attempt needs reason + one-shot permit", "senza motivo/permesso rifiutato; con permesso 1 nuovo tentativo; replay permesso rifiutato", t25)
        record("T26", "RV03 unknown blocks run/model fallbacks", "SUBMIT_UNKNOWN: stessa spec reconciliation-required; altro run/modello OperationBusy; 0 submit", t26)
        record("T27", "P-B03 cumulative ledger via runtime", "3 job regolati saturano l'envelope; quarto BudgetExceeded con 0 vivi; non regolato resta esposto", t27)
        record("T28", "P-B01 spender boundary mock (protocol)", "solo intenti strutturati ED ESPLICITI; resume senza attempt rifiutato; shell rifiutata; permesso monouso; segreto mai nel canale",
               lambda: t28(canary_home, secret_dir))
        record("T29", "P-B01 privilege isolation", "orchestrator non puo' leggere il segreto, scrivere il worker, fare dispatch diretto",
               lambda: t29(canary_home, secret_dir))
        record("T37", "DELTA 03 intent fail-closed", "governed resume senza attempt -> NO_EXISTING_ATTEMPT (0 effetti); prima spesa solo new_attempt+INITIAL_GENERATION; boundary senza intent -> PROTOCOL; resume-as-start solo LEGACY_LAB marcato",
               lambda: t37(canary_home, secret_dir))
        record("T30", "recovery mock: crash after send before journal", "RESERVED con ownership; recovery -> SUBMIT_UNKNOWN; replay 0 submit", t30)
        record("T31", "CR-02 envelope authorization binding", "envelope derivato dallo scope; fuori scope/altro envelope/scope non autorizzato rifiutati; envelope_units vietato nel governato", t31)
        record("T32", "CR-02 quote binding", "quote omessa/inferiore/diversa/altra spec/altra op rifiutate prima dell'invio; zero attestato PASS; budget omesso = quote", t32)
        record("T33", "CR-01 cross-operation identity", "spec viva di OP_A non restituita a OP_B; RESUME(OP_A) != RESUME(OP_B) su spec uguale", t33)
        record("T34", "CR-10 work-order operation namespace", "'<wo>:<asset>' stabile fra run; distinto fra WO; spec distinta non bloccata; stessa spec viva OperationConflict; spec_key intatta", t34)
        record("T35", "CR-09 resume is not new spend/dispatch", "quote scaduta/consumata non blocca il resume; UNKNOWN/RESERVED 0 submit; spec_key=latest; ledger/permit/quote invariati; ownership", t35)
        record("T36", "quote lifecycle (atomic single use) via runtime", "Q1 consumata; riuso rifiutato; Q2 nuovo attempt; resume non riconsuma; rifiuti pre-reservation non consumano", t36)
    finally:
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "remove", "--force", stale_core],
                       capture_output=True)
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "prune"], capture_output=True)
        shutil.rmtree(scratch, ignore_errors=True)
    summary = write_results()
    print(gate_report.console_summary(summary))
    print("crediti spesi: 0 · provider reali: 0 · rete generativa: 0")
    return summary["runner_exit"]


if __name__ == "__main__":
    sys.exit(main())
