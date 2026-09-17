# PROVIDER BOUNDARY GATE — OPEN-GAP CLOSURE / PRE-REAL-PROVIDER (2026-09-17)

MOCK ONLY · **ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION · NO DEPLOY · NO TAG · NO RELEASE · NO MERGE**

> **Package v2** — incorpora il delta correttivo della Human Review 01
> (`HUMAN_REVIEW_HOLD — EVIDENCE_CHAIN_AND_CORE_RUNTIME_PAIR_NOT_READY`).
> Reporting/evidence-only: il diff funzionale del Runtime è invariato (0 righe), il Core
> candidate è invariato, nessun merge è stato eseguito.
> Dettaglio: `HUMAN_REVIEW_01_CORRECTIVE_DELTA.md`.

Fase precedente, chiusa e mergiata:
`PROVIDER_EXECUTION_BOUNDARY_HARDENING_MERGED — LAB_BASELINE_CANONICAL_WITH_OPEN_GAPS`.
Il bundle v3 (`PROVIDER_BOUNDARY_HARDENING_01/`) **non è stato modificato**.

## Baseline canonica

| | |
|---|---|
| CORE `Frantonaccio/creative-os` `main` | `740ee979300fe20a9382992528604dee70cb2fcf` |
| RUNTIME `Frantonaccio/esercitazioni` `origin/main` | `0698279703ab959625ac4e84ee636bc5b93b45fd` |
| Runtime pin `REQUIRED_CORE_SHA` | `740ee979300fe20a9382992528604dee70cb2fcf` |
| P2 frozen `hf_batch.py` | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` |

Verificata prima di ogni write e a fine fase: `REALITY_LOCK.md`. Nessun `CANONICAL_BASELINE_DRIFT`.

## Come rieseguire

```bash
# PHASE A — riproduzioni pre-fix (non correggono nulla)
python3 PROVIDER_BOUNDARY_GATE_02/pbg2/reproduce.py

# GATE C00..C11
python3 PROVIDER_BOUNDARY_GATE_02/pbg2/run_gate2.py

