#!/usr/bin/env python3
"""PHASE A — INSPECT / REPRODUCE.

Esegue le riproduzioni PRE-FIX sul Runtime canonico attuale e scrive
`evidence/pre_fix/reproduction_*.json`. Nessuna correzione avviene qui.

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BUNDLE)
GATE01 = os.path.join(REPO, "RUNTIME_INTEGRATION_GATE_01")
BUNDLE01 = os.path.join(REPO, "PROVIDER_BOUNDARY_HARDENING_01")
CORE_PATH = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")
STATE_DIR = os.path.join(GATE01, "state")
PRE_FIX_DIR = os.path.join(BUNDLE, "evidence", "pre_fix")
for p in (GATE01, BUNDLE01, BUNDLE):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("RUNTIME_GATE_ROOT", GATE01)
os.environ.setdefault("PBGATE01_ROOT", BUNDLE01)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from pbgate import pb_worker                                # noqa: E402
from pbg2 import repro_workers                              # noqa: E402

CTX = multiprocessing.get_context("spawn")


def db_for(name: str) -> str:
    p = os.path.join(STATE_DIR, f"pbg2_{name}.db")
    pb_worker.cleanup_db(p)
    return p


def in_process(fn, *args, **kwargs) -> dict:
    q = CTX.Queue()
    p = CTX.Process(target=pb_worker._entry, args=(q, fn, args, kwargs))
    p.start()
    p.join(180)
    if p.is_alive():
        p.terminate()
        return {"ok": False, "error": "TIMEOUT_PROCESS"}
    if q.empty():
        return {"ok": False, "error": "NO_RESULT", "exitcode": p.exitcode}
    return q.get(timeout=10)


def run_until_exit(fn, *args, **kwargs) -> dict:
    """Come `in_process`, ma il figlio puo' morire volontariamente (os._exit): si riferisce
    l'exitcode invece di pretendere un risultato."""
    q = CTX.Queue()
    p = CTX.Process(target=pb_worker._entry, args=(q, fn, args, kwargs))
    p.start()
    p.join(180)
    return {"exitcode": p.exitcode, "result": (q.get(timeout=5) if not q.empty() else None)}


def write(name: str, payload: dict) -> str:
    os.makedirs(PRE_FIX_DIR, exist_ok=True)
    path = os.path.join(PRE_FIX_DIR, f"reproduction_{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    return os.path.relpath(path, BUNDLE)


# ------------------------------------------------------------------ riproduzioni
def ng04() -> dict:
    db = db_for("ng04")
    prep = in_process(repro_workers.prepare_unknown_jobs, db, CORE_PATH, ["lab:ng04_a", "lab:ng04_b"])
    r = in_process(repro_workers.repro_ng04_stale_report_accepted, db, CORE_PATH)
    pb_worker.cleanup_db(db)
    return {"prepare": prep, "repro": r,
            "status": "REPRODUCED" if r.get("reproduced") else "NOT_REPRODUCED"}


def ng05() -> dict:
    surface = in_process(repro_workers.repro_ng05_core_surface, CORE_PATH)
    db = db_for("ng05")
    prep = in_process(repro_workers.prepare_unknown_jobs, db, CORE_PATH, ["lab:ng05_a"])
    rows = pb_worker._rows(db)
    job_id = rows[0]["job_id"] if rows else None
    totals_before = in_process(repro_workers._totals, db, CORE_PATH) if job_id else None
    crash = run_until_exit(repro_workers.repro_ng05_crash_between, db, CORE_PATH, job_id) if job_id else None
    after_rows = pb_worker._rows(db)
    totals_after = in_process(repro_workers._totals, db, CORE_PATH) if job_id else None
    terminal_unsettled = (totals_after or {}).get("terminal_unsettled_jobs")
    row_after = next((r for r in after_rows if r["job_id"] == job_id), None)
    reproduced = bool(
        surface.get("core_change_required")
        and crash and crash.get("exitcode") == 7
        and row_after and row_after["state"] == "FAILED" and row_after["settled_units"] is None
        and terminal_unsettled == 1)
    pb_worker.cleanup_db(db)
    return {"core_surface": surface, "prepare": prep, "job_id": job_id,
            "totals_before": totals_before, "crash": crash, "row_after": row_after,
            "totals_after": totals_after,
            "status": "REPRODUCED" if reproduced else "NOT_REPRODUCED"}


def orphan() -> dict:
    db = db_for("orphan")
    r = in_process(repro_workers.repro_orphan_no_exit, db, CORE_PATH)
    pb_worker.cleanup_db(db)
    return {"repro": r, "status": "REPRODUCED" if r.get("reproduced") else "NOT_REPRODUCED"}


def legacy() -> dict:
    db1, db2, db3 = db_for("legacy1"), db_for("legacy2"), db_for("legacy3")
    switch = in_process(repro_workers.repro_legacy_spendable, db1, CORE_PATH, "legacy repro", "lab:legacy_repro")
    helper = in_process(repro_workers.repro_test_helper_store_call, db2, CORE_PATH)
    core = in_process(repro_workers.repro_core_primitive_direct, db3, CORE_PATH)
    for d in (db1, db2, db3):
        pb_worker.cleanup_db(d)
    reproduced = bool(switch.get("reproduced") and helper.get("reproduced") and core.get("reproduced"))
    return {"legacy_lab_switch": switch, "test_helper_store_call": helper,
            "core_primitives_direct": core,
            "status": "REPRODUCED" if reproduced else "NOT_REPRODUCED"}


def composition() -> dict:
    static = in_process(repro_workers.repro_composition_not_exercised, CORE_PATH)
    db = db_for("composition")
    prep = in_process(repro_workers.prepare_unknown_jobs, db, CORE_PATH, ["lab:comp_a"])
    forge = in_process(repro_workers.repro_forge_with_leaked_key, db, CORE_PATH)
    pb_worker.cleanup_db(db)
    reproduced = bool(static.get("reproduced") and forge.get("reproduced"))
    return {"static": static, "prepare": prep, "forge_with_leaked_key": forge,
            "status": "REPRODUCED" if reproduced else "NOT_REPRODUCED"}


def main() -> int:
    out = {}
    for name, fn in (("ng04_freshness", ng04), ("ng05_atomicity", ng05),
                     ("orphan_lease", orphan), ("legacy_spend_paths", legacy),
                     ("pb01_pb02_composition", composition)):
        print(f"[repro] {name} …", flush=True)
        res = fn()
        out[name] = res
        print(f"[repro] {name}: {res['status']}", flush=True)
        write(name, res)
    summary = {k: v["status"] for k, v in out.items()}
    write("SUMMARY", {"summary": summary, "core_path": CORE_PATH,
                      "runtime_head": subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                                                     capture_output=True, text=True).stdout.strip(),
                      "core_head": subprocess.run(["git", "-C", CORE_PATH, "rev-parse", "HEAD"],
                                                  capture_output=True, text=True).stdout.strip()})
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if all(v == "REPRODUCED" for v in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
