# COORDINATED CORE + RUNTIME INTEGRATION — NG-05 (2026-09-17)

MOCK ONLY · **ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION · NO DEPLOY · NO TAG · NO RELEASE · NO MERGE**

Lavoro autorizzato dalla Human Review dopo `HUMAN_REVIEW_APPROVED — EVIDENCE_CHAIN_CORRECTIVE_DELTA`:
l'unico lavoro ammesso era creare una **coppia Core+Runtime coerente** in cui il Runtime consumi
davvero `mark_refused_pre_submit`.

## Input approvati

| | |
|---|---|
| Core baseline canonica | `740ee979300fe20a9382992528604dee70cb2fcf` |
| **Core candidate approvato** | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` (`harden/provider-boundary-core-atomicity-2026-09-17`) |
| Core review state | `APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED` |
| Runtime main canonico | `0698279703ab959625ac4e84ee636bc5b93b45fd` |
| Runtime reviewed code sha | `e845b744a4af3a143b1b1e710016726c57ad6c39` |
| Runtime reviewed evidence head | `4a73cdad18034e7c1bd9842a37e34e0273f9325a` |
| Evidence bundle v2 | `12cd7773f5d242578ae877d34bb6d3603d429725127626a7ff4d1780dd20e078` |
| P2 frozen | `637f3a803ee38d0494f6ca51837f36207593680a06920e7d76b80660329ea7d1` |

Reality Lock: 8/8 verifiche (D00). **Nessun `APPROVED_INPUT_DRIFT`.**

## La modifica coordinata

| file | cosa cambia |
|---|---|
| `runtime/go_candidate.py` | `ReservationObserver._refuse_pre_submit` sostituisce `store.reconcile(...)` + `store.settle(...)` con **una sola** `store.mark_refused_pre_submit(job, reason, source=…, evidence=…, now=…)` |
| `runtime/core_pin.py` | `REQUIRED_CORE_SHA` `740ee979…` → **`9cf9cee1…`**; la vecchia baseline entra in `KNOWN_STALE_CORE_SHAS`, così un Core senza l'API viene rifiutato con `STALE_CORE_PIN` invece di un `AttributeError` a metà percorso |

```
 RUNTIME_INTEGRATION_GATE_01/runtime/core_pin.py     | 18 ++++--
 RUNTIME_INTEGRATION_GATE_01/runtime/go_candidate.py | 63 +++++++++++-----------
 2 files changed, 46 insertions(+), 35 deletions(-)
