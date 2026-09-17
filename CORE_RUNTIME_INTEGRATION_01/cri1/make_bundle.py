#!/usr/bin/env python3
"""Confezionamento del bundle di integrazione, in DUE passi.

    python3 cri1/make_bundle.py manifest     # PRIMA del commit evidence
    <git add -A && git commit>               # -> runtime_evidence_head_sha
    python3 cri1/make_bundle.py package      # DOPO il commit evidence

Riusa, senza copiarla, l'authority di provenance approvata dalla Human Review
(`PROVIDER_BOUNDARY_GATE_02/pbg2/bundle_provenance.py`): stessa catena non
self-referenziale, stesso verificatore fail-closed, stessa regola sul `SHA256SUMS` che copre
`MANIFEST.json`, stesso divieto della chiave ambigua `runtime_commit`.

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BUNDLE)
BUNDLE_REL = os.path.basename(BUNDLE)
BUNDLE02 = os.path.join(REPO, "PROVIDER_BOUNDARY_GATE_02")
GATE01 = os.path.join(REPO, "RUNTIME_INTEGRATION_GATE_01")
CORE_BASELINE = os.environ.get("CREATIVE_OS_CORE_BASELINE_PATH", "/home/user/creative-os")
CORE_CANDIDATE = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os-atomicity")
P2 = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "P2_RUNTIME",
                  "hf_batch.py")
OUT_DIR = os.environ.get("CRI1_PACKAGE_OUT",
                         "/tmp/claude-0/-home-user-esercitazioni/"
                         "48f94f47-e448-5466-9811-f92e1498b0cd/scratchpad")
ZIP_NAME = "VF_CORE_RUNTIME_INTEGRATION_NG05_EVIDENCE_2026-09-17.zip"
CANONICAL_RUNTIME_BASE = "0698279703ab959625ac4e84ee636bc5b93b45fd"
REVIEWED_RUNTIME_HEAD = "4a73cdad18034e7c1bd9842a37e34e0273f9325a"
APPROVED_CORE_CANDIDATE = "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515"

for p in (GATE01, BUNDLE02, BUNDLE, REPO):
    if p not in sys.path:
        sys.path.insert(0, p)
from pbg2 import bundle_provenance as bp                         # noqa: E402
from runtime.core_pin import REQUIRED_CORE_SHA                   # noqa: E402


def git(*a, cwd=REPO) -> str:
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True,
                          check=True).stdout.strip()


def build_manifest(report: dict, gap_status: dict, file_count: int) -> dict:
    pair = report["pair_readiness"]
    pr, ts = report["phase_readiness"], report["test_suite"]
    return {
        "schema": "core-runtime-integration-ng05-manifest/1",
        "phase": "COORDINATED CORE + RUNTIME INTEGRATION — NG-05",
        "date": "2026-09-17",
        "perimeter": "MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · "
                     "NO PRODUCTION · NO DEPLOY · NO TAG · NO RELEASE · NO MERGE",
        "approved_inputs": {
            "core_baseline": "740ee979300fe20a9382992528604dee70cb2fcf",
            "core_candidate": APPROVED_CORE_CANDIDATE,
            "core_candidate_branch": "harden/provider-boundary-core-atomicity-2026-09-17",
            "core_candidate_review_state": "APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED",
            "runtime_main": CANONICAL_RUNTIME_BASE,
            "runtime_reviewed_code_sha": "e845b744a4af3a143b1b1e710016726c57ad6c39",
            "runtime_reviewed_evidence_head_sha": REVIEWED_RUNTIME_HEAD,
            "evidence_bundle_v2_sha256":
                "12cd7773f5d242578ae877d34bb6d3603d429725127626a7ff4d1780dd20e078",
        },
        # --- i due SHA, disambiguati (struttura approvata, preservata) ---------------------
        "runtime_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "runtime_code_sha": bp.runtime_code_sha(REPO),
        "runtime_code_sha_meaning":
            "commit che porta il diff FUNZIONALE coordinato del Runtime (consumo di "
            "mark_refused_pre_submit + spostamento di REQUIRED_CORE_SHA).",
        "runtime_evidence_head_sha": bp.EXTERNAL_ONLY,
        "runtime_evidence_head_sha_meaning":
            "commit che aggiunge MANIFEST.json + SHA256SUMS. Un file committato non puo' "
            "dichiarare lo SHA del commit che lo contiene: il valore vive in PROVENANCE.json.",
        "canonical_runtime_base_sha": CANONICAL_RUNTIME_BASE,
        "reviewed_runtime_base_sha": REVIEWED_RUNTIME_HEAD,
        "core_candidate": {
            "repo": "Frantonaccio/creative-os",
            "branch": git("rev-parse", "--abbrev-ref", "HEAD", cwd=CORE_CANDIDATE),
            "sha": git("rev-parse", "HEAD", cwd=CORE_CANDIDATE),
            "base": "740ee979300fe20a9382992528604dee70cb2fcf",
            "review_state": "APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED",
            "modified_by_this_delta": False,
            "consumed_by_runtime_candidate": pair["runtime_consumes_core_candidate"],
        },
        "core_pin": {"required_core_sha": REQUIRED_CORE_SHA,
                     "points_to_core_candidate": pair["pin_points_to_core_candidate"],
                     "previous": "740ee979300fe20a9382992528604dee70cb2fcf"},
        "p2_sha256": bp.sha256_file(P2),
        # `merge_readiness` e' il nome che il verificatore approvato cerca: qui e' la
        # PAIR READINESS di questa fase, che lo estende senza cambiarne le chiavi.
        "merge_readiness": pair,
        "pair_readiness": pair,
        "test_suite": {k: ts[k] for k in ("total", "pass", "fail", "blocked",
                                          "all_tests_passed", "test_suite_decision")},
        "phase_readiness": {
            "all_requirements_verified": pr["all_requirements_verified"],
            "phase_gate_decision": pr["phase_gate_decision"],
            "max_state": pr["max_state"],
            "max_state_meaning": pr["max_state_meaning"],
            "open_requirements_blocking_all_verified": pr["open_requirements_blocking_all_verified"],
            "policy_decision_required": pr["policy_decision_required"],
            "real_provider_required": pr["real_provider_required"],
            "core_change_required": pr["core_change_required"],
        },
        "gap_status": gap_status,
        "files_covered_by_sha256sums": file_count,
        "sha256sums": bp.SUMS_NAME,
        "sha256sums_scope": "ogni file committato del bundle, incluso MANIFEST.json, "
                            "escluso soltanto SHA256SUMS stesso",
        "external_provenance": {"file": bp.PROVENANCE_NAME, "checksums": bp.EXTERNAL_SUMS_NAME,
                                "committed": False},
        "not_implied": pr["not_implied"],
        "next": "Human Merge Authorization separata. Nessun merge, nessun tag, nessun deploy.",
    }


def cmd_manifest() -> int:
    rd = json.load(open(os.path.join(BUNDLE, "READINESS.json"), encoding="utf-8"))
    manifest = build_manifest(rd["report"], rd["gap_status"], 0)
    path = os.path.join(BUNDLE, bp.MANIFEST_NAME)
    json.dump(manifest, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False,
              sort_keys=True)
    files = bp.disk_files(BUNDLE)
    manifest["files_covered_by_sha256sums"] = len(files)
    json.dump(manifest, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False,
              sort_keys=True)
    bp.write_sums(BUNDLE, files)
    check = bp.verify(BUNDLE, expect_committed=False)
    print(json.dumps({"runtime_code_sha": manifest["runtime_code_sha"],
                      "runtime_evidence_head_sha": manifest["runtime_evidence_head_sha"],
                      "core_pin": manifest["core_pin"], "files_covered": len(files),
                      "manifest_covered": bp.MANIFEST_NAME in bp.read_sums(
                          os.path.join(BUNDLE, bp.SUMS_NAME)),
                      "verify_problems": check["problems"],
                      "pair_readiness": {k: manifest["pair_readiness"][k]
                                         for k in ("core_runtime_pair_ready", "merge_authorized")}},
                     indent=2, ensure_ascii=False))
    return 0 if check["ok"] else 1


def cmd_package() -> int:
    manifest = json.load(open(os.path.join(BUNDLE, bp.MANIFEST_NAME), encoding="utf-8"))
    code_sha, head = manifest["runtime_code_sha"], git("rev-parse", "HEAD")
    if head == code_sha:
        raise SystemExit("il commit evidence non esiste ancora: HEAD == runtime_code_sha")
    stub = {"runtime_code_sha": code_sha, "runtime_evidence_head_sha": head}
    verification = bp.verify(BUNDLE, repo=REPO, bundle_rel=BUNDLE_REL, provenance=stub,
                             expect_committed=True)
    if not verification["ok"]:
        print(json.dumps(verification, indent=2, ensure_ascii=False))
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    zip_path = os.path.join(OUT_DIR, ZIP_NAME)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    committed = bp.committed_files(REPO, BUNDLE_REL) + [bp.SUMS_NAME]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(committed):
            z.write(os.path.join(BUNDLE, rel), os.path.join(BUNDLE_REL, rel))
    prov = bp.build_provenance(bundle_dir=BUNDLE, repo=REPO, zip_path=zip_path,
                               runtime_code_sha=code_sha, verification=verification)
    prov["core_pin"] = manifest["core_pin"]
    prov["approved_inputs"] = manifest["approved_inputs"]
    prov["pair_readiness"] = manifest["pair_readiness"]
    prov_path = os.path.join(OUT_DIR, bp.PROVENANCE_NAME)
    json.dump(prov, open(prov_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False,
              sort_keys=True)
    ext = bp.write_external_sums(OUT_DIR, [prov_path, zip_path])
    final = bp.verify(BUNDLE, repo=REPO, bundle_rel=BUNDLE_REL, provenance=prov,
                      expect_committed=True)
    print(json.dumps({
        "runtime_code_sha": code_sha, "runtime_evidence_head_sha": head,
        "distinct": code_sha != head,
        "core_candidate_sha": manifest["core_candidate"]["sha"],
        "required_core_sha": manifest["core_pin"]["required_core_sha"],
        "zip": {"path": zip_path, "sha256": prov["zip"]["sha256"], "bytes": prov["zip"]["bytes"]},
        "provenance": prov_path, "external_sums": ext, "files_in_zip": len(committed),
        "verify_ok": final["ok"], "verify_problems": final["problems"],
        "pair_readiness": {k: manifest["pair_readiness"][k]
                           for k in ("core_runtime_pair_ready", "merge_authorized")},
    }, indent=2, ensure_ascii=False))
    return 0 if final["ok"] else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "manifest"
    sys.exit(cmd_manifest() if cmd == "manifest" else cmd_package())
