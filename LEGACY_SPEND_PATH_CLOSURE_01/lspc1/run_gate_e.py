#!/usr/bin/env python3
"""LEGACY SPEND PATH CLOSURE + LEGACY TEST MIGRATION — gate E00..E12.

MOCK ONLY · ZERO PROVIDER REALI · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUZIONE.

Ogni passo scrive la propria evidenza in `evidence/Exx_*.json` e una riga in
`TEST_RESULTS.md` con EXPECTED / ACTUAL / EVIDENCE / PASS-FAIL.

La distinzione fra le due domande e' mantenuta rigorosamente, e non e' una
formalita':

    A. TEST SUITE RESULT      i test hanno prodotto l'esito atteso?
    B. REQUIREMENT READINESS  il requisito e' davvero chiuso?

Un PASS qui puo' dimostrare che un requisito resta POLICY_DECISION_REQUIRED o
REAL_PROVIDER_REQUIRED. `READINESS.json` tiene le due cose separate.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BUNDLE)
GATE01 = os.path.join(REPO, "RUNTIME_INTEGRATION_GATE_01")
for _p in (BUNDLE, GATE01):
    if _p not in sys.path:
        sys.path.insert(0, _p)

EVIDENCE_DIR = os.path.join(BUNDLE, "evidence")
REGRESSION_DIR = os.path.join(BUNDLE, "regression")
CORE_PATH = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")

BASELINE_CORE_SHA = "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515"
# Primo candidate di questa fase, quello su cui la Human Review ha trovato il blocker
# DISPATCH_AUTHORIZATION_FORGEABLE. E13 ci riproduce il difetto: riprodurlo sul Core
# gia' corretto non riprodurrebbe nulla.
REVIEWED_CORE_SHA = "44f9ea29cea112dfb30c752e5519498e25044c19"
BASELINE_RUNTIME_SHA = "fea7b439a63a0100a732e21af4dfde6b8edd0951"
P2_SHA = "637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1"
P2_PATH = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16",
                       "P2_RUNTIME", "hf_batch.py")

GREEN, RED, YEL, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
RESULTS: list[dict] = []
P2_BEFORE = {}


# --------------------------------------------------------------- utilita'
def sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args, cwd: str) -> str:
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True).stdout.strip()


def evidence(step: str, name: str, payload) -> str:
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    path = os.path.join(EVIDENCE_DIR, f"{step}_{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    return os.path.relpath(path, BUNDLE)


def record(step: str, title: str, expected: str, fn):
    t0 = time.time()
    try:
        actual, ev, ok = fn()
        err = None
    except Exception as e:                                  # noqa: BLE001
        actual, ev, ok = f"{type(e).__name__}: {e}", "", False
        err = traceback.format_exc(limit=6)
    RESULTS.append({"id": step, "title": title, "expected": expected, "actual": actual,
                    "evidence": ev, "pass": bool(ok), "seconds": round(time.time() - t0, 1),
                    "error": err})
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  {step} {mark}  {title}\n       {DIM}{actual}{RESET}", flush=True)
    if err:
        print(f"{DIM}{err}{RESET}", flush=True)


# =========================================================== E00 reality lock
def e00():
    core_head = git("rev-parse", "HEAD", cwd=CORE_PATH)
    core_branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=CORE_PATH)
    core_dirty = git("status", "--porcelain", "--untracked-files=all", cwd=CORE_PATH)
    rt_head = git("rev-parse", "HEAD", cwd=REPO)
    rt_branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=REPO)
    rt_dirty = git("status", "--porcelain", "--untracked-files=all", cwd=REPO)
    core_base_ok = subprocess.run(
        ["git", "-C", CORE_PATH, "merge-base", "--is-ancestor", BASELINE_CORE_SHA, core_head]
    ).returncode == 0
    rt_base_ok = subprocess.run(
        ["git", "-C", REPO, "merge-base", "--is-ancestor", BASELINE_RUNTIME_SHA, rt_head]
    ).returncode == 0
    from runtime.core_pin import REQUIRED_CORE_SHA
    p2 = sha256_file(P2_PATH)
    P2_BEFORE.update(sha256=p2, path=P2_PATH, size=os.path.getsize(P2_PATH))
    checks = {
        "core_remote_main_is_canonical_baseline":
            git("ls-remote", "origin", "refs/heads/main", cwd=CORE_PATH).split()[0] == BASELINE_CORE_SHA,
        "runtime_remote_main_is_canonical_baseline":
            git("ls-remote", "origin", "refs/heads/main", cwd=REPO).split()[0] == BASELINE_RUNTIME_SHA,
        "core_candidate_descends_from_baseline": core_base_ok,
        "runtime_candidate_descends_from_baseline": rt_base_ok,
        "core_worktree_clean": core_dirty == "",
        # L'unico percorso che puo' essere sporco e' il bundle che questo gate sta
        # producendo: il delta di codice e' gia' committato, l'evidenza no (non puo'
        # esserlo: la si sta scrivendo adesso).
        "runtime_worktree_clean_outside_this_bundle": all(
            "LEGACY_SPEND_PATH_CLOSURE_01" in ln
            for ln in rt_dirty.splitlines() if ln.strip()),
        "runtime_pin_points_at_core_head": REQUIRED_CORE_SHA == core_head,
        "p2_frozen_unchanged": p2 == P2_SHA,
        "no_tags_core": git("tag", cwd=CORE_PATH) == "",
        "no_tags_runtime": git("tag", cwd=REPO) == "",
    }
    payload = {
        "declared_canonical_baseline": {"core_main": BASELINE_CORE_SHA,
                                        "runtime_main": BASELINE_RUNTIME_SHA,
                                        "p2_frozen": P2_SHA},
        "observed": {"core": {"head": core_head, "branch": core_branch,
                              "remote_main": git("ls-remote", "origin", "refs/heads/main",
                                                 cwd=CORE_PATH).split()[0],
                              "dirty": core_dirty.splitlines()},
                     "runtime": {"head": rt_head, "branch": rt_branch,
                                 "remote_main": git("ls-remote", "origin", "refs/heads/main",
                                                    cwd=REPO).split()[0],
                                 "dirty_paths": [ln[3:] for ln in rt_dirty.splitlines()]},
                     "runtime_pin": REQUIRED_CORE_SHA, "p2_sha256": p2},
        "checks": checks,
        "note": ("La baseline canonica dichiarata dal handoff e' cio' che i due `main` REMOTI "
                 "portano; il lavoro di questa fase vive su branch dedicati che ne DISCENDONO. "
                 "Nessuna scrittura su main."),
    }
    ev = evidence("E00", "reality_lock", payload)
    failed = [k for k, v in checks.items() if not v]
    return (f"Core {core_head[:12]} ({core_branch}) · Runtime {rt_head[:12]} ({rt_branch}) · "
            f"pin={REQUIRED_CORE_SHA[:12]} · P2={p2[:16]}… · controlli falliti: "
            f"{failed or 'nessuno'}"), ev, not failed


# =========================================================== E01 inventario
def e01():
    from lspc1 import inventory
    static = inventory.run(CORE_PATH, GATE01, BUNDLE)
    ev = evidence("E01", "spend_path_inventory_static", static)
    ok = (static["core"]["files_with_spend_surface"] > 0
          and static["runtime"]["files_with_spend_surface"] > 0
          and "grant_dispatch" in static["core"]["call_totals"]
          and "authorize_dispatch" in static["core"]["call_totals"])
    return (f"CORE: {static['core']['files_with_spend_surface']} file con superficie di spesa, "
            f"{sum(static['core']['call_totals'].values())} chiamate · RUNTIME: "
            f"{static['runtime']['files_with_spend_surface']} file, "
            f"{sum(static['runtime']['call_totals'].values())} chiamate · confine presente nel Core: "
            f"grant_dispatch/authorize_dispatch"), ev, ok


# =========================================================== E02 pre-fix
def e02(scratch: str):
    """RIPRODUZIONE PRE-FIX sulla COPPIA CANONICA (Core 9cf9cee1 + Runtime fea7b439).

    Riprodurre il difetto sul codice gia' corretto non riprodurrebbe nulla: qui si
    montano due worktree ai due SHA canonici e vi si eseguono LE STESSE sonde."""
    from lspc1 import runner
    core_wt = os.path.join(scratch, "core_baseline")
    rt_wt = os.path.join(scratch, "runtime_baseline")
    subprocess.run(["git", "-C", CORE_PATH, "worktree", "add", "--detach", core_wt,
                    BASELINE_CORE_SHA], check=True, capture_output=True)
    subprocess.run(["git", "-C", REPO, "worktree", "add", "--detach", rt_wt,
                    BASELINE_RUNTIME_SHA], check=True, capture_output=True)
    try:
        pre = runner.probe_all(core_wt, gate01=os.path.join(rt_wt, "RUNTIME_INTEGRATION_GATE_01"))
    finally:
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "remove", "--force", core_wt],
                       capture_output=True)
        subprocess.run(["git", "-C", REPO, "worktree", "remove", "--force", rt_wt],
                       capture_output=True)
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "prune"], capture_output=True)
        subprocess.run(["git", "-C", REPO, "worktree", "prune"], capture_output=True)
    reached = {k: (v.get("sentinel") or {}).get("reached") for k, v in pre.items()}
    # Il difetto DEVE riprodursi: se nessun percorso legacy raggiungesse lo spender,
    # non ci sarebbe nulla da chiudere e questa fase sarebbe senza oggetto.
    reproduced = {
        "legacy_lab_go_reaches_spender": reached.get("P1") == 1,
        "core_run_job_direct_reaches_spender": reached.get("P4") == 1,
        "core_run_job_with_client_budget_reaches_spender": reached.get("P4env") == 1,
        "adapter_submit_direct_reaches_spender": reached.get("P5") == 1,
        "adapter_authorize_payload_direct_crosses":
            (pre.get("P6", {}).get("sentinel") or {}).get("authorized_calls") == 1,
        "reconcile_then_respend_reaches_spender":
            pre.get("P7", {}).get("respend", {}).get("ok") is True,
        "hf_batch_legacy_reaches_spender": (reached.get("P10") or 0) >= 1,
        "store_call_dispatches_any_method":
            pre.get("P8", {}).get("surface_declared") is False,
    }
    ev = evidence("E02", "pre_fix_reproduction", {
        "core_baseline": BASELINE_CORE_SHA, "runtime_baseline": BASELINE_RUNTIME_SHA,
        "reproduced": reproduced, "probes": pre,
        "note": ("`reached` = attraversamenti del confine dello spender osservati dalla "
                 "SENTINELLA. Su questa coppia canonica il percorso legacy spende davvero.")})
    ok = all(reproduced.values())
    missing = [k for k, v in reproduced.items() if not v]
    return (f"sulla coppia canonica: lo spender e' raggiunto da LEGACY_LAB go, run_job diretto, "
            f"submit diretto, authorize_payload diretto, reconcile+respend e hf_batch · "
            f"non riprodotto: {missing or 'nessuno'}"), ev, ok


# =========================================================== E03 Core primitives
def e03():
    log = os.path.join(REGRESSION_DIR, "core_spender_boundary.log")
    os.makedirs(REGRESSION_DIR, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(CORE_PATH, "tests", "run_spender_boundary.py")],
                       capture_output=True, text=True, cwd=CORE_PATH, timeout=1800,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(r.stdout + "\n--- stderr ---\n" + r.stderr)
    import re
    plain = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
    passes = len(re.findall(r"^PASS {2}", plain, re.M))
    total = passes + len(re.findall(r"^FAIL {2}", plain, re.M))
    diff = subprocess.run(["git", "-C", CORE_PATH, "diff", "--stat", BASELINE_CORE_SHA, "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    ev = evidence("E03", "core_primitives_classification", {
        "core_delta_stat": diff.splitlines(),
        "unit_suite": {"returncode": r.returncode, "pass": passes, "total": total,
                       "log": os.path.relpath(log, BUNDLE), "tail": r.stdout[-2500:]},
        "classification": {
            "transport.pipeline.run_job": "E — primitive che poteva diventare un bypass provider; "
                                          "ristretta SOLO per adapter spendibili, firma invariata",
            "adapters.*.submit / authorize_payload": "E — confine dello spender: template method "
                                                     "non sovrascrivibile in SpendCapableAdapter",
            "registry.reservations.reconcile": "A/D — primitive interna valida (non dispaccia); "
                                               "allowlist OPZIONALE delle provenienze, default inerte",
            "tests.worker.store_call": "C — helper di test che invocava lo store direttamente; "
                                       "superficie ora DICHIARATA (lettura/autorita'/sonda)",
            "go(authorization=None) LEGACY_LAB": "B — percorso di compatibilita' del Runtime; "
                                                 "reso LAB_ONLY_NON_PROVIDER_CAPABLE",
        }})
    return (f"Core delta additivo ({len(diff.splitlines())} file) · suite unitaria del confine: "
            f"{passes}/{total} PASS, exit {r.returncode}"), ev, (r.returncode == 0 and total >= 11
                                                                 and passes == total)


# =========================================================== E04 controprove
def e04():
    from lspc1 import runner
    post = runner.probe_all(CORE_PATH)
    reached = {k: (v.get("sentinel") or {}).get("reached") for k, v in post.items()}
    zero = {k: v.get("sentinel_zero") for k, v in post.items()}
    checks = {
        "legacy_lab_go_refused_before_any_effect":
            post["P1"].get("code") == "LEGACY_LAB_NOT_PROVIDER_CAPABLE"
            and post["P1"]["store"].get("created") is False and zero["P1"],
        "refusal_precedes_core_pin_gate":
            post["P1pin"].get("code") == "LEGACY_LAB_NOT_PROVIDER_CAPABLE" and zero["P1pin"],
        "lab_adapter_still_works": post["P2"].get("ok") is True,
        "governed_path_reaches_spender": reached.get("P3") == 1 and post["P3"].get("state") == "SUCCEEDED",
        "core_run_job_direct_refused":
            post["P4"].get("code") == "SPEND_AUTHORIZATION_REQUIRED"
            and post["P4"]["store"].get("reservations") == 0 and zero["P4"],
        "client_budget_refused_for_spender":
            post["P4env"].get("code") == "SPEND_AUTHORIZATION_REQUIRED"
            and post["P4env"]["store"].get("reservations") == 0 and zero["P4env"],
        "adapter_submit_direct_refused":
            post["P5"].get("code") == "SPEND_AUTHORIZATION_REQUIRED" and zero["P5"],
        "adapter_authorize_payload_direct_refused":
            post["P6"].get("code") == "SPEND_AUTHORIZATION_REQUIRED" and zero["P6"],
        "reconcile_cannot_lead_to_spend":
            post["P7"]["respend"].get("code") == "SPEND_AUTHORIZATION_REQUIRED" and zero["P7"],
        "reconcile_allowlist_refuses_forged_evidence":
            post["P7al"]["reconcile"].get("accepted") is False
            and post["P7al"]["reconcile"].get("state") == "RESERVED",
        "store_call_surface_declared":
            post["P8"].get("code") == "STORE_CALL_METHOD_NOT_ALLOWED"
            and post["P8"].get("surface_declared") is True,
        "hf_batch_legacy_refused":
            post["P10"].get("code") == "LEGACY_LAB_NOT_PROVIDER_CAPABLE" and zero["P10"],
    }
    sentinel_zero_on_every_legacy_path = all(
        zero[k] for k in ("P1", "P1pin", "P4", "P4env", "P5", "P6", "P7", "P7al", "P10"))
    checks["sentinel_zero_on_every_legacy_path"] = sentinel_zero_on_every_legacy_path
    ev = evidence("E04", "provider_boundary_counterproofs", {
        "checks": checks, "sentinel_reached": reached, "probes": post,
        "note": ("La sentinella sostituisce il provider reale: `reached` conta gli "
                 "attraversamenti del confine. Zero in ogni percorso legacy, 1 nel governato: "
                 "se fosse zero anche li', la controprova non proverebbe nulla.")})
    failed = [k for k, v in checks.items() if not v]
    return (f"sentinella a 0 in tutti i percorsi legacy, 1 nel governato · controlli falliti: "
            f"{failed or 'nessuno'}"), ev, not failed


# =========================================================== E05 LAB_ONLY
def e05():
    from lspc1 import runner
    sw = runner.config_switches(CORE_PATH)
    at = sw.get("attempts", {})
    inner = at.get("_masked_inner", {})
    checks = {
        "mode_engaged_refuses": at["modalita_ingaggiata"]["refused"]
        and at["modalita_ingaggiata"].get("code") == "LEGACY_LAB_NOT_PROVIDER_CAPABLE",
        "mode_disengaged_refuses_too": at["modalita_disingaggiata"]["refused"]
        and at["modalita_disingaggiata"].get("code") == "LEGACY_LAB_NOT_PROVIDER_CAPABLE",
        "env_cannot_reopen": at["ambiente_forza_abilitato"]["refused"]
        and at["ambiente_forza_abilitato"].get("code") == "LEGACY_LAB_NOT_PROVIDER_CAPABLE",
        "subclass_cannot_retake_submit": at["sottoclasse_riprende_submit"]["refused"]
        and at["sottoclasse_riprende_submit"].get("error") == "TypeError",
        "masking_the_capability_does_not_help":
            at["wrapper_che_nasconde_la_capability"]["refused"]
            and at["wrapper_che_nasconde_la_capability"].get("code") == "SPEND_AUTHORIZATION_REQUIRED",
        "masked_inner_sentinel_zero": inner.get("reached") == 0 and inner.get("transport_sent") == 0,
    }
    from runtime.provider_gate import (LEGACY_LAB_PROVIDER_CAPABILITY, LEGACY_LAB_SPEND_PATH,
                                       legacy_spend_path_state)
    declared = {"LEGACY_LAB_SPEND_PATH": LEGACY_LAB_SPEND_PATH,
                "legacy_spend_path_state()": legacy_spend_path_state(),
                "LEGACY_LAB_PROVIDER_CAPABILITY": LEGACY_LAB_PROVIDER_CAPABILITY}
    checks["capability_declared"] = LEGACY_LAB_PROVIDER_CAPABILITY == "LAB_ONLY_NON_PROVIDER_CAPABLE"
    checks["historic_switch_value_unchanged"] = LEGACY_LAB_SPEND_PATH == "ENABLED_LAB_ONLY"
    ev = evidence("E05", "legacy_lab_only_non_provider_capable", {
        "checks": checks, "declared": declared, "attempts": at,
        "note": ("Il VALORE storico dell'interruttore non e' stato rinominato: i gate approvati "
                 "lo asseriscono letteralmente e rinominarlo avrebbe indebolito un controllo "
                 "storico senza aggiungere garanzie. Cio' che cambia e' la CAPABILITY, e a "
                 "imporla e' il codice, non l'etichetta.")})
    failed = [k for k, v in checks.items() if not v]
    return (f"modalita' ingaggiata/disingaggiata, ambiente, sottoclasse e wrapper che nasconde "
            f"la capability: tutti rifiutati, sentinella 0 · falliti: {failed or 'nessuno'}"), ev, not failed


# =========================================================== E06 budget legacy
def e06():
    from lspc1 import runner
    r = runner.budget_paths(CORE_PATH)
    checks = {
        "envelope_units_refused_for_spender_at_core":
            r["core_envelope_units"].get("code") == "SPEND_AUTHORIZATION_REQUIRED"
            and r["core_envelope_units"]["store"].get("reservations") == 0,
        "envelope_units_refused_in_governed_runtime":
            r["runtime_envelope_units"].get("code") == "LEGACY_ENVELOPE_UNITS_FORBIDDEN",
        "client_amount_must_match_trusted_quote":
            r["client_amount_mismatch"].get("code") == "BUDGET_NOT_QUOTED"
            and r["client_amount_mismatch"].get("submits") == 0,
        "client_omitting_amount_gets_quote_amount":
            r["client_omits_amount"].get("budget_units") == 10,
        "budget_units_still_available_to_lab_adapter":
            r["lab_budget_units"].get("ok") is True,
        "envelope_units_unreachable_from_spender_path": (
            (r["core_envelope_units"].get("sentinel") or {}).get("reached") == 0),
    }
    ev = evidence("E06", "legacy_envelope_budget_paths", {
        "checks": checks, "probes": r,
        "note": ("`budget_units`/`envelope_units` restano per il LABORATORIO. Nel percorso "
                 "spendibile il client non sceglie il prezzo: l'importo viene dalla quote "
                 "fidata, e `envelope_units` e' rifiutato sia dal Runtime (governato) sia dal "
                 "Core (adapter spendibile).")})
    failed = [k for k, v in checks.items() if not v]
    return (f"client budget grezzo non raggiunge il confine dello spender; importo solo dalla "
            f"quote fidata · falliti: {failed or 'nessuno'}"), ev, not failed


# =========================================================== E07 migrazione
def e07():
    from lspc1 import migrated
    out = {}
    for mid, orig, title, fn in migrated.MIGRATED:
        try:
            actual, ok, detail = fn()
        except Exception as e:                              # noqa: BLE001
            actual, ok, detail = f"{type(e).__name__}: {e}", False, {
                "trace": traceback.format_exc(limit=5)}
        out[mid] = {"migrated_from": orig, "title": title, "pass": ok, "actual": actual,
                    "detail": detail}
        print(f"       {DIM}· {mid} <- {orig} {'PASS' if ok else 'FAIL'}: {actual[:150]}{RESET}",
              flush=True)
    ev = evidence("E07", "legacy_test_migration", {
        "cases": out,
        "mode_by_case": {mid: ("CORE_UNIT" if mid == "M13" else "GOVERNED_PATH") for mid in out},
        "note": ("`tests/run_gate.py` NON e' stato toccato: resta la base di non-regressione. "
                 "Questa suite dimostra che cio' che i test storici verificavano e' verificabile "
                 "dal percorso governato o dal Core, quindi non richiede un bypass spendibile.")})
    failed = [k for k, v in out.items() if not v["pass"]]
    n = len(out)
    return (f"{n - len(failed)}/{n} equivalenti migrati PASS (19 GOVERNED_PATH + 1 CORE_UNIT) · "
            f"falliti: {failed or 'nessuno'}"), ev, not failed


# =========================================================== E08 R0-R1
def e08():
    os.makedirs(REGRESSION_DIR, exist_ok=True)
    log = os.path.join(REGRESSION_DIR, "r0_r1_run_gate_post_fix.log")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CREATIVE_OS_CORE_PATH": CORE_PATH}
    env.pop("CREATIVE_OS_PROVIDER_BOUNDARY_MODE", None)
    env.pop("CREATIVE_OS_LEGACY_LAB_SPEND_PATH", None)
    r = subprocess.run([sys.executable, os.path.join(GATE01, "tests", "run_gate.py")],
                       capture_output=True, text=True, cwd=GATE01, env=env, timeout=5400)
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(r.stdout + "\n--- stderr ---\n" + r.stderr)
    results_path = os.path.join(GATE01, "evidence", "RESULTS.json")
    data = json.load(open(results_path, encoding="utf-8")) if os.path.exists(results_path) else {}
    summary = data.get("summary") or {}
    if os.path.exists(results_path):
        shutil.copy(results_path, os.path.join(REGRESSION_DIR, "r0_r1_RESULTS_post_fix.json"))
    shutil.copy(os.path.join(GATE01, "TEST_RESULTS.md"),
                os.path.join(REGRESSION_DIR, "r0_r1_TEST_RESULTS_post_fix.md"))
    pre_path = os.path.join(REGRESSION_DIR, "r0_r1_RESULTS_pre_fix.json")
    pre = json.load(open(pre_path, encoding="utf-8")).get("summary", {}) if os.path.exists(pre_path) else {}
    fails = set(summary.get("fail_ids") or [])
    pre_fails = set(pre.get("fail_ids") or [])
    new_fails = sorted(fails - pre_fails)
    ev = evidence("E08", "regression_r0_r1", {
        "core_path": CORE_PATH, "returncode": r.returncode, "summary": summary,
        "pre_fix_same_environment": pre,
        "declared_historical_baseline": {"total": 37, "pass": 36, "fail": 0,
                                         "blocked": [{"id": "T29",
                                                      "reason_code": "BLOCKED_ENVIRONMENT"}]},
        "regressions_introduced_by_this_phase": new_fails,
        "log": os.path.relpath(log, BUNDLE), "stdout_tail": r.stdout[-3000:],
        "note": ("Il confronto che conta e' PRE-FIX vs POST-FIX NELLO STESSO AMBIENTE. Un FAIL "
                 "presente gia' prima di questa fase non e' una regressione di questa fase: e' "
                 "un difetto preesistente, e va riferito come tale, non nascosto.")})
    ok = (not new_fails
          and summary.get("inventory", {}).get("valid") is True
          and summary.get("total") == 37
          and set(t["id"] for t in (summary.get("blocked_tests") or [])) <= {"T29"})
    return (f"T01-T37 sulla coppia candidate: PASS {summary.get('pass')}/{summary.get('total')} · "
            f"FAIL {sorted(fails) or 'nessuno'} (pre-fix nello stesso ambiente: "
            f"{sorted(pre_fails) or 'nessuno'}) · BLOCKED "
            f"{[t['id'] for t in (summary.get('blocked_tests') or [])]} · regressioni introdotte "
            f"da questa fase: {new_fails or 'nessuna'}"), ev, ok


# =========================================================== E09 meccanismi
def e09(scratch: str):
    """Rieseguo i meccanismi gia' verificati (P-B01+P-B02 composition, NG-04 freshness,
    legacy spend paths, orphan lease) con LE STESSE funzioni del gate approvato, contro
    la coppia candidate. Le evidenze vanno in QUESTO bundle: quelli approvati non si toccano."""
    sys.path.insert(0, os.path.join(REPO, "PROVIDER_BOUNDARY_GATE_02"))
    from pbg2 import run_gate2
    from tests import gate_report
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
                actual, evf, ok = fn()
                out[label] = {"ok": ok, "actual": actual, "evidence": evf}
            except gate_report.GateBlocked as b:
                out[label] = {"ok": False, "blocked": True, "reason_code": b.reason_code,
                              "actual": b.actual}
            print(f"       {DIM}· {label}: {'PASS' if out[label].get('ok') else out[label]}{RESET}",
                  flush=True)
    finally:
        run_gate2.CORE_PATH, run_gate2.EVIDENCE_DIR, run_gate2.RAW_DIR = saved
    # suite del CORE (non-regressione del delta Core)
    core_suites = {}
    for name in ("run_golden", "run_reservation", "run_boot_paths", "run_case_collision",
                 "run_block2", "run_review_pr2", "run_review_pr2_final",
                 "run_ng05_pre_submit_atomicity", "run_r0_r1_hardening"):
        p = subprocess.run([sys.executable, os.path.join(CORE_PATH, "tests", f"{name}.py")],
                           capture_output=True, text=True, cwd=CORE_PATH, timeout=3600,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        core_suites[name] = {"returncode": p.returncode, "tail": p.stdout.strip()[-200:]}
        print(f"       {DIM}· core/{name}: exit {p.returncode}{RESET}", flush=True)
    ev = evidence("E09", "mechanism_and_core_regressions", {
        "core_path": CORE_PATH, "mechanisms": out, "core_suites": core_suites,
        "not_run": {"tests/run_contamination.py":
                    "RUN_CONTAMINATION resta NOT_RUN per mandato: non viene chiuso "
                    "incidentalmente eseguendolo come segnale di non-regressione."}})
    failed = [k for k, v in out.items() if not v.get("ok")]
    failed += [k for k, v in core_suites.items() if v["returncode"] != 0]
    return (f"meccanismi sul candidate: {len(out) - len([k for k in failed if k in out])}/{len(out)} · "
            f"suite del Core: {len([v for v in core_suites.values() if v['returncode'] == 0])}/"
            f"{len(core_suites)} · falliti: {failed or 'nessuno'}"), ev, not failed


# =========================================================== E10 pin + P2
def e10():
    from runtime.core_pin import KNOWN_STALE_CORE_SHAS, REQUIRED_CORE_SHA, verify_core_pin
    head = git("rev-parse", "HEAD", cwd=CORE_PATH)
    p2_after = sha256_file(P2_PATH)
    checks = {
        "pin_equals_core_candidate_head": REQUIRED_CORE_SHA == head,
        "previous_canonical_baseline_is_now_stale":
            BASELINE_CORE_SHA in KNOWN_STALE_CORE_SHAS
            and verify_core_pin(BASELINE_CORE_SHA).code == "STALE_CORE_PIN",
        # HUMAN REVIEW 01: anche il candidate revisionato e' superato. Ha il confine,
        # ma l'autorizzazione che lo apriva era costruibile dal chiamante.
        "reviewed_candidate_is_now_stale":
            REVIEWED_CORE_SHA in KNOWN_STALE_CORE_SHAS
            and verify_core_pin(REVIEWED_CORE_SHA).code == "STALE_CORE_PIN",
        "unknown_sha_is_mismatch": verify_core_pin("de" * 20).code == "CORE_PIN_MISMATCH",
        "dirty_tree_fails_closed":
            verify_core_pin(REQUIRED_CORE_SHA, dirty=(" M adapters/base.py",)).code
            == "CORE_WORKTREE_DIRTY",
        "p2_before_equals_after": P2_BEFORE.get("sha256") == p2_after == P2_SHA,
    }
    ev = evidence("E10", "core_pin_and_p2_freeze", {
        "checks": checks, "required_core_sha": REQUIRED_CORE_SHA, "core_head": head,
        "known_stale": sorted(KNOWN_STALE_CORE_SHAS),
        "p2": {"before": P2_BEFORE.get("sha256"), "after": p2_after, "declared": P2_SHA,
               "path": os.path.relpath(P2_PATH, REPO)}})
    failed = [k for k, v in checks.items() if not v]
    return (f"pin {REQUIRED_CORE_SHA[:12]} == Core HEAD · {BASELINE_CORE_SHA[:12]} e "
            f"{REVIEWED_CORE_SHA[:12]} ora STALE · "
            f"P2 before==after=={p2_after[:16]}… · falliti: {failed or 'nessuno'}"), ev, not failed


# =========================================================== E11 catena evidence
def e11():
    """La catena deve distinguere code SHA, evidence-head SHA, base canonica e branch
    REALE. Qui si registra cio' che e' vero ADESSO; il commit dell'evidenza avra' un
    SHA diverso da quello del codice, ed e' esattamente il punto."""
    core_head = git("rev-parse", "HEAD", cwd=CORE_PATH)
    rt_head = git("rev-parse", "HEAD", cwd=REPO)
    # I bytecode sono artefatti dell'esecuzione, non evidenza: si rimuovono PRIMA
    # di verificare, e poi si verifica che non ce ne siano. Rimuoverli e basta
    # sarebbe una pulizia; verificarli dopo e' un controllo.
    for dirpath, dirnames, _ in list(os.walk(BUNDLE)):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
    pyc = []
    for dirpath, dirnames, filenames in os.walk(BUNDLE):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            if fn.endswith(".pyc") or "__pycache__" in dirpath:
                pyc.append(os.path.relpath(os.path.join(dirpath, fn), BUNDLE))
    # I bundle APPROVATI non si toccano. `RUNTIME_INTEGRATION_GATE_01/evidence` NON e'
    # in questa lista, e va detto perche': rieseguire la suite storica riscrive per
    # costruzione la propria evidenza: e' cio' che E08 fa. Le due copie (pre-fix e
    # post-fix) vivono in `regression/` di QUESTO bundle, e l'albero storico viene
    # riportato al suo stato prima della pubblicazione.
    approved_untouched = {
        b: git("status", "--porcelain", "--", b, cwd=REPO) == ""
        for b in ("PROVIDER_BOUNDARY_HARDENING_01", "PROVIDER_BOUNDARY_GATE_02",
                  "CORE_RUNTIME_INTEGRATION_01",
                  "RUNTIME_INTEGRATION_GATE_01/p2_handoff",
                  "RUNTIME_INTEGRATION_GATE_01/runtime", "RUNTIME_INTEGRATION_GATE_01/tests")}
    checks = {"no_pyc_or_pycache_in_bundle": not pyc,
              "core_code_sha_declared": len(core_head) == 40,
              "runtime_code_sha_declared": len(rt_head) == 40,
              **{f"approved_bundle_untouched:{k}": v for k, v in approved_untouched.items()}}
    ev = evidence("E11", "evidence_chain_integrity", {
        "checks": checks,
        "chain": {
            "canonical_base": {"core_main": BASELINE_CORE_SHA, "runtime_main": BASELINE_RUNTIME_SHA},
            "code_sha": {"core": core_head, "runtime": rt_head},
            "evidence_head_sha": "assegnato dal commit che pubblica questo bundle (successivo a "
                                 "code_sha: un bundle non puo' contenere il proprio hash)",
            "real_branch": {"core": git("rev-parse", "--abbrev-ref", "HEAD", cwd=CORE_PATH),
                            "runtime": git("rev-parse", "--abbrev-ref", "HEAD", cwd=REPO)}},
        "pyc_found": pyc})
    failed = [k for k, v in checks.items() if not v]
    return (f"nessun .pyc/__pycache__ · code SHA Core {core_head[:12]} / Runtime {rt_head[:12]} "
            f"distinti da evidence-head · bundle approvati intatti · falliti: "
            f"{failed or 'nessuno'}"), ev, not failed


