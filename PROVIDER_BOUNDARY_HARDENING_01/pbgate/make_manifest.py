#!/usr/bin/env python3
"""MANIFEST.json generato dalla STESSA classificazione del gate (Human Review 02).

Il manifest non riassume a mano nulla: legge `evidence/RESULTS.json`, ne prende il report
prodotto da `pbgate/phase_readiness.py` e lo riporta con le due sezioni separate, piu' le
reference Git non ambigue. Cosi' console, RESULTS.json, TEST_RESULTS.md, README e MANIFEST
dicono la stessa cosa per costruzione, e B13 lo verifica.

    python3 pbgate/make_manifest.py <runtime_code_sha>
"""
from __future__ import annotations

import json
import os
import sys

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BUNDLE not in sys.path:
    sys.path.insert(0, BUNDLE)

from pbgate import phase_readiness                                  # noqa: E402

CANONICAL = {
    "core_repo": "Frantonaccio/creative-os", "core_branch": "main",
    "core_sha": "740ee979300fe20a9382992528604dee70cb2fcf",
    "runtime_repo": "Frantonaccio/esercitazioni",
    "canonical_runtime_base_sha": "39c82968fbfb3f3b7ba9fcfe9dc317ea0da9e74e",
    "runtime_branch": "claude/provider-boundary-hardening-c1k77q",
    "required_core_sha": "740ee979300fe20a9382992528604dee70cb2fcf",
    "p2_sha256": "637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1",
}
SUPERSEDES = [
    {"bundle_version": "v1", "external_sha256": "054ea4821097eca1f95264ae3acb3b037f8ab1219d0536cca9c1f90a0d61b961",
     "code_sha": "9aafe9b16f10861846ec7527191009c6e0dabbd6", "evidence_head_sha": "c66fd30c41c132c394ad54619d317d8c9f16f60d",
     "verdict": "HUMAN_REVIEW_HOLD — PRE_SEND_PROVENANCE_MISMATCH"},
    {"bundle_version": "v2", "external_sha256": "b54de9b5b7a661fc28f4d18488f8eac77d8a369cdcb4ec2deb5f00a4cb9e04a4",
     "code_sha": "7fa9cd656ce5970cbd8a549345d8330abbe79f47", "evidence_head_sha": "06771aa6fbf7f210575b08f9453610e305e11921",
     "verdict": "HUMAN_REVIEW_HOLD — PHASE_READINESS_REPORTING_INCONSISTENT (reporting-only)"},
]


def build_manifest(report: dict, *, runtime_code_sha: str, bundle_version: str = "v3") -> dict:
    """Manifest DERIVATO dal report: nessun valore di stato e' ricalcolato qui."""
    phase_readiness.validate(report)
    ts, pr = report["test_suite"], report["phase_readiness"]
    return {
        "package_name": f"VF_PROVIDER_EXECUTION_BOUNDARY_HARDENING_EVIDENCE_{bundle_version.lstrip('v').zfill(2)}",
        "bundle_version": bundle_version, "created_date": "2026-09-17",
        "phase": "PROVIDER / EXECUTION BOUNDARY HARDENING",
        "declared_state": pr["max_state"],
        "not_implied": pr["not_implied"] + ["P-B01 verified beyond LAB uid boundary",
                                            "P-B02 composed with P-B01 inside the isolated spender"],
        "supersedes": SUPERSEDES,
        # --- A. test suite (fatti sui test) --------------------------------------------
        "test_suite": {"runner": "pbgate/run_boundary_gate.py", "inventory": ts["inventory"],
                       "total": ts["total"], "pass": ts["pass"], "fail": ts["fail"], "blocked": ts["blocked"],
                       "all_tests_passed": ts["all_tests_passed"],
                       "test_suite_decision": ts["test_suite_decision"], "meaning": ts["meaning"]},
        # --- B. readiness di fase (requisiti) ------------------------------------------
        "phase_readiness": {"all_requirements_verified": pr["all_requirements_verified"],
                            "phase_gate_decision": pr["phase_gate_decision"],
                            "max_state": pr["max_state"],
                            "open_requirements_this_phase": pr["open_requirements_this_phase"],
                            "open_requirements_future_gate": pr["open_requirements_future_gate"],
                            "open_requirements_other_phase": pr["open_requirements_other_phase"],
                            "verified_requirements": pr["verified_requirements"], "meaning": pr["meaning"]},
        "gap_status": phase_readiness.machine_readable_gaps(report),
        # --- reference Git non ambigue --------------------------------------------------
        "references": {**CANONICAL, "runtime_code_sha": runtime_code_sha,
                       "runtime_code_sha_meaning": "commit containing code + evidence + documents of this bundle",
                       "runtime_evidence_head_sha": "declared in PROVENANCE.json (external file, generated after the "
                                                    "commit that adds this manifest; a manifest cannot name its own commit)",
                       "core_changed": False, "core_branch_created": False, "main_touched": False},
        "credits_spent": 0, "real_providers": 0, "real_credentials": 0, "generative_network_calls": 0,
        "checksums": "SHA256SUMS covers every committed bundle file (this manifest included, SHA256SUMS itself "
                     "excluded); SHA256SUMS.EXTERNAL covers PROVENANCE.json, generated after the final commit",
        "authority": "pbgate/phase_readiness.py — console, RESULTS.json, TEST_RESULTS.md, README e questo manifest "
                     "derivano tutti dallo stesso report; B13 verifica la coerenza.",
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    report = json.load(open(os.path.join(BUNDLE, "evidence", "RESULTS.json"), encoding="utf-8"))["report"]
    manifest = build_manifest(report, runtime_code_sha=sys.argv[1],
                              bundle_version=sys.argv[2] if len(sys.argv) > 2 else "v3")
    with open(os.path.join(BUNDLE, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    pr = manifest["phase_readiness"]
    print(f"MANIFEST.json {manifest['bundle_version']} · code {sys.argv[1][:12]} · "
          f"all_tests_passed={manifest['test_suite']['all_tests_passed']} · "
          f"all_requirements_verified={pr['all_requirements_verified']} · {pr['phase_gate_decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
