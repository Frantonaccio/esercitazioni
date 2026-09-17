#!/usr/bin/env python3
"""Confeziona il bundle in DUE passi, perche' la catena non sia self-referenziale.

    python3 pbg2/make_bundle.py manifest     # PRIMA del commit evidence
    <git add -A && git commit>               # -> runtime_evidence_head_sha
    python3 pbg2/make_bundle.py package      # DOPO il commit evidence

`manifest` scrive `MANIFEST.json` e poi `SHA256SUMS` (per ultimo, su ogni file del bundle
incluso il manifest, escluso soltanto se stesso). Entrambi entrano nel commit evidence.

`package` verifica la catena contro i file realmente COMMITTATI, costruisce lo ZIP, e
genera fuori dal repository `PROVENANCE.json` e `SHA256SUMS.EXTERNAL`. Sono gli unici
artefatti che conoscono `runtime_evidence_head_sha`, ed e' per questo che non sono
committati: un file committato non puo' dichiarare lo SHA del commit che lo contiene.

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BUNDLE)
BUNDLE_REL = os.path.basename(BUNDLE)
CORE = os.environ.get("CREATIVE_OS_CORE_PATH", "/home/user/creative-os")
CORE_BRANCH_PATH = os.environ.get("CREATIVE_OS_CORE_BRANCH_PATH", "/home/user/creative-os-atomicity")
GATE01 = os.path.join(REPO, "RUNTIME_INTEGRATION_GATE_01")
P2 = os.path.join(GATE01, "p2_handoff", "VF_RUNTIME_T16_HANDOFF_2026-09-16", "P2_RUNTIME",
                  "hf_batch.py")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"     # nessun .pyc finisce nel bundle committato
OUT_DIR = os.environ.get("PBG2_PACKAGE_OUT",
                         "/tmp/claude-0/-home-user-esercitazioni/"
                         "48f94f47-e448-5466-9811-f92e1498b0cd/scratchpad")
ZIP_NAME = "VF_PROVIDER_BOUNDARY_GATE_OPEN_GAP_CLOSURE_EVIDENCE_2026-09-17_v2.zip"
CANONICAL_RUNTIME_BASE = "0698279703ab959625ac4e84ee636bc5b93b45fd"
CANONICAL_CORE = "740ee979300fe20a9382992528604dee70cb2fcf"

for p in (GATE01, BUNDLE, REPO):
    if p not in sys.path:
        sys.path.insert(0, p)
from pbg2 import bundle_provenance as bp                         # noqa: E402
from runtime.core_pin import REQUIRED_CORE_SHA                   # noqa: E402


def git(*a, cwd=REPO) -> str:
    return subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True,
                          check=True).stdout.strip()


def runtime_code_sha() -> str:
    """Il commit che porta il diff FUNZIONALE del Runtime. Derivato da Git (unica sede:
    `bundle_provenance.runtime_code_sha`), mai scritto a mano."""
    return bp.runtime_code_sha(REPO)


def cmd_manifest() -> int:
    readiness_path = os.path.join(BUNDLE, "READINESS.json")
    if not os.path.exists(readiness_path):
        raise SystemExit("READINESS.json assente: eseguire prima pbg2/run_gate2.py")
    rd = json.load(open(readiness_path, encoding="utf-8"))
    report = rd["report"]
    code_sha = runtime_code_sha()

    manifest = bp.build_manifest(
        runtime_branch=git("rev-parse", "--abbrev-ref", "HEAD"),
        runtime_code_sha=code_sha,
        canonical_runtime_base_sha=CANONICAL_RUNTIME_BASE,
        core_sha=git("rev-parse", "HEAD", cwd=CORE),
        core_branch_sha=git("rev-parse", "HEAD", cwd=CORE_BRANCH_PATH),
        core_branch_name=git("rev-parse", "--abbrev-ref", "HEAD", cwd=CORE_BRANCH_PATH),
        core_branch_base=git("rev-parse", "HEAD~1", cwd=CORE_BRANCH_PATH),
        p2_sha256=bp.sha256_file(P2),
        required_core_sha=REQUIRED_CORE_SHA,
        readiness_report=report,
        gap_status=rd["gap_status"],
        file_count=0)
    # il conteggio si conosce solo dopo aver scritto il manifest: si scrive due volte, la
    # seconda con il numero giusto, e SOLO DOPO si calcolano i checksum.
    with open(os.path.join(BUNDLE, bp.MANIFEST_NAME), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False, sort_keys=True)
    files = bp.disk_files(BUNDLE)
    manifest["files_covered_by_sha256sums"] = len(files)
    with open(os.path.join(BUNDLE, bp.MANIFEST_NAME), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False, sort_keys=True)
    bp.write_sums(BUNDLE, files)

    check = bp.verify(BUNDLE, expect_committed=False)
    print(json.dumps({"runtime_code_sha": code_sha,
                      "runtime_evidence_head_sha": manifest["runtime_evidence_head_sha"],
                      "files_covered": len(files),
                      "manifest_covered": bp.MANIFEST_NAME in bp.read_sums(
                          os.path.join(BUNDLE, bp.SUMS_NAME)),
                      "verify_problems": check["problems"],
                      "merge_readiness": manifest["merge_readiness"]},
                     indent=2, ensure_ascii=False))
    return 0 if check["ok"] else 1


def cmd_package() -> int:
    manifest = json.load(open(os.path.join(BUNDLE, bp.MANIFEST_NAME), encoding="utf-8"))
    code_sha = manifest["runtime_code_sha"]
    head = git("rev-parse", "HEAD")
    if head == code_sha:
        raise SystemExit("il commit evidence non esiste ancora: HEAD == runtime_code_sha")

    # 1. verifica la catena contro i file REALMENTE committati
    provenance_stub = {"runtime_code_sha": code_sha, "runtime_evidence_head_sha": head}
    verification = bp.verify(BUNDLE, repo=REPO, bundle_rel=BUNDLE_REL,
                             provenance=provenance_stub, expect_committed=True)
    if not verification["ok"]:
        print(json.dumps(verification, indent=2, ensure_ascii=False))
        return 1

    # 2. ZIP dei soli file committati del bundle
    os.makedirs(OUT_DIR, exist_ok=True)
    zip_path = os.path.join(OUT_DIR, ZIP_NAME)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    committed = bp.committed_files(REPO, BUNDLE_REL) + [bp.SUMS_NAME]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(committed):
            z.write(os.path.join(BUNDLE, rel), os.path.join(BUNDLE_REL, rel))

    # 3. PROVENANCE esterna + checksum esterni
    prov = bp.build_provenance(bundle_dir=BUNDLE, repo=REPO, zip_path=zip_path,
                               runtime_code_sha=code_sha, verification=verification)
    prov_path = os.path.join(OUT_DIR, bp.PROVENANCE_NAME)
    with open(prov_path, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, indent=2, ensure_ascii=False, sort_keys=True)
    ext_path = bp.write_external_sums(OUT_DIR, [prov_path, zip_path])

    # 4. ri-verifica con la provenance REALE (chiude i controlli 4 e 5)
    final = bp.verify(BUNDLE, repo=REPO, bundle_rel=BUNDLE_REL, provenance=prov,
                      expect_committed=True)
    print(json.dumps({
        "runtime_code_sha": code_sha,
        "runtime_evidence_head_sha": head,
        "distinct": code_sha != head,
        "zip": {"path": zip_path, "sha256": prov["zip"]["sha256"], "bytes": prov["zip"]["bytes"]},
        "provenance": prov_path, "external_sums": ext_path,
        "files_in_zip": len(committed),
        "verify_ok": final["ok"], "verify_problems": final["problems"],
        "merge_readiness": manifest["merge_readiness"],
    }, indent=2, ensure_ascii=False))
    return 0 if final["ok"] else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "manifest"
    sys.exit(cmd_manifest() if cmd == "manifest" else cmd_package())