# =========================================================== E12 reporting
def e12():
    from lspc1 import readiness
    rd = readiness.build(RESULTS, core_path=CORE_PATH, repo=REPO)
    with open(os.path.join(BUNDLE, "READINESS.json"), "w", encoding="utf-8") as fh:
        json.dump(rd, fh, indent=2, ensure_ascii=False, sort_keys=True)
    ev = evidence("E12", "reporting_test_result_vs_readiness", rd)
    checks = {
        "suite_result_and_readiness_are_separate_objects":
            "test_suite_result" in rd and "requirement_readiness" in rd,
        "all_requirements_verified_is_false": rd["requirement_readiness"]["all_requirements_verified"] is False,
        "ng04_policy_untouched":
            rd["requirement_readiness"]["requirements"]["RECONCILIATION_FRESHNESS_NG04_POLICY"]
            == "POLICY_DECISION_REQUIRED",
        "orphan_lease_policy_untouched":
            rd["requirement_readiness"]["requirements"]["ORPHAN_RESERVED_LEASE_POLICY"]
            == "POLICY_DECISION_REQUIRED",
        "real_provider_requirements_untouched":
            rd["requirement_readiness"]["requirements"]["REAL_AUTHORIZATION_AND_PRICING"]
            == "REAL_PROVIDER_REQUIRED",
        "run_contamination_still_not_run":
            rd["requirement_readiness"]["requirements"]["RUN_CONTAMINATION"] == "NOT_RUN",
        "independent_ci_still_not_run":
            rd["requirement_readiness"]["requirements"]["INDEPENDENT_CI_STATUS_CHECKS"] == "NOT_RUN",
        "no_provider_ready_claim": rd["explicitly_not_claimed"]["provider_ready"] is False,
    }
    failed = [k for k, v in checks.items() if not v]
    return (f"stato massimo: {rd['phase_state']} · suite: "
            f"{rd['test_suite_result']['pass']}/{rd['test_suite_result']['total']} · "
            f"requisiti aperti: {len(rd['requirement_readiness']['open'])} · falliti: "
            f"{failed or 'nessuno'}"), ev, not failed


