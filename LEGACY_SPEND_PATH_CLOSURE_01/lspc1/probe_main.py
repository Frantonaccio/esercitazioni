#!/usr/bin/env python3
"""Esecutore delle sonde, invocato come PROCESSO A SE'.

    python3 -m lspc1.probe_main <core_path> <out.json> [gate01_path]

Perche' un processo separato e non una funzione: le sonde PRE-FIX devono girare
contro un Runtime diverso (il worktree canonico `fea7b439`). Un interprete che ha
gia' importato il Runtime candidate non puo' fingere di non averlo fatto — e un
test che finge non e' un test. Qui l'isolamento e' reale: interprete nuovo,
`sys.path` nuovo, ambiente nuovo.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import sys

if len(sys.argv) >= 4 and sys.argv[3]:
    os.environ["LSPC1_GATE01"] = sys.argv[3]

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BUNDLE not in sys.path:
    sys.path.insert(0, BUNDLE)

from lspc1 import workers                                           # noqa: E402

CTX = multiprocessing.get_context("spawn")


def run(fn, *a, **k) -> dict:
    q = CTX.Queue()
    p = CTX.Process(target=workers._entry, args=(q, fn, a, k))
    p.start()
    p.join(240)
    if p.is_alive():
        p.terminate()
        return {"ok": False, "error": "TIMEOUT_PROCESS"}
    return q.get(timeout=10)


def probes(core: str) -> dict:
    sd = workers.state_db
    plan = [
        ("P1", workers.p1_legacy_with_spender, (core, sd("p1")), {}),
        ("P1pin", workers.p1_legacy_with_spender, (core, sd("p1b")), {"break_pin": True}),
        ("P2", workers.p2_legacy_with_lab_adapter, (core, sd("p2")), {}),
        ("P3", workers.p3_governed_with_spender, (core, sd("p3")), {}),
        ("P4", workers.p4_core_run_job_direct, (core, sd("p4")), {}),
        ("P4env", workers.p4_core_run_job_direct, (core, sd("p4b")), {"envelope_units": 1000}),
        ("P5", workers.p5_adapter_submit_direct, (core, sd("p5")), {}),
        ("P6", workers.p6_authorize_payload_direct, (core, sd("p6")), {}),
        ("P7", workers.p7_reconcile_raw, (core, sd("p7")), {}),
        ("P7al", workers.p7_reconcile_raw, (core, sd("p7b")), {"allowlist": True}),
        ("P8", workers.p8_store_call, (core, sd("p8")), {}),
        ("P10", workers.p10_hf_batch_legacy, (core, sd("p10")), {}),
    ]
    return {name: run(fn, *a, **k) for name, fn, a, k in plan}


def switches(core: str) -> dict:
    return run(workers.p9_config_switches, core, os.path.join(workers.STATE_DIR, "lspc1_p9"))


def budget(core: str) -> dict:
    """I percorsi economici legacy: chi puo' ancora scegliere un importo, e dove."""
    sd = workers.state_db
    out = {}
    out["core_envelope_units"] = run(workers.p4_core_run_job_direct, core, sd("b1"),
                                     envelope_units=1000, prompt="b1 client budget")
    # Runtime GOVERNATO con envelope_units grezzo
    out["runtime_envelope_units"] = run(workers.gov_run, core, sd("b2"), "b2 env units",
                                        op="LSPCB:b2", amount=10, envelope_units=500,
                                        intent="new_attempt", reason="INITIAL_GENERATION",
                                        auto_permit=True)
    # il client presenta un importo DIVERSO dalla quote fidata
    out["client_amount_mismatch"] = run(workers.gov_run, core, sd("b3"), "b3 mismatch",
                                        op="LSPCB:b3", amount=10, budget_units=1,
                                        intent="new_attempt", reason="INITIAL_GENERATION",
                                        auto_permit=True)
    # il client NON presenta alcun importo: lo riceve dalla quote
    out["client_omits_amount"] = run(workers.gov_run, core, sd("b4"), "b4 omit",
                                     op="LSPCB:b4", amount=10, budget_units=None,
                                     intent="new_attempt", reason="INITIAL_GENERATION",
                                     auto_permit=True)
    # laboratorio: budget_units/envelope_units restano disponibili
    out["lab_budget_units"] = run(workers.p2_legacy_with_lab_adapter, core, sd("b5"),
                                  prompt="b5 lab budget")
    return out


def main() -> int:
    core, outfile = sys.argv[1], sys.argv[2]
    mode = os.environ.get("LSPC1_PROBE_MODE", "probes")
    data = {"probes": probes, "switches": switches, "budget": budget}[mode](core)
    with open(outfile, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
