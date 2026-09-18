#!/usr/bin/env python3
"""Confezionamento del bundle, in DUE passi — e i due passi non sono un capriccio.

    python3 lspc1/make_bundle.py manifest     # PRIMA del commit dell'evidenza
    <git add -A && git commit>                # -> evidence_head_sha
    python3 lspc1/make_bundle.py package      # DOPO il commit dell'evidenza

Un bundle non puo' contenere lo SHA del commit che lo contiene: e' un cane che si
morde la coda, e fingere di saperlo e' esattamente il difetto che le review
precedenti hanno corretto. Percio' `MANIFEST.json` dichiara
`DECLARED_IN_EXTERNAL_PROVENANCE`, e lo SHA vero vive in `PROVENANCE.json`, che sta
FUORI dal commit.

Riusa l'authority di provenance gia' approvata
(`PROVIDER_BOUNDARY_GATE_02/pbg2/bundle_provenance.py`) per le primitive: stessa
catena non self-referenziale, stessa scansione di materiale credenziale, stesso
divieto della chiave ambigua `runtime_commit`.

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
GATE01 = os.path.join(REPO, "RUNTIME_INTEGRATION_GATE_01")
GATE02 = os.path.join(REPO, "PROVIDER_BOUNDARY_GATE_02")
CORE = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")
P2 = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "P2_RUNTIME",
                  "hf_batch.py")
OUT_DIR = os.environ.get("LSPC1_PACKAGE_OUT", os.path.join(REPO, "..", "lspc1_package"))
ZIP_NAME = "VF_LEGACY_SPEND_PATH_CLOSURE_EVIDENCE_V2_2026-09-18.zip"

CANONICAL_CORE_BASE = "9cf9cee1a751f7a2ad6c768574ff5aa38d8db515"
CANONICAL_RUNTIME_BASE = "fea7b439a63a0100a732e21af4dfde6b8edd0951"
P2_DECLARED = "637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1"

# Iterazione 1, sottoposta a Human Review e NON mergiata. Resta dichiarata: un bundle
# v2 che non dicesse da dove viene sarebbe un bundle senza storia.
REVIEWED_CORE_SHA = "44f9ea29cea112dfb30c752e5519498e25044c19"
REVIEWED_RUNTIME_CODE_SHA = "ad2f9c072b2a775637eb0b0da0aeca1cb82ca770"
REVIEWED_RUNTIME_EVIDENCE_HEAD = "108af8a606d81ef1b09191fda062d684befd54ec"
REVIEWED_ZIP_SHA256 = "c0f497c08e201b2f14679cb81c80ce820ee6a5fc8927964c231077ea35073d34"

for p in (GATE01, GATE02, BUNDLE, REPO):
    if p not in sys.path:
        sys.path.insert(0, p)
from pbg2 import bundle_provenance as bp                          # noqa: E402
from runtime.core_pin import REQUIRED_CORE_SHA                    # noqa: E402


def git(*a, cwd=REPO) -> str:
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True,
                          check=True).stdout.strip()


def _load(rel: str) -> dict:
    with open(os.path.join(BUNDLE, rel), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------- manifest
def build_manifest(file_count: int) -> dict:
    readiness = _load("READINESS.json")
    results = _load(os.path.join("evidence", "RESULTS.json"))["summary"]
    return {
        "schema": "legacy-spend-path-closure-manifest/1",
        "phase": "LEGACY SPEND PATH CLOSURE + LEGACY TEST MIGRATION",
        "date": "2026-09-18",
        "mode": "MOCK ONLY · ZERO PROVIDER REALI · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUZIONE",

        # --- catena di evidenza: quattro cose diverse, quattro nomi diversi ---
        "canonical_base": {"core_main": CANONICAL_CORE_BASE,
                           "runtime_main": CANONICAL_RUNTIME_BASE},
        "core_repo": "Frantonaccio/creative-os",
        "core_branch": git("rev-parse", "--abbrev-ref", "HEAD", cwd=CORE),
        "core_code_sha": git("rev-parse", "HEAD", cwd=CORE),
        "runtime_repo": "Frantonaccio/esercitazioni",
        "runtime_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "runtime_code_sha": bp.runtime_code_sha(REPO),
        "runtime_evidence_head_sha": bp.EXTERNAL_ONLY,
        "canonical_runtime_base_sha": CANONICAL_RUNTIME_BASE,
        "branch_note": ("il mandato indicava `harden/legacy-spend-runtime-2026-09-18`; il "
                        "classifier della sessione impone il branch reale sopra e vieta di "
                        "pubblicare altrove. Riportato come richiesto da §15."),

        "core_pin": {"required_core_sha": REQUIRED_CORE_SHA,
                     "points_to_core_candidate": REQUIRED_CORE_SHA == git("rev-parse", "HEAD",
                                                                          cwd=CORE),
                     "previous_canonical_now_stale": CANONICAL_CORE_BASE},
        "p2_frozen": {"declared": P2_DECLARED, "observed": bp.sha256_file(P2),
                      "path": os.path.relpath(P2, REPO)},

        "test_suite_result": readiness["test_suite_result"],
        "requirement_readiness": readiness["requirement_readiness"],
        "phase_state": readiness["phase_state"],
        "explicitly_not_claimed": readiness["explicitly_not_claimed"],
        "gate": {"steps": results["total"], "pass": results["pass"], "fail": results["fail"],
                 "fail_ids": results["fail_ids"], "decision": results["gate_decision"]},
        "human_review_01": {
            "verdict_received": "HUMAN_REVIEW_HOLD — DISPATCH_AUTHORIZATION_FORGEABLE",
            "reviewed_iteration": {
                "core_sha": REVIEWED_CORE_SHA,
                "runtime_code_sha": REVIEWED_RUNTIME_CODE_SHA,
                "runtime_evidence_head_sha": REVIEWED_RUNTIME_EVIDENCE_HEAD,
                "zip_sha256": REVIEWED_ZIP_SHA256,
                "merged": False},
            "blocker": ("`DispatchAuthorization` era costruibile e `grant_dispatch(adapter, "
                        "auth)` accettava l'oggetto senza rileggere il journal; `_dispatch` e "
                        "`_authorize_payload` erano invocabili direttamente."),
            "reproduced_on_reviewed_candidate": True,
            "evidence": ["evidence/E13_forged_dispatch_authorization.json",
                         "evidence/E14_threat_model.json",
                         "HUMAN_REVIEW_01_CORRECTIVE_DELTA.md", "THREAT_MODEL.md"],
            "resolution": ("grant_dispatch riceve lo store e rilegge il journal; costruttore "
                           "con token di conio; registro dei coniati per identita' a consumo "
                           "singolo; guard automatico sugli hook."),
            "history_preserved": "nessun amend, nessun force-push: delta correttivi come "
                                 "commit nuovi sugli stessi branch",
            "snapshot_seal_write_race": {
                "status": "STILL_OPEN",
                "human_review_classification": ["PREEXISTING", "FAIL_CLOSED",
                                                "AVAILABILITY / CONCURRENCY DEFECT",
                                                "NO DOUBLE SPEND OBSERVED"],
                "fixed_here": False,
                "next": "candidato del gate successivo, dopo il merge di questa fase"},
        },
        "file_count": file_count,
        "credential_scan": bp.scan_credentials(BUNDLE),
    }


def step_manifest() -> int:
    manifest = build_manifest(file_count=0)
    # Idempotente: il manifest si conta UNA volta, che esista gia' o no.
    files = [f for f in bp.disk_files(BUNDLE) if f != bp.MANIFEST_NAME]
    manifest["file_count"] = len(files) + 1          # + MANIFEST.json stesso
    with open(os.path.join(BUNDLE, bp.MANIFEST_NAME), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False, sort_keys=True)
    for k in bp.FORBIDDEN_MANIFEST_KEYS:
        assert k not in manifest, f"chiave ambigua vietata nel manifest: {k}"
    for k in bp.REQUIRED_MANIFEST_KEYS:
        assert k in manifest, f"chiave obbligatoria mancante nel manifest: {k}"
    # SHA256SUMS per ULTIMO: copre MANIFEST.json e ogni altro file, mai se stesso.
    sums = bp.write_sums(BUNDLE)
    print(f"MANIFEST.json  file_count={manifest['file_count']}")
    print(f"SHA256SUMS     {len(bp.read_sums(sums))} voci")
    hits = manifest["credential_scan"]["hits"]
    print(f"scansione credenziali: {manifest['credential_scan']['files_scanned']} file, "
          f"{len(hits)} riscontri {hits if hits else ''}")
    print("ORA: git add -A && git commit  ->  poi `package`")
    return 0 if not hits else 1


# ------------------------------------------------------------------- provenance
def verify_chain() -> dict:
    """Verifica fail-closed PRIMA di dichiarare qualunque cosa."""
    head = git("rev-parse", "HEAD")
    manifest = _load(bp.MANIFEST_NAME)
    sums = bp.read_sums(os.path.join(BUNDLE, bp.SUMS_NAME))
    committed = bp.committed_files(REPO, BUNDLE_REL)
    missing = [f for f in committed if f not in sums]
    mismatches = [f for f in committed
                  if f in sums and sums[f] != bp.sha256_file(os.path.join(BUNDLE, f))]
    code_sha = manifest["runtime_code_sha"]
    descends = subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", code_sha, head]
                              ).returncode == 0
    problems = []
    if missing:
        problems.append(f"file committati non coperti da SHA256SUMS: {missing}")
    if mismatches:
        problems.append(f"checksum non corrispondenti: {mismatches}")
    if not descends:
        problems.append(f"evidence head {head[:12]} non discende da code sha {code_sha[:12]}")
    if manifest["runtime_evidence_head_sha"] != bp.EXTERNAL_ONLY:
        problems.append("il manifest dichiara un evidence head: deve stare nella provenance esterna")
    if bp.sha256_file(P2) != P2_DECLARED:
        problems.append("P2 congelato modificato")
    return {"ok": not problems, "problems": problems,
            "checks": {"git_head": head, "runtime_code_sha": code_sha,
                       "evidence_head_descends_from_code_sha": descends,
                       "sums_entries": len(sums), "expected_files": len(committed),
                       "file_set_source": "git ls-files", "missing_from_sums": missing,
                       "mismatches": mismatches,
                       "manifest_evidence_head_field": manifest["runtime_evidence_head_sha"]}}


def step_package() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    verification = verify_chain()
    head = git("rev-parse", "HEAD")
    manifest = _load(bp.MANIFEST_NAME)
    readiness = _load("READINESS.json")

    zip_path = os.path.join(OUT_DIR, ZIP_NAME)
    files = bp.committed_files(REPO, BUNDLE_REL) + [bp.SUMS_NAME]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(set(files)):
            z.write(os.path.join(BUNDLE, rel), arcname=os.path.join(BUNDLE_REL, rel))
    zip_sha = bp.sha256_file(zip_path)

    provenance = {
        "schema": "legacy-spend-path-closure-provenance/1",
        "phase": "LEGACY SPEND PATH CLOSURE + LEGACY TEST MIGRATION",
        "generated_after_commit": head,
        "canonical_base": {"core_main": CANONICAL_CORE_BASE,
                           "runtime_main": CANONICAL_RUNTIME_BASE},
        "core": {"repo": "Frantonaccio/creative-os",
                 "branch": manifest["core_branch"], "code_sha": manifest["core_code_sha"],
                 "descends_from_canonical_base": subprocess.run(
                     ["git", "-C", CORE, "merge-base", "--is-ancestor", CANONICAL_CORE_BASE,
                      manifest["core_code_sha"]]).returncode == 0,
                 "review_state": "CANDIDATE — NOT_MERGE_AUTHORIZED"},
        "runtime": {"repo": "Frantonaccio/esercitazioni",
                    "branch": manifest["runtime_branch"],
                    "code_sha": manifest["runtime_code_sha"],
                    "evidence_head_sha": head,
                    "branch_note": manifest["branch_note"],
                    "review_state": "CANDIDATE — NOT_MERGE_AUTHORIZED"},
        "relationship": (f"{manifest['runtime_code_sha'][:12]} -> {head[:12]}: il primo porta il "
                         f"diff funzionale del Runtime, il secondo aggiunge evidenza, documenti, "
                         f"MANIFEST.json e SHA256SUMS. Non sono lo stesso SHA e non vanno "
                         f"chiamati con lo stesso nome."),
        "core_pin": manifest["core_pin"],
        "p2_frozen": manifest["p2_frozen"],
        "human_review_01": manifest["human_review_01"],
        "phase_state": readiness["phase_state"],
        "test_suite_result": readiness["test_suite_result"],
        "requirement_readiness": readiness["requirement_readiness"],
        "explicitly_not_claimed": readiness["explicitly_not_claimed"],
        "bundle_verification": verification,
        "artifacts": {bp.MANIFEST_NAME: bp.sha256_file(os.path.join(BUNDLE, bp.MANIFEST_NAME)),
                      bp.SUMS_NAME: bp.sha256_file(os.path.join(BUNDLE, bp.SUMS_NAME))},
        "zip": {"name": ZIP_NAME, "sha256": zip_sha, "bytes": os.path.getsize(zip_path)},
        "not_implied": ["provider reale verificato", "provider ready", "production ready",
                        "credenziali autorizzate", "spend autorizzato", "merge autorizzato",
                        "R2 autorizzato", "NG-04 policy decisa", "orphan lease policy decisa",
                        "chiusura degli altri open requirements"],
        "human_merge_authorization": False,
        "merge_authorized": False,
    }
    prov_path = os.path.join(OUT_DIR, bp.PROVENANCE_NAME)
    with open(prov_path, "w", encoding="utf-8") as fh:
        json.dump(provenance, fh, indent=2, ensure_ascii=False, sort_keys=True)

    ext_path = os.path.join(OUT_DIR, bp.EXTERNAL_SUMS_NAME)
    with open(ext_path, "w", encoding="utf-8") as fh:
        for name in (ZIP_NAME, bp.PROVENANCE_NAME):
            fh.write(f"{bp.sha256_file(os.path.join(OUT_DIR, name))}  {name}\n")

    print(f"verifica catena: {'OK' if verification['ok'] else verification['problems']}")
    print(f"ZIP            {zip_path}")
    print(f"SHA256 ESTERNO {zip_sha}")
    print(f"PROVENANCE     {prov_path}")
    print(f"EXTERNAL SUMS  {ext_path}")
    return 0 if verification["ok"] else 1


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "manifest"
    sys.exit({"manifest": step_manifest, "package": step_package}[step]())