# =========================================================== E13 forged capability
def e13(scratch: str):
    """HUMAN REVIEW 01 — DISPATCH_AUTHORIZATION_FORGEABLE.

    Due esecuzioni delle STESSE sonde: sul candidate revisionato `44f9ea29`, dove il
    difetto deve riprodursi, e sul delta correttivo, dove deve essere chiuso. Se il
    difetto non si riproducesse, questa sezione non proverebbe nulla."""
    from lspc1 import runner
    wt = os.path.join(scratch, "core_reviewed")
    subprocess.run(["git", "-C", CORE_PATH, "worktree", "add", "--detach", wt,
                    REVIEWED_CORE_SHA], check=True, capture_output=True)
    try:
        pre = runner.forge_probes(wt)
    finally:
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "remove", "--force", wt],
                       capture_output=True)
        subprocess.run(["git", "-C", CORE_PATH, "worktree", "prune"], capture_output=True)
    post = runner.forge_probes(CORE_PATH)

    def att(run_, probe, name):
        return ((run_.get(probe) or {}).get("attempts") or {}).get(name) or {}

    def sent(run_, probe, field="reached"):
        return ((run_.get(probe) or {}).get("sentinel") or {}).get(field)

    reproduced = {
        "counterexample_reached_spender_on_reviewed_candidate":
            att(pre, "P11", "counterexample_review").get("refused") is False,
        "slot_injection_reached_spender": att(pre, "P11", "slot_injection").get("refused") is False,
        "two_arg_grant_existed": att(pre, "P11", "grant_dispatch_two_arg").get("refused") is False,
        "direct_hooks_reached_spender": (sent(pre, "P12") or 0) >= 1,
        "sentinel_reached_on_reviewed_candidate": (sent(pre, "P11") or 0) >= 1,
    }
    closed = {
        "counterexample_refused":
            att(post, "P11", "counterexample_review").get("code") == "DISPATCH_AUTHORIZATION_FORGED",
        "slot_injection_refused":
            att(post, "P11", "slot_injection").get("code") == "DISPATCH_AUTHORIZATION_FORGED",
        "two_arg_grant_no_longer_exists":
            att(post, "P11", "grant_dispatch_two_arg").get("error") == "TypeError",
        "grant_dispatch_takes_the_store":
            (post.get("P11") or {}).get("grant_dispatch_accepts_authorization") is False,
        "hooks_refused": all(
            att(post, "P12", n).get("refused") is True
            for n in ("_dispatch_senza_grant", "_authorize_payload_senza_grant",
                      "_dispatch_con_autorizzazione_fabbricata",
                      "_authorize_payload_con_autorizzazione_fabbricata")),
        "hooks_guarded_by_base": all(
            (post.get("P12") or {}).get("hooks_guarded", {}).values()),
        "sentinel_zero_forged": (post.get("P11") or {}).get("sentinel_zero") is True,
        "sentinel_zero_hooks": (post.get("P12") or {}).get("sentinel_zero") is True,
    }
    ev = evidence("E13", "forged_dispatch_authorization", {
        "reviewed_core_sha": REVIEWED_CORE_SHA, "corrective_core_sha":
            git("rev-parse", "HEAD", cwd=CORE_PATH),
        "blocker_reproduced_on_reviewed_candidate": reproduced,
        "blocker_closed_on_corrective_delta": closed,
        "probes_pre_fix": pre, "probes_post_fix": post,
        "note": ("`bypass_constructor` risulta NON rifiutato in entrambe le esecuzioni, ed e' "
                 "corretto: costruire un oggetto Python e' sempre possibile. Cio' che conta "
                 "e' che quell'oggetto non apra nulla — vedi `slot_injection`.")})
    failed = [k for k, v in {**{f"repro:{k}": v for k, v in reproduced.items()},
                             **{f"closed:{k}": v for k, v in closed.items()}}.items() if not v]
    return (f"sul candidate revisionato {REVIEWED_CORE_SHA[:12]}: sentinella "
            f"{sent(pre, 'P11')} (forge) / {sent(pre, 'P12')} (hook) — BLOCKER_REPRODUCED · "
            f"sul correttivo: 0 / 0, controesempio -> DISPATCH_AUTHORIZATION_FORGED, "
            f"grant a due argomenti inesistente · falliti: {failed or 'nessuno'}"), ev, not failed


