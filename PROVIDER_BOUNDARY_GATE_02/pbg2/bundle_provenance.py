"""CATENA DI PROVENANCE DEL BUNDLE — generatore e verificatore fail-closed.

Corregge il BLOCKER 1 della Human Review 01 di questa fase
(`EVIDENCE_CHAIN_AND_CORE_RUNTIME_PAIR_NOT_READY`).

IL DIFETTO. Nel package v1 `MANIFEST.json` era dentro lo ZIP ma NON era coperto da
`SHA256SUMS`, e il manifest dichiarava un generico `runtime_commit = e845b744…` mentre il
branch remoto puntava a `555e1f48…`. I due SHA sono legittimamente diversi — `555e1f48` e'
il commit che AGGIUNGE manifest e checksum — ma il nome `runtime_commit` non lo diceva, e
chiunque rilegga il package fra tre settimane deve poterlo capire senza fare archeologia
su Git.

LA CATENA, non self-referenziale
--------------------------------
Il problema di fondo e' che un manifest committato non puo' dichiarare lo SHA del commit
che lo contiene. La catena quindi si spezza in due livelli:

  1. COMMIT CODICE            `runtime_code_sha`
     Il diff funzionale del Runtime. E' cio' che la Human Review ha revisionato.

  2. COMMIT EVIDENCE          `runtime_evidence_head_sha`
     Aggiunge `MANIFEST.json` + `SHA256SUMS` (e i documenti del delta correttivo).
     `MANIFEST.json` dichiara `runtime_code_sha`, che conosce; NON dichiara
     `runtime_evidence_head_sha`, che non puo' conoscere. Lo dice esplicitamente con
     `runtime_evidence_head_sha: "DECLARED_IN_EXTERNAL_PROVENANCE"`.

  3. PROVENANCE ESTERNA       `PROVENANCE.json`, generata DOPO il commit evidence e MAI
     committata. E' l'unico posto in cui i due SHA compaiono insieme, insieme allo SHA256
     dello ZIP e a quelli di `MANIFEST.json` e `SHA256SUMS`.

  4. `SHA256SUMS.EXTERNAL`    copre `PROVENANCE.json` e lo ZIP.

`SHA256SUMS` (interno) copre OGNI file committato del bundle, **incluso `MANIFEST.json`**,
escluso soltanto se stesso. Gli artefatti esterni (3 e 4) non sono committati e non vi
compaiono.

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

MANIFEST_NAME = "MANIFEST.json"
SUMS_NAME = "SHA256SUMS"
PROVENANCE_NAME = "PROVENANCE.json"
EXTERNAL_SUMS_NAME = "SHA256SUMS.EXTERNAL"

# Chiavi che il manifest DEVE avere, con il significato disambiguato.
REQUIRED_MANIFEST_KEYS = ("runtime_code_sha", "runtime_evidence_head_sha", "runtime_branch",
                          "canonical_runtime_base_sha")
# Chiave ambigua bandita dalla Human Review: non deve piu' comparire.
FORBIDDEN_MANIFEST_KEYS = ("runtime_commit",)
EXTERNAL_ONLY = "DECLARED_IN_EXTERNAL_PROVENANCE"

# File presenti sul disco del bundle ma NON committati: non entrano in SHA256SUMS.
NEVER_COMMITTED = (PROVENANCE_NAME, EXTERNAL_SUMS_NAME)

# Forme di materiale credenziale che NON devono comparire in nessun file del bundle.
# Vivono qui, in un solo posto: il file che le dichiara e' l'unico escluso dalla scansione,
# altrimenti l'elenco troverebbe se stesso (esclusione dichiarata nell'evidenza di C11).
CREDENTIAL_PATTERNS = ("sk-", "api_key=", "apikey=", "Bearer ", "AKIA", "-----BEGIN ",
                       "HIGGSFIELD_API", "OPENAI_API")
CREDENTIAL_SCAN_SELF = "pbg2/bundle_provenance.py"
CREDENTIAL_SCAN_SKIP_EXT = (".zip", ".db", ".bin", ".sock")


def scan_credentials(bundle_dir: str) -> dict:
    """Cerca materiale credenziale in ogni file di testo del bundle. `hits` vuoto e' la
    condizione richiesta: nessuna credenziale letta, installata o trascritta in questa fase."""
    hits = []
    scanned = 0
    for root, dirs, names in os.walk(bundle_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in names:
            path = os.path.join(root, n)
            rel = os.path.relpath(path, bundle_dir)
            if rel == CREDENTIAL_SCAN_SELF or n.endswith(CREDENTIAL_SCAN_SKIP_EXT):
                continue
            try:
                body = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            scanned += 1
            found = [p for p in CREDENTIAL_PATTERNS if p in body]
            if found:
                hits.append({"file": rel, "patterns": found})
    # L'elenco letterale NON viene riferito nell'esito: finirebbe in un file di evidenza del
    # bundle e la scansione successiva troverebbe se stessa. Si riferisce il suo digest.
    fingerprint = hashlib.sha256("\n".join(CREDENTIAL_PATTERNS).encode("utf-8")).hexdigest()
    return {"patterns_sha256": fingerprint, "patterns_count": len(CREDENTIAL_PATTERNS),
            "patterns_declared_in": CREDENTIAL_SCAN_SELF,
            "files_scanned": scanned, "hits": hits,
            "self_reference_excluded": CREDENTIAL_SCAN_SELF,
            "extensions_skipped": list(CREDENTIAL_SCAN_SKIP_EXT)}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          check=True).stdout.strip()


# Percorsi che contengono il diff FUNZIONALE del Runtime. Il resto del repository e'
# evidenza, documentazione e strumenti del bundle. Il bytecode compilato non e' codice
# sorgente: escluderlo evita che un `.pyc` finito per sbaglio nell'indice sposti
# `runtime_code_sha` su un commit di sola evidenza.
RUNTIME_CODE_PATHS = ("RUNTIME_INTEGRATION_GATE_01/runtime", "RUNTIME_INTEGRATION_GATE_01/tests")
RUNTIME_CODE_EXCLUDE = (":(exclude)**/__pycache__/**", ":(exclude)**/*.pyc")


def runtime_code_sha(repo: str) -> str:
    """L'ultimo commit che tocca il codice funzionale del Runtime. Derivato da Git, mai
    scritto a mano: e' il valore che la Human Review ha revisionato."""
    sha = _git(repo, "log", "-1", "--format=%H", "--", *RUNTIME_CODE_PATHS, *RUNTIME_CODE_EXCLUDE)
    if not sha:
        raise RuntimeError("impossibile derivare runtime_code_sha")
    return sha


