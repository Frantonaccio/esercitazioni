# VF Runtime T16 Handoff — 2026-09-16

Read-only evidence package extracted from `VF_RUNTIME_ARTIFACT_CONSOLIDATION_2026-09-16.zip`.

Purpose: close P2-ABSENT / T16 in the remote Runtime Integration Gate without inventing provenance.

## Authoritative historical P2 runtime
- `P2_RUNTIME/hf_batch.py`
- SHA256: `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1`
- This is byte-identical to `LAB/hf_batch_ORIGINAL.py`.
- It is historical production evidence, NOT the future canonical runtime implementation.

## Lab-only artifacts
- `LAB/hf_batch_lab.py`
- `LAB/gate01_lab.py`
- These reimplemented reservation/state logic in the old integration lab and MUST NOT be promoted as future runtime architecture.

## Control Pack
Two distinct versions are preserved:
- `CONTROL_PACK_ORIGINAL/`: original `_cowork_inbox` Production Control Pack.
- `CONTROL_PACK_CANDIDATE_FIXED/`: lab candidate with Python 3.9 minimum guard and direct `test_control.py` false-green fix.

Do not silently overwrite one with the other.

## Specs
All top-level `spec*.json` files from the final P2 production run are included so the real `hf_batch.py -> GenSpec` mapping can be derived from actual inputs.

## Evidence
Includes final P2 SHA manifest, runtime lock, old integration initial state, and diffs.

No credentials, `.env`, `.git`, provider secrets, media binaries, or caches are included.