# =========================================================== E14 threat model
def e14():
    from lspc1 import threat_model
    r = threat_model.verify()
    doc = os.path.join(BUNDLE, "THREAT_MODEL.md")
    checks = dict(r["checks"])
    checks["documented_alongside_machine_readable"] = os.path.isfile(doc)
    ev = evidence("E14", "threat_model", {"checks": checks, "model": r["model"]})
    failed = [k for k, v in checks.items() if not v]
    n_core = len(r["model"]["core_boundary"]["protects_against"])
    n_out = len(r["model"]["explicitly_not_protected_against"])
    return (f"confine del Core: {n_core} minacce coperte, ognuna con evidenza · P-B01: "
            f"{len(r['model']['process_boundary_p_b01']['protects_against'])} · fuori "
            f"perimetro, dichiarate: {n_out} · falliti: {failed or 'nessuno'}"), ev, not failed


# =========================================================================
def main() -> int:
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    os.makedirs(REGRESSION_DIR, exist_ok=True)
    print(f"LEGACY SPEND PATH CLOSURE 01 — Core {CORE_PATH} @ "
          f"{git('rev-parse', 'HEAD', cwd=CORE_PATH)[:12]}")
    _cleanup_state()                     # igiene PRIMA del Reality Lock, non dopo
    scratch = tempfile.mkdtemp(prefix="lspc1_")
    try:
        record("E00", "Reality Lock", "coppia canonica verificata, branch dedicati, P2 invariato", e00)
        record("E01", "inventario statico dei percorsi di spesa",
               "ogni entry point che tocca la catena di spesa, in Core e Runtime", e01)
        record("E02", "riproduzione PRE-FIX sulla coppia canonica",
               "lo spender E' raggiungibile dai percorsi legacy su 9cf9cee1 + fea7b439",
               lambda: e02(scratch))
        record("E03", "classificazione delle primitive del Core + suite unitaria del confine",
               "delta additivo, 11/11 PASS", e03)
        record("E04", "controprove del confine provider (sentinella)",
               "0 attraversamenti in ogni percorso legacy, 1 nel governato", e04)
        record("E05", "LEGACY_LAB = LAB_ONLY_NON_PROVIDER_CAPABLE",
               "adapter/modalita'/config non riaprono un percorso di spesa", e05)
        record("E06", "percorsi legacy di envelope/budget",
               "il client non sceglie il prezzo; envelope_units non raggiunge lo spender", e06)
        record("E07", "migrazione dei test storici",
               "20/20 equivalenti governati o Core-unit, assert non indeboliti", e07)
        record("E08", "regressione R0-R1 T01-T37",
               "nessuna regressione introdotta da questa fase", e08)
        record("E09", "meccanismi approvati + suite del Core sulla coppia candidate",
               "P-B01/P-B02, NG-04, legacy spend paths, orphan lease, suite Core: verdi",
               lambda: e09(scratch))
        record("E10", "Core pin e P2 freeze", "pin sul candidate, baseline precedente STALE, "
                                              "P2 before == after", e10)
        record("E11", "integrita' della catena di evidenza",
               "code SHA / evidence-head / base canonica / branch distinti, 0 .pyc", e11)
        record("E13", "HUMAN REVIEW 01: autorizzazione fabbricata e hook diretti",
               "difetto riprodotto su 44f9ea29, chiuso sul correttivo, sentinella 0",
               lambda: e13(scratch))
        record("E14", "threat model del confine dello spender",
               "cosa protegge il Core, cosa protegge P-B01, cosa nessuno dei due pretende", e14)
        record("E12", "reporting: esito della suite vs readiness del requisito",
               "due oggetti separati; nessun requisito chiuso per errore", e12)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        _cleanup_state()
    return _write_results()