# CONFEZIONAMENTO in due passi (catena non self-referenziale)
python3 PROVIDER_BOUNDARY_GATE_02/pbg2/make_bundle.py manifest   # MANIFEST.json, poi SHA256SUMS
git add -A && git commit                                          # -> runtime_evidence_head_sha
python3 PROVIDER_BOUNDARY_GATE_02/pbg2/make_bundle.py package     # ZIP + PROVENANCE + SHA256SUMS.EXTERNAL
```

Il gate richiede `root` + `CAP_SETUID`/`CAP_SETGID`/`CAP_CHOWN` + `setpriv` per C02 (UID distinti).
Senza, C02 è `BLOCKED_ENVIRONMENT` con `requirement_verified: false`: **nessun PASS simulato**.

<!-- READINESS:BEGIN (generato da pbg2/readiness.py — non modificare a mano) -->
## Stato (authority unica: `pbg2/readiness.py`)

**A. Test suite** — 12/12 PASS, FAIL 0, BLOCKED 0, inventario 12/12 valido:
`all_tests_passed = true`, `test_suite_decision = ALL_TESTS_PASS`.

**B. Phase readiness** — `all_requirements_verified = false`,
`phase_gate_decision = LAB_GATE_COMPLETE_WITH_OPEN_GAPS`,
stato massimo `PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW`.

Requisiti aperti che impediscono `all_requirements_verified`:
`ORPHAN_RESERVED_LEASE_POLICY`, `NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY`,
`RECONCILIATION_FRESHNESS_NG04_POLICY`, `LEGACY_SPEND_PATHS_CORE_PRIMITIVES`,
`LEGACY_TESTS_MIGRATION_TO_GOVERNED`, `REAL_AUTHORIZATION_AND_PRICING`,
`REAL_PROVIDER_RECONCILIATION`.

**C. Merge readiness** — `runtime_candidate_ready = true`, `core_candidate_ready = true`,
**`core_runtime_pair_ready = false`**, **`merge_authorized = false`**.
Core candidate: `APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED`.

Un test PASS su un requisito aperto significa che il gate ha **verificato che quel requisito resta
aperto**: non lo chiude. Dettaglio per requisito in `TEST_RESULTS.md` e `OPEN_REQUIREMENTS.md`.
<!-- READINESS:END -->

## Matrice dei test

| ID | test | esito |
|---|---|---|
| C00 | Reality Lock canonico (Core/Runtime/pin/P2) | PASS |
| C01 | PHASE A: 5/5 gap riprodotti prima di ogni fix | PASS |
| C02 | **P-B02 + P-B01: composizione dentro lo spender isolato** | PASS |
| C03 | **NG-04: meccanismo di freshness fail-closed e parametrico** | PASS |
| C04 | **Legacy spend paths: inventario + modalità Provider Boundary** | PASS |
| C05 | **Orphan lease: meccanismo parametrico, policy non decisa** | PASS |
| C06 | NG-05: decisione e delta additivo del Core su branch dedicato | PASS |
| C07 | Regressione R0-R1 (T01-T37) | PASS (36/37, 0 FAIL, T29 `BLOCKED_ENVIRONMENT` per policy) |
| C08 | P2 freeze e Core pin invariati a fine fase | PASS |
| C09 | Reporting: test suite result e phase readiness separati (11 controprove) | PASS |
| C10 | **Catena di provenance del bundle: verificatore fail-closed** (12 controprove) | PASS |
| C11 | **Regressione del delta correttivo** (reporting/evidence-only) | PASS |

## Cosa è cambiato rispetto alla fase precedente

| requisito | prima | dopo |
|---|---|---|
| `P_B02_P_B01_COMPOSITION` | `NOT_VERIFIED` | **`VERIFIED_LAB`** |
| `RECONCILIATION_FRESHNESS_NG04` | `STILL_OPEN` | meccanismo **`VERIFIED_LAB`**, policy `POLICY_DECISION_REQUIRED` |
| `LEGACY_SPEND_PATHS_PROVIDER_GATE` | `BLOCKED_PROVIDER_GATE` (indistinto) | **scomposto**: runtime `VERIFIED_LAB`, primitive del Core `CORE_CHANGE_REQUIRED`, migrazione test `STILL_OPEN` |
| `ORPHAN_RESERVED_LEASE` | `STILL_OPEN` (indistinto) | **scomposto**: meccanismo `VERIFIED_LAB`, policy `POLICY_DECISION_REQUIRED` |
| `NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY` | `OPEN_CONSERVATIVE_LIMITATION` | **`CORE_CHANGE_REQUIRED`** con delta prodotto e verificato 9/9 su branch dedicato |
| `REAL_AUTHORIZATION_AND_PRICING` / `REAL_PROVIDER_RECONCILIATION` | `NOT_VERIFIED` | **`REAL_PROVIDER_REQUIRED`** con prerequisiti documentati |

Una premessa del mandato è risultata **falsa** ed è documentata come tale: il Core canonico **non**
offre una primitive a transazione singola con provenance parametrica (`GAP_MATRIX.md` §4).

## Documenti

| file | contenuto |
|---|---|
| `REALITY_LOCK.md` | baseline before/after |
| `GAP_MATRIX.md` | PHASE A: requisito, file/function, call path, riproduzione, stato, rischio, fix minimo, test |
| `PB01_PB02_COMPOSITION.md` | composizione P-B01+P-B02 e le 11 controprove |
| `NG04_FRESHNESS.md` | freshness: meccanismo vs policy |
| `NG05_ATOMICITY.md` | atomicità pre-submit: decisione e delta Core |
| `ORPHAN_LEASE_MECHANISM_POLICY.md` | orphan lease: meccanismo vs policy |
| `LEGACY_SPEND_PATHS_V2.md` | inventario aggiornato dei 13 entry point |
| `REAL_PROVIDER_PREREQUISITES.md` | prerequisiti per il provider reale |
| `TEST_RESULTS.md` | matrice dei test + readiness (generato) |
| `READINESS.json` | `gap_status` a macchina (generato) |
| `OPEN_REQUIREMENTS.md` | requisiti aperti e come chiuderli |
| `CHANGED_FILES.md` | file cambiati, Runtime e Core |
| `HUMAN_REVIEW_01_CORRECTIVE_DELTA.md` | risposta al HOLD: catena evidence e coppia Core+Runtime |
| `MANIFEST.json` / `SHA256SUMS` | integrità del bundle (il secondo copre il primo) |

## Catena di provenance

```
runtime_code_sha            commit con il diff FUNZIONALE del Runtime
        |
        v
runtime_evidence_head_sha   commit che aggiunge MANIFEST.json + SHA256SUMS
        |                   (dichiarato solo nella provenance ESTERNA: un file
        |                    committato non può nominare il commit che lo contiene)
        v
PROVENANCE.json             esterna, non committata — i due SHA insieme + SHA256 dello ZIP
SHA256SUMS.EXTERNAL         copre PROVENANCE.json e lo ZIP
```

`SHA256SUMS` copre **ogni file committato del bundle, incluso `MANIFEST.json`**, escluso
soltanto se stesso. Il verificatore è `pbg2/bundle_provenance.py:verify`, esercitato da C10
con 12 controprove ed eseguito sul bundle reale da `pbg2/make_bundle.py package`.

## Perimetro

`PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW` è uno stato di **lavoro** con open
gaps. **Non** significa: provider reale verificato · provider ready · production ready ·
credenziali autorizzate · spend autorizzato · **merge autorizzato** · R2 autorizzato.

`merge_authorized = false`. Il Core candidate è `APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED`.

**STOP. Serve una Human Review separata.**
