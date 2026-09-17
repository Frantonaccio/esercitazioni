# OPEN REQUIREMENTS — dopo COORDINATED CORE + RUNTIME INTEGRATION (NG-05)

> Gli stati sono gli stessi che il gate produce a macchina. Authority unica:
> `cri1/readiness.py`, che **importa** il vocabolario approvato da
> `PROVIDER_BOUNDARY_GATE_02/pbg2/readiness.py` invece di copiarlo. I valori stanno in
> `READINESS.json` (`gap_status`), `evidence/RESULTS.json` e `TEST_RESULTS.md` sezione B.

## A. Test suite

`13/13 PASS` · `0 FAIL` · `0 BLOCKED` · inventario `13/13` valido · `all_tests_passed = true`.

## B. Phase readiness

`all_requirements_verified = false` · `phase_gate_decision = LAB_GATE_COMPLETE_WITH_OPEN_GAPS` ·
stato massimo `CORE_RUNTIME_PAIR_READY_FOR_HUMAN_REVIEW`.

### Chiusi da questa integrazione

| id | stato | evidenza |
|---|---|---|
| `APPROVED_INPUT_REALITY_LOCK` | `VERIFIED_LAB` | D00 |
| `CORE_PIN_POINTS_TO_CANDIDATE` | `VERIFIED_LAB` | D01 |
| `RUNTIME_CONSUMES_CORE_CANDIDATE` | `VERIFIED_LAB` | D01, D06 |
| **`NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY`** | **`VERIFIED_LAB`** — era `CORE_CHANGE_REQUIRED` | D02, D03, D04, D05 |
| `NG03_PRE_SUBMIT_SETTLEMENT_PROVENANCE` | `VERIFIED_LAB` | D06, D07 |
| `SUBMIT_UNKNOWN_NO_ZERO_SETTLEMENT` | `VERIFIED_LAB` | D08 |
| `MECHANISM_REGRESSIONS_ON_CANDIDATE` | `VERIFIED_LAB` | D09 |
| `R0_R1_NO_REGRESSION` | `VERIFIED_LAB` | D10 |
| `P2_FREEZE_AND_BASELINE_UNTOUCHED` | `VERIFIED_LAB` | D11 |
| `EVIDENCE_CHAIN_INTEGRITY` | `VERIFIED_LAB` | D12 |

### Aperti — invariati per decisione esplicita della Human Review

| id | stato | perché resta aperto |
|---|---|---|
| `RECONCILIATION_FRESHNESS_NG04_POLICY` | **`POLICY_DECISION_REQUIRED`** | Il meccanismo è verificato anche sul Core candidate (D09). I **valori** di `max_age_s` e `max_future_skew_s` richiedono clock semantics, latenza e timing reali del provider. Nessun valore inventato: nessun 30s, 60s, 5m. |
| `ORPHAN_RESERVED_LEASE_POLICY` | **`POLICY_DECISION_REQUIRED`** | Meccanismo verificato anche sul candidate (D09). `RECLAIM_POLICY = NOT_AUTHORIZED`. Finestra, attore, evidenze e classi ammesse restano una decisione umana. |
| `LEGACY_SPEND_PATHS_CORE_PRIMITIVES` | **`CORE_CHANGE_REQUIRED`** | **Problema distinto da NG-05.** Il Core candidate *aggiunge* una primitive, non ne governa l'accesso: `transport.pipeline.run_job`, `adapter.submit` e `store.reconcile` raw restano raggiungibili da qualunque codice con il Core in `sys.path`. Non chiuso da questa integrazione. |
| `LEGACY_TESTS_MIGRATION_TO_GOVERNED` | **`STILL_OPEN`** | **Problema distinto da NG-05.** Invariato. |
| `REAL_AUTHORIZATION_AND_PRICING` | **`REAL_PROVIDER_REQUIRED`** | Fuori scope: nessun provider reale, nessuna credenziale, 0 crediti. |
| `REAL_PROVIDER_RECONCILIATION` | **`REAL_PROVIDER_REQUIRED`** | Come sopra. |
| `CORE_RUNTIME_MERGE_AUTHORIZATION` | **`STILL_OPEN`** | Non è un fatto tecnico. Serve una Human Merge Authorization separata; il codice non se la concede. |

### Di altre fasi — elencati, non imputati

`RUN_CONTAMINATION` (`NOT_RUN`), `G_N02_SEMANTIC_CLAIM_PARAPHRASE` (`STILL_OPEN`),
`RV07_SCHEDULER_RECOVERY_RESIDUAL` (`STILL_OPEN`), `INDEPENDENT_CI_STATUS_CHECKS` (`NOT_RUN`).

## C. Pair readiness

| campo | valore |
|---|---|
| `core_candidate_ready` | **`true`** |
| `runtime_candidate_ready` | **`true`** |
| `pin_points_to_core_candidate` | **`true`** |
| `runtime_consumes_core_candidate` | **`true`** |
| **`core_runtime_pair_ready`** | **`true`** |
| **`merge_authorized`** | **`false`** |
| `core_review_state` | `APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED` |
| `required_core_sha` | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` |
| `core_candidate_sha` | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` |

**Pair blockers: nessuno.**
**Merge blockers:** `OPEN_REQUIREMENTS`, `HUMAN_MERGE_AUTHORIZATION_ABSENT`.

### Invarianti fail-closed (`cri1/readiness.validate`)

Solleva `ReportingInconsistent` se:

- `core_runtime_pair_ready = true` con blockers non vuoti;
- `core_runtime_pair_ready = true` senza pin, senza consumo dell'API, senza NG-05 end-to-end
  verificato o senza NG-03 preservato;
- `merge_authorized = true` con coppia non pronta;
- `merge_authorized = true` con requisiti aperti;
- `merge_authorized = true` senza `human_merge_authorization` esplicita;
- `merge_authorized = false` senza `merge_blockers` dichiarati;
- `max_state` di coppia senza `core_runtime_pair_ready`.

### Cosa `core_runtime_pair_ready = true` NON implica

- chiusura degli altri open requirements;
- merge autorizzato;
- provider reale;
- production ready.

## D. Perimetro

`CORE_RUNTIME_PAIR_READY_FOR_HUMAN_REVIEW` con `merge_authorized = false`.

**STOP. Serve una Human Merge Authorization separata. Non mergiare.**