def _cleanup_state():
    """Riporta il bundle STORICO esattamente al suo stato committato.

    Rieseguire la suite R0-R1 riscrive la propria evidenza e lascia artefatti in
    `state/` (store, snapshot, esche della sentinella). Sono artefatti di
    esecuzione, non evidenza di questa fase: le due copie che contano (pre-fix e
    post-fix) vivono in `regression/` di QUESTO bundle. Qui si ripristina l'albero
    storico e si rimuove SOLO cio' che non e' tracciato sotto di esso — mai nulla
    fuori da `RUNTIME_INTEGRATION_GATE_01`."""
    subprocess.run(["git", "-C", REPO, "checkout", "--", "RUNTIME_INTEGRATION_GATE_01"],
                   capture_output=True)
    out = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--untracked-files=all",
                          "--", "RUNTIME_INTEGRATION_GATE_01"],
                         capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if not ln.startswith("??"):
            continue
        rel = ln[3:].strip()
        if not rel.startswith("RUNTIME_INTEGRATION_GATE_01/"):
            continue
        path = os.path.join(REPO, rel)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)


def _write_results() -> int:
    # READINESS riscritto sui risultati COMPLETI: quando E12 lo costruisce, se stesso
    # non e' ancora nel conteggio (un passo non puo' riferire il proprio esito prima di
    # averlo). Qui la lista e' chiusa, e il file finale copre tutti i passi.
    try:
        from lspc1 import readiness
        rd = readiness.build(RESULTS, core_path=CORE_PATH, repo=REPO)
        with open(os.path.join(BUNDLE, "READINESS.json"), "w", encoding="utf-8") as fh:
            json.dump(rd, fh, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception as e:                                  # noqa: BLE001
        print(f"{RED}READINESS non riscritto: {type(e).__name__}: {e}{RESET}")
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["pass"])
    failed = [r["id"] for r in RESULTS if not r["pass"]]
    summary = {"schema": "legacy-spend-path-closure-results/1", "total": total, "pass": passed,
               "fail": len(failed), "fail_ids": failed,
               "pass_ids": [r["id"] for r in RESULTS if r["pass"]],
               "gate_decision": "LSPC_GATE_COMPLETE" if not failed else "LSPC_GATE_NOT_FAVORABLE",
               "runner_exit": 0 if not failed else 1}
    with open(os.path.join(EVIDENCE_DIR, "RESULTS.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": summary["schema"], "results": RESULTS, "summary": summary},
                  fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    lines = ["# TEST RESULTS — LEGACY SPEND PATH CLOSURE + LEGACY TEST MIGRATION", "",
             "MOCK ONLY · ZERO PROVIDER REALI · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUZIONE.", "",
             "| # | verifica | EXPECTED | ACTUAL | EVIDENCE | ESITO |", "|---|---|---|---|---|---|"]
    for r in RESULTS:
        lines.append(f"| {r['id']} | {r['title']} | {r['expected']} | {r['actual']} | "
                     f"`{r['evidence']}` | {'PASS' if r['pass'] else 'FAIL'} |")
    lines += ["", f"**{passed}/{total} PASS** · falliti: {failed or 'nessuno'}", "",
              "Un PASS qui e' un ESITO DI SUITE, non una readiness: vedi `READINESS.json` e "
              "`OPEN_REQUIREMENTS.md`.", ""]
    with open(os.path.join(BUNDLE, "TEST_RESULTS.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\n{passed}/{total} PASS · falliti: {failed or 'nessuno'}")
    print("crediti spesi: 0 · provider reali: 0 · rete generativa: 0")
    return summary["runner_exit"]


if __name__ == "__main__":
    sys.exit(main())