```

**Il Core candidate non è stato modificato.** Nessun `APPROVED_CORE_CANDIDATE_INSUFFICIENT`:
l'API approvata è bastata così com'era.

La provenance resta quella osservata: `RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED`.
`TRANSPORT_ATTESTED_NOT_SENT` non è usata per il caso pre-transport — e ora è il **Core** a
rifiutarla su quel percorso, quindi l'invariante NG-03 è imposta da entrambi i lati.

## Come rieseguire

```bash
export CREATIVE_OS_CORE_PATH=/home/user/creative-os-atomicity          # Core candidate
export CREATIVE_OS_CORE_BASELINE_PATH=/home/user/creative-os           # Core baseline
python3 CORE_RUNTIME_INTEGRATION_01/cri1/run_gate_d.py                 # D00..D12
```

Senza `CREATIVE_OS_CORE_PATH` sul candidate, il runtime si ferma **prima dell'import** con
`STALE_CORE_PIN`: è il comportamento voluto, non un problema di configurazione.

D09 (composizione P-B01+P-B02) richiede `root` + `CAP_SETUID`/`CAP_SETGID`/`CAP_CHOWN` +
`setpriv`. Senza, è `BLOCKED_ENVIRONMENT`: nessun PASS simulato.

## Matrice dei test

| ID | test | esito |
|---|---|---|
| D00 | Reality Lock sugli input approvati | PASS |
| D01 | Core pin al candidate; fail-closed su baseline/sporco/assente; consumo reale dell'API | PASS |
| D02 | **NG-05 end-to-end: SERIALIZATION_DRIFT** | PASS |
| D03 | **NG-05 end-to-end: IDENTITY_DRIFT** | PASS |
| D04 | **NG-05 end-to-end: crash prima del COMMIT del Core** | PASS |
| D05 | **NG-05 end-to-end: CAS, non-RESERVED, identità remota, provenance vietata** | PASS |
| D06 | NG-03 preservation: provenance del trasporto confinata | PASS |
| D07 | NG-03 controprova positiva: il percorso transport-attested la registra ancora | PASS |
| D08 | SUBMIT_UNKNOWN: nessun settlement zero, nessun blind retry | PASS |
| D09 | Regressioni dei meccanismi sul Core candidate | PASS |
| D10 | Regressione R0-R1 (T01-T37) contro il Core candidate | PASS (36/37, 0 FAIL, T29 `BLOCKED_ENVIRONMENT` per policy) |
| D11 | P2 freeze, baseline intatte, bundle approvati non toccati | PASS |
| D12 | Catena di provenance: struttura approvata preservata | PASS |

<!-- READINESS:BEGIN (generato da cri1/readiness.py — non modificare a mano) -->
## Stato

**A. Test suite** — 13/13 PASS, FAIL 0, BLOCKED 0, inventario 13/13 valido:
`all_tests_passed = true`.

**B. Phase readiness** — `all_requirements_verified = false`,
`phase_gate_decision = LAB_GATE_COMPLETE_WITH_OPEN_GAPS`,
stato massimo `CORE_RUNTIME_PAIR_READY_FOR_HUMAN_REVIEW`.

**C. Pair readiness** — `core_candidate_ready = true`, `runtime_candidate_ready = true`,
`pin_points_to_core_candidate = true`, `runtime_consumes_core_candidate = true`,
**`core_runtime_pair_ready = true`**, **`merge_authorized = false`**.

Pair blockers: nessuno. Merge blockers: `OPEN_REQUIREMENTS`, `HUMAN_MERGE_AUTHORIZATION_ABSENT`.
<!-- READINESS:END -->

## Cosa `core_runtime_pair_ready = true` NON significa

- **non** è un'autorizzazione al merge (`merge_authorized = false`);
- **non** implica la chiusura degli altri open requirements;
- **non** significa provider reale, credenziali, spend o production ready.

Restano aperti, invariati e distinti: `RECONCILIATION_FRESHNESS_NG04_POLICY` e
`ORPHAN_RESERVED_LEASE_POLICY` (`POLICY_DECISION_REQUIRED`),
`LEGACY_SPEND_PATHS_CORE_PRIMITIVES` (`CORE_CHANGE_REQUIRED`),
`LEGACY_TESTS_MIGRATION_TO_GOVERNED` (`STILL_OPEN`), `REAL_AUTHORIZATION_AND_PRICING` e
`REAL_PROVIDER_RECONCILIATION` (`REAL_PROVIDER_REQUIRED`).

Il Core delta NG-05 **non** li risolve: sono problemi diversi.

## Documenti

| file | contenuto |
|---|---|
| `REALITY_LOCK.md` | input approvati, before/after |
| `RUNTIME_DIFF.md` | il diff coordinato, riga per riga |
| `NG05_END_TO_END.md` | le sei dimostrazioni di atomicità |
| `OPEN_REQUIREMENTS.md` | requisiti aperti e pair readiness |
| `CHANGED_FILES.md` | file cambiati, Runtime e Core |
| `TEST_RESULTS.md`, `READINESS.json` | generati dall'authority unica |
| `MANIFEST.json`, `SHA256SUMS` | integrità del bundle (il secondo copre il primo) |

## Perimetro

`CORE_RUNTIME_PAIR_READY_FOR_HUMAN_REVIEW` con `merge_authorized = false`.

**STOP. Serve una Human Merge Authorization separata. Non mergiare.**