def runtime_code_unchanged_since(repo: str, code_sha: str) -> dict:
    """Il codice funzionale del Runtime non e' cambiato dopo `code_sha`, working tree incluso.
    E' la verifica che questo delta e' davvero reporting/evidence-only."""
    diff = subprocess.run(["git", "-C", repo, "diff", code_sha, "--", *RUNTIME_CODE_PATHS,
                           *RUNTIME_CODE_EXCLUDE], capture_output=True, text=True,
                          check=True).stdout
    return {"code_sha": code_sha, "paths": list(RUNTIME_CODE_PATHS),
            "excluded": list(RUNTIME_CODE_EXCLUDE),
            "diff_bytes": len(diff), "unchanged": diff == ""}


def disk_files(bundle_dir: str) -> list[str]:
    """File del bundle presenti sul disco, esclusi cache, checksum e artefatti esterni."""
    out = []
    for root, dirs, names in os.walk(bundle_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in names:
            rel = os.path.relpath(os.path.join(root, n), bundle_dir)
            if rel == SUMS_NAME or rel in NEVER_COMMITTED:
                continue
            out.append(rel)
    return sorted(out)


def committed_files(repo: str, bundle_rel: str) -> list[str]:
    """File del bundle realmente TRACCIATI da Git, relativi al bundle. Esclude `SHA256SUMS`
    (si copre da solo? no: e' l'unico file che non puo' coprirsi) e gli artefatti esterni."""
    listing = _git(repo, "ls-files", "--", bundle_rel).splitlines()
    out = []
    for p in listing:
        rel = os.path.relpath(p, bundle_rel)
        if rel == SUMS_NAME or rel in NEVER_COMMITTED:
            continue
        out.append(rel)
    return sorted(out)


# --------------------------------------------------------------------------- generazione
def write_sums(bundle_dir: str, files: list[str] | None = None) -> str:
    """Scrive `SHA256SUMS` su OGNI file del bundle escluso se stesso. Va chiamato per
    ULTIMO: qualunque scrittura successiva invalida i checksum."""
    files = disk_files(bundle_dir) if files is None else sorted(files)
    path = os.path.join(bundle_dir, SUMS_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        for rel in files:
            fh.write(f"{sha256_file(os.path.join(bundle_dir, rel))}  {rel}\n")
    return path


def read_sums(path: str) -> dict:
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            digest, _, rel = line.partition("  ")
            out[rel] = digest
    return out


def build_manifest(*, runtime_branch: str, runtime_code_sha: str, canonical_runtime_base_sha: str,
                   core_sha: str, core_branch_sha: str, core_branch_name: str,
                   core_branch_base: str, p2_sha256: str, required_core_sha: str,
                   readiness_report: dict, gap_status: dict, file_count: int) -> dict:
    """Manifest del bundle. NON dichiara lo SHA del commit che lo contiene: e' impossibile,
    e fingere di saperlo e' esattamente il difetto che questo delta corregge."""
    pr = readiness_report["phase_readiness"]
    ts = readiness_report["test_suite"]
    return {
        "schema": "provider-boundary-gate-open-gap-closure-manifest/2",
        "phase": "PROVIDER BOUNDARY GATE — OPEN-GAP CLOSURE / PRE-REAL-PROVIDER",
        "date": "2026-09-17",
        "corrective_delta": "HUMAN_REVIEW_01 — EVIDENCE_CHAIN_AND_CORE_RUNTIME_PAIR_NOT_READY "
                            "(reporting/evidence-only: nessuna modifica funzionale al Runtime)",
        "perimeter": "MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · "
                     "NO PRODUCTION · NO DEPLOY · NO TAG · NO RELEASE · NO MERGE",
        "canonical_baseline": {
            "core_repo": "Frantonaccio/creative-os",
            "core_branch": "main",
            "core_sha": core_sha,
            "runtime_repo": "Frantonaccio/esercitazioni",
            "canonical_runtime_base_sha": canonical_runtime_base_sha,
            "required_core_sha": required_core_sha,
            "p2_sha256": p2_sha256,
        },
        # --- i due SHA, disambiguati (BLOCKER 1) ---------------------------------------
        "runtime_branch": runtime_branch,
        "runtime_code_sha": runtime_code_sha,
        "runtime_code_sha_meaning":
            "commit che porta il diff FUNZIONALE del Runtime, quello revisionato dalla "
            "Human Review. Invariato da questo delta correttivo.",
        "runtime_evidence_head_sha": EXTERNAL_ONLY,
        "runtime_evidence_head_sha_meaning":
            "commit che aggiunge MANIFEST.json + SHA256SUMS (e i documenti del delta "
            "correttivo). Un manifest committato non puo' dichiarare lo SHA del commit che "
            "lo contiene: il valore vive in PROVENANCE.json, generata DOPO quel commit e "
            "mai committata, insieme a SHA256SUMS.EXTERNAL.",
        "canonical_runtime_base_sha": canonical_runtime_base_sha,
        # --- Core candidate --------------------------------------------------------------
        "core_candidate": {
            "repo": "Frantonaccio/creative-os",
            "branch": core_branch_name,
            "sha": core_branch_sha,
            "base": core_branch_base,
            "review_state": "APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED",
            "consumed_by_runtime_candidate": False,
        },
        # --- merge readiness (BLOCKER 2) -------------------------------------------------
        "merge_readiness": readiness_report["merge_readiness"],
        "test_suite": {k: ts[k] for k in ("total", "pass", "fail", "blocked",
                                          "all_tests_passed", "test_suite_decision")},
        "phase_readiness": {
            "all_requirements_verified": pr["all_requirements_verified"],
            "phase_gate_decision": pr["phase_gate_decision"],
            "max_state": pr["max_state"],
            "max_state_meaning": "stato di LAVORO con open gaps. NON e' un'autorizzazione al merge.",
            "open_requirements_blocking_all_verified": pr["open_requirements_blocking_all_verified"],
            "policy_decision_required": pr["policy_decision_required"],
            "real_provider_required": pr["real_provider_required"],
            "core_change_required": pr["core_change_required"],
        },
        "gap_status": gap_status,
        "files_covered_by_sha256sums": file_count,
        "sha256sums": SUMS_NAME,
        "sha256sums_scope": "ogni file committato del bundle, incluso MANIFEST.json, "
                            "escluso soltanto SHA256SUMS stesso",
        "external_provenance": {"file": PROVENANCE_NAME, "checksums": EXTERNAL_SUMS_NAME,
                                "committed": False},
        "not_implied": pr["not_implied"],
        "next": "Human Review separata. Nessun merge, nessun tag, nessun deploy, nessun R2.",
    }


def build_provenance(*, bundle_dir: str, repo: str, zip_path: str | None,
                     runtime_code_sha: str, verification: dict) -> dict:
    """PROVENANCE ESTERNA, generata DOPO il commit evidence. Non viene committata."""
    head = _git(repo, "rev-parse", "HEAD")
    manifest = json.load(open(os.path.join(bundle_dir, MANIFEST_NAME), encoding="utf-8"))
    prov = {
        "schema": "provider-boundary-gate-open-gap-closure-provenance/1",
        "generated_after_commit": head,
        "runtime_repo": "Frantonaccio/esercitazioni",
        "runtime_branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "runtime_code_sha": runtime_code_sha,
        "runtime_evidence_head_sha": head,
        "canonical_runtime_base_sha": manifest["canonical_runtime_base_sha"],
        "relationship": f"{runtime_code_sha} -> {head} "
                        f"(il secondo aggiunge MANIFEST.json + SHA256SUMS e i documenti del "
                        f"delta correttivo; il diff funzionale del Runtime sta nel primo)",
        "evidence_head_descends_from_code_sha": subprocess.run(
            ["git", "-C", repo, "merge-base", "--is-ancestor", runtime_code_sha, head]).returncode == 0,
        "core_candidate": manifest["core_candidate"],
        "merge_readiness": manifest["merge_readiness"],
        "artifacts": {
            MANIFEST_NAME: sha256_file(os.path.join(bundle_dir, MANIFEST_NAME)),
            SUMS_NAME: sha256_file(os.path.join(bundle_dir, SUMS_NAME)),
        },
        "bundle_verification": verification,
        "not_implied": manifest["not_implied"],
    }
    if zip_path and os.path.exists(zip_path):
        prov["zip"] = {"name": os.path.basename(zip_path), "sha256": sha256_file(zip_path),
                       "bytes": os.path.getsize(zip_path)}
    return prov


def write_external_sums(out_dir: str, files: list[str]) -> str:
    path = os.path.join(out_dir, EXTERNAL_SUMS_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        for p in files:
            fh.write(f"{sha256_file(p)}  {os.path.basename(p)}\n")
    return path


# --------------------------------------------------------------------------- verifica
def verify(bundle_dir: str, *, repo: str | None = None, bundle_rel: str | None = None,
           provenance: dict | None = None, expect_committed: bool = True) -> dict:
    """Verificatore FAIL-CLOSED della catena. Restituisce `problems` vuoto solo se tutto torna.

    Controlli richiesti dalla Human Review:
      1. un file committato del bundle NON presente in SHA256SUMS      -> MISSING_FROM_SUMS
      2. un checksum EXTRA, per un file che non esiste/non e' committato -> EXTRA_IN_SUMS
      3. un MISMATCH fra checksum dichiarato e file reale               -> CHECKSUM_MISMATCH
      4. `runtime_code_sha == runtime_evidence_head_sha` quando esiste
         il commit evidence successivo                                  -> CODE_SHA_EQUALS_EVIDENCE_HEAD
      5. HEAD del branch diverso da `runtime_evidence_head_sha`         -> HEAD_NOT_EVIDENCE_HEAD

    Piu' i controlli che rendono la catena non ambigua per costruzione:
      MANIFEST_NOT_COVERED, AMBIGUOUS_MANIFEST_KEY, MANIFEST_KEY_MISSING,
      EVIDENCE_HEAD_NOT_DESCENDANT, MERGE_READINESS_MISSING, MERGE_AUTHORIZED_WITHOUT_PAIR.
    """
    problems: list[dict] = []
    checks: dict = {}
    sums_path = os.path.join(bundle_dir, SUMS_NAME)
    manifest_path = os.path.join(bundle_dir, MANIFEST_NAME)

    if not os.path.exists(sums_path):
        problems.append({"code": "SUMS_MISSING", "detail": SUMS_NAME})
        return {"ok": False, "problems": problems, "checks": checks}
    if not os.path.exists(manifest_path):
        problems.append({"code": "MANIFEST_MISSING", "detail": MANIFEST_NAME})
        return {"ok": False, "problems": problems, "checks": checks}

    sums = read_sums(sums_path)
    if expect_committed and repo and bundle_rel:
        expected = committed_files(repo, bundle_rel)
        source = "git ls-files"
    else:
        expected = disk_files(bundle_dir)
        source = "disk"
    checks["file_set_source"] = source
    checks["expected_files"] = len(expected)
    checks["sums_entries"] = len(sums)

    # 1. copertura
    missing = sorted(set(expected) - set(sums))
    for rel in missing:
        problems.append({"code": "MISSING_FROM_SUMS", "detail": rel})
    # 4bis. il manifest DEVE essere coperto (esplicito, anche se implicato da 1)
    if MANIFEST_NAME not in sums:
        problems.append({"code": "MANIFEST_NOT_COVERED", "detail": MANIFEST_NAME})
    # 2. extra
    for rel in sorted(set(sums) - set(expected)):
        problems.append({"code": "EXTRA_IN_SUMS", "detail": rel})
    # SHA256SUMS non puo' coprire se stesso
    if SUMS_NAME in sums:
        problems.append({"code": "EXTRA_IN_SUMS", "detail": SUMS_NAME + " (si coprirebbe da solo)"})
    # 3. mismatch
    mismatches = []
    for rel, digest in sorted(sums.items()):
        full = os.path.join(bundle_dir, rel)
        if not os.path.exists(full):
            problems.append({"code": "EXTRA_IN_SUMS", "detail": f"{rel} (file assente)"})
            continue
        actual = sha256_file(full)
        if actual != digest:
            mismatches.append(rel)
            problems.append({"code": "CHECKSUM_MISMATCH", "detail": rel,
                             "declared": digest, "actual": actual})
    checks["missing_from_sums"] = missing
    checks["mismatches"] = mismatches

    # --- manifest: chiavi disambiguate ------------------------------------------------
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    for k in FORBIDDEN_MANIFEST_KEYS:
        if k in manifest:
            problems.append({"code": "AMBIGUOUS_MANIFEST_KEY", "detail": k})
    for k in REQUIRED_MANIFEST_KEYS:
        if not manifest.get(k):
            problems.append({"code": "MANIFEST_KEY_MISSING", "detail": k})
    checks["manifest_keys_ok"] = not [p for p in problems
                                      if p["code"] in ("AMBIGUOUS_MANIFEST_KEY", "MANIFEST_KEY_MISSING")]

    # --- merge readiness (BLOCKER 2) ---------------------------------------------------
    mr = manifest.get("merge_readiness")
    if not isinstance(mr, dict):
        problems.append({"code": "MERGE_READINESS_MISSING", "detail": "merge_readiness"})
    else:
        for k in ("runtime_candidate_ready", "core_candidate_ready", "core_runtime_pair_ready",
                  "merge_authorized"):
            if k not in mr:
                problems.append({"code": "MERGE_READINESS_MISSING", "detail": k})
        if mr.get("merge_authorized") and not mr.get("core_runtime_pair_ready"):
            problems.append({"code": "MERGE_AUTHORIZED_WITHOUT_PAIR",
                             "detail": "merge_authorized=true con core_runtime_pair_ready=false"})
    checks["merge_readiness"] = mr

    # --- i due SHA, e la loro relazione ------------------------------------------------
    code_sha = manifest.get("runtime_code_sha")
    declared_head = manifest.get("runtime_evidence_head_sha")
    if declared_head != EXTERNAL_ONLY and declared_head and code_sha and declared_head == code_sha:
        problems.append({"code": "CODE_SHA_EQUALS_EVIDENCE_HEAD", "detail": code_sha})
    checks["runtime_code_sha"] = code_sha
    checks["manifest_evidence_head_field"] = declared_head

    if provenance is not None:
        p_code = provenance.get("runtime_code_sha")
        p_head = provenance.get("runtime_evidence_head_sha")
        checks["provenance_runtime_code_sha"] = p_code
        checks["provenance_runtime_evidence_head_sha"] = p_head
        if p_code != code_sha:
            problems.append({"code": "PROVENANCE_CODE_SHA_MISMATCH",
                             "detail": f"manifest {code_sha} != provenance {p_code}"})
        # 4. i due SHA devono essere DIVERSI quando esiste il commit evidence
        if p_code and p_head and p_code == p_head:
            problems.append({"code": "CODE_SHA_EQUALS_EVIDENCE_HEAD", "detail": p_head})
        if repo and p_head:
            head = _git(repo, "rev-parse", "HEAD")
            checks["git_head"] = head
            # 5. HEAD del branch deve coincidere con l'evidence head dichiarato
            if head != p_head:
                problems.append({"code": "HEAD_NOT_EVIDENCE_HEAD",
                                 "detail": f"git HEAD {head} != provenance {p_head}"})
            if p_code:
                ok = subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor",
                                     p_code, p_head]).returncode == 0
                checks["evidence_head_descends_from_code_sha"] = ok
                if not ok:
                    problems.append({"code": "EVIDENCE_HEAD_NOT_DESCENDANT",
                                     "detail": f"{p_code} non e' antenato di {p_head}"})

    return {"ok": not problems, "problems": problems, "checks": checks}
