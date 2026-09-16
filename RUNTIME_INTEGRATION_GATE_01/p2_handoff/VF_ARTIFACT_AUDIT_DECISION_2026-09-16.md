# ValoreFarmacia Creative OS — Artifact Audit Decision

Date: 2026-09-16
Source package: `VF_RUNTIME_ARTIFACT_CONSOLIDATION_2026-09-16.zip`
Source ZIP SHA256: `8e5fb8e9fe6e401647730a7a12f5e327a3488e66e5a951d295eb64d0008f118a`

## Executive verdict

Nothing critical was lost. The main failure was not disappearance of the runtime but **lack of a canonical home** for the production runtime and its integration artifacts.

The historical P2 runtime exists intact:

`VF_PILOT_OUTPUTS/P2_PRIMA_SI_PARLA/RUN_20260915_FINAL_PRODUCTION/scripts/hf_batch.py`

SHA256:
`637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1`

The same full hash is confirmed by multiple independent local evidence files and by the byte-identical lab backup `hf_batch_ORIGINAL.py`.

The ZIP integrity was independently verified: 1,190 files covered by `SHA256SUMS`, 0 missing, 0 mismatches, 0 uncovered. No `.git`, `.env`, Higgsfield credentials, private-key filenames, `node_modules`, or `__pycache__` are present.

## Critical architecture finding

The P2 production `hf_batch.py` **recorded and fingerprinted Core state but did not execute Core control primitives** for spending/idempotency. Its lock explicitly stated Core role in generation as `nessuno per la generazione`. The actual provider path was direct:

`hf_batch.py -> subprocess higgsfield generate create -> wait -> result_url -> urlretrieve`

The final production runtime locks show Core:
`9afaddf3cec1e8baf9600ed8dc0461e7adccb5c7`, CLEAN.

This explains why the later C26 work was necessary. The current canonical Core is now `819e7cfedb0f6641dc797e7993bec79462ac8df6`, but the historical P2 run must remain historical evidence and must not be rewritten retroactively.

## Definitive classification

### CANONICAL NOW

1. **Core repository**
   - GitHub: `Frantonaccio/creative-os`
   - canonical branch: `main`
   - canonical SHA: `819e7cfedb0f6641dc797e7993bec79462ac8df6`
   - role: contracts, state machine, atomic reservation, idempotency, generic control primitives.

2. **ValoreFarmacia tenant repository**
   - GitHub: `Frantonaccio/vf-tenant-valorefarmacia`
   - current local branch observed: `fix/performance-first-creative-gate`
   - HEAD: `5bb3cf2cb5c9d5227c195a376a7d6c29cd5091be`
   - local dirty file: `LEARNINGS/HUMAN_GATE_EVENTS.jsonl`
   - role: brand, claims, cast, creative policy, learnings, Human Gate evidence.
   - warning: repository is canonical by role, but the observed working tree is not a clean canonical snapshot until the append-only event delta is reconciled.

3. **Future runtime canonical candidate**
   - NOT the old P2 `hf_batch.py`.
   - basis: the current Runtime Integration Gate branch created after C26, which delegates reservation/idempotency to Core.
   - this should become a dedicated runtime repository after T16 and review.

### HISTORICAL PRODUCTION / EVIDENCE

1. `P2_RUNTIME/.../hf_batch.py`
   - role: exact historical production runner for P2.
   - immutable evidence.
   - do not promote as future runtime.

2. `RUN_20260915_FINAL_PRODUCTION/` manifests, traces, locks, QA, edit metadata, specs.
   - immutable chain-of-custody evidence.

3. `RULESET_LOCK_RECONSTRUCTED.json`
   - retrospective evidence only, not proof of a preventive lock for the earlier run.

4. Human Gate and checkpoint evidence:
   - `HUMAN_GATE_EVENTS.jsonl`
   - `CHECKPOINT_STATUS_INDEX.json`
   - final QA/trace/lock files.

5. Core PR review packages and Runtime Hardening evidence.

### LAB / ARCHIVE ONLY

1. `INTEGRATION_GATE_01/lab/hf_batch_lab.py`
   - old mock extension.
   - added a `lab` verb to historical `hf_batch.py`.
   - do not promote.

2. `INTEGRATION_GATE_01/lab/gate01_lab.py`
   - real file, not imaginary.
   - contains a parallel `DurableJobStore`, reservation logic, state vocabulary and old Core pin `9afaddf...`.
   - this architecture is superseded by C26 and must remain archive/evidence only.

3. `VF_CORE_CANDIDATES/creative-os_7ea87fd`
   - historical Core candidate, detached.
   - retain as historical evidence until any still-relevant visual narrative changes are separately reconciled.

4. Production Control Pack original `_cowork_inbox` copy.
   - preserve as original package evidence.

5. Production Control Pack `candidate_fixed` copy.
   - preserve separately as a corrected lab candidate.
   - differences are meaningful: Python 3.9 guard and prevention of direct `test_control.py` false-green.

### RUNTIME TO BUILD / PROMOTE

Create one dedicated canonical runtime repository, recommended name:

`Frantonaccio/vf-runtime-valorefarmacia`

It should contain only production orchestration and runtime integration, not media or tenant policy duplication.

Suggested responsibilities:
- Core pin + clean-tree gate
- real `hf_batch go -> GenSpec` binding
- Core `ReservationStore` integration
- provider adapter boundary
- quote / submit / reconcile orchestration
- production budget ledger integration
- exact-byte snapshot boundary
- QA asset-hash binding
- authenticated Human Gate references

It must import/use Core rather than copy Core state machines.

### DRIVE / ASSET STORE

Keep outside GitHub:
- video/audio/stills
- large references
- final production exports
- evidence ZIPs
- heavy run artifacts

GitHub should hold manifests, hashes, metadata and code, not duplicate media payloads.

### DELETE-LATER CANDIDATES

Do not delete now. After canonical repos and Drive archives are verified:

- `hf_batch_ORIGINAL.py` byte-identical backup, after historical runtime archive is confirmed.
- prunable `RUNTIME_HARDENING_GATE/core_wt` worktree after all unique evidence is retained.
- superseded workspaces such as `VF_REPO_WORKSPACE_V5_SUPERSEDED`, V6 and case-collision invalid copies, after deduplication against Git history and evidence manifests.
- duplicate local Control Pack copies only after preserving both original and corrected candidate states.

`VF_CREATIVE_OS` should not be silently repurposed as the new runtime repo. It is an older, separate P1/ingest repository with no remote and multiple untracked artifacts. Freeze/archive it first.

## Corrections to earlier assumptions

- `gate01_lab.py` **does exist**. Earlier uncertainty about its existence was wrong.
- `hf_batch.py` was not missing. It was outside the canonical GitHub repositories.
- the full historical P2 runtime hash is now verified, not merely a prefix.
- the control pack has two distinct versions and must not be collapsed by filename alone.

## Next operational gate

Use `VF_RUNTIME_T16_HANDOFF_2026-09-16.zip` to resume the existing Runtime Integration Gate branch.

Required outcome:
1. derive the real mapping from historical `hf_batch.py` and real P2 `spec*.json` to Core `GenSpec`;
2. close T16 by proving the source P2 runtime bytes/hash;
3. preserve old lab files as evidence only;
4. do not import old `gate01_lab.py` reservation logic into the new runtime;
5. keep real provider disabled;
6. stop at `READY_FOR_RUNTIME_INTEGRATION_REVIEW`.

Only after that should a new canonical runtime repository be created/published.
