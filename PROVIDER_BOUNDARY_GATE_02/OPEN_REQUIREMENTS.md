# OPEN REQUIREMENTS — dopo PROVIDER BOUNDARY GATE / OPEN-GAP CLOSURE (2026-09-17)

> Gli stati qui sotto sono gli **stessi** che il gate produce a macchina. L'authority unica è
> `pbg2/readiness.py`; il valore per ogni id sta in `READINESS.json` (`gap_status`), in
> `evidence/RESULTS.json` (`report.phase_readiness.requirements`) e in `TEST_RESULTS.md` sezione B.
> `all_requirements_verified = false` finché uno di questi è aperto.

## A. Test suite

`10/10 PASS` · `0 FAIL` · `0 BLOCKED` · inventario `10/10` valido ·
`all_tests_passed = true` · `test_suite_decision = ALL_TESTS_PASS`

**Un test PASS può verificare che un requisito resta APERTO.** `C05 PASS` significa che il gate ha
verificato che l'orphan lease resta aperto; `C06 PASS` che il Core va modificato.

## B. Phase readiness

`all_requirements_verified = false` · `phase_gate_decision = LAB_GATE_COMPLETE_WITH_OPEN_GAPS` ·
stato massimo raggiunto: `PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW`

### Chiusi in questa fase (perimetro LAB)

| id | stato | evidenza |
|---|---|---|
| `REALITY_LOCK_CANONICAL` | `VERIFIED_LAB` | C00 |
| `GAP_MATRIX_PHASE_A` | `VERIFIED_LAB` | C01 |
| **`P_B02_P_B01_COMPOSITION`** | **`VERIFIED_LAB`** | C02 — era `NOT_VERIFIED` |
| **`RECONCILIATION_FRESHNESS_NG04_MECHANISM`** | **`VERIFIED_LAB`** | C03 — era `STILL_OPEN` |
| **`LEGACY_SPEND_PATHS_RUNTIME_CLOSURE`** | **`VERIFIED_LAB`** | C04 |
| **`ORPHAN_RESERVED_LEASE_MECHANISM`** | **`VERIFIED_LAB`** | C05 |
| `R0_R1_NO_REGRESSION` | `VERIFIED_LAB` | C07 |
| `P2_FREEZE_AND_CORE_PIN` | `VERIFIED_LAB` | C08 |
| `PHASE_READINESS_REPORTING` | `VERIFIED_LAB` | C09 |

### Aperti, imputabili a questa fase o al Provider Boundary Gate

| id | stato | cosa serve per chiuderlo |
|---|---|---|
| `ORPHAN_RESERVED_LEASE_POLICY` | **`POLICY_DECISION_REQUIRED`** | Decidere finestra (`min_age_s`), attore autorizzato, evidenze richieste, classi ammesse. Il meccanismo è pronto e parametrico. `ORPHAN_LEASE_MECHANISM_POLICY.md` §4. |
| `RECONCILIATION_FRESHNESS_NG04_POLICY` | **`POLICY_DECISION_REQUIRED`** | Decidere `max_age_s` e `max_future_skew_s`. Nessun valore è stato inventato. `NG04_FRESHNESS.md` §4. |
| `NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY` | **`CORE_CHANGE_REQUIRED`** | Human Review del delta additivo `mark_refused_pre_submit` (branch Core `harden/provider-boundary-core-atomicity-2026-09-17`, 9/9 suite PASS), merge nel Core, spostamento del pin del Runtime. `NG05_ATOMICITY.md`. |
| `LEGACY_SPEND_PATHS_CORE_PRIMITIVES` | **`CORE_CHANGE_REQUIRED`** | `transport.pipeline.run_job`, `adapter.submit` e `store.reconcile` raw non sono governati da alcun interruttore del Runtime. Proposta minima in `LEGACY_SPEND_PATHS_V2.md`; modifica del Core non autorizzata da questo mandato. |
| `LEGACY_TESTS_MIGRATION_TO_GOVERNED` | **`STILL_OPEN`** | Migrare T01-T27 al percorso governato, per poter fissare `LEGACY_LAB_SPEND_PATH = "DISABLED"` in codice. |
| `REAL_AUTHORIZATION_AND_PRICING` | **`REAL_PROVIDER_REQUIRED`** | Provider reale, credenziali, budget. Prerequisiti in `REAL_PROVIDER_PREREQUISITES.md`. |
| `REAL_PROVIDER_RECONCILIATION` | **`REAL_PROVIDER_REQUIRED`** | Come sopra. |

### Di altre fasi — elencati, NON imputati a questa

| id | stato |
|---|---|
| `RUN_CONTAMINATION` | `NOT_RUN` (input Tenant assente) |
| `G_N02_SEMANTIC_CLAIM_PARAPHRASE` | `STILL_OPEN` (non toccato) |
| `RV07_SCHEDULER_RECOVERY_RESIDUAL` | `STILL_OPEN` (non toccato; P-B02 offre ora l'uscita autenticata da `SUBMIT_UNKNOWN` **dentro lo spender**, ma nessuno scheduler la invoca) |
| `INDEPENDENT_CI_STATUS_CHECKS` | `NOT_RUN` (assenti sul branch, come nelle fasi precedenti) |

## C. Distinzione richiesta dal mandato

| categoria | id |
|---|---|
| **VERIFIED** | i 9 della sezione «Chiusi in questa fase» |
| **STILL_OPEN** | `LEGACY_TESTS_MIGRATION_TO_GOVERNED` |
| **BLOCKED** | nessun test BLOCKED; i requisiti bloccati sono classificati sotto `CORE_CHANGE_REQUIRED` |
| **POLICY_DECISION_REQUIRED** | `ORPHAN_RESERVED_LEASE_POLICY`, `RECONCILIATION_FRESHNESS_NG04_POLICY` |
| **REAL_PROVIDER_REQUIRED** | `REAL_AUTHORIZATION_AND_PRICING`, `REAL_PROVIDER_RECONCILIATION` |
| **CORE_CHANGE_REQUIRED** | `NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY`, `LEGACY_SPEND_PATHS_CORE_PRIMITIVES` |

## D. Perimetro

`PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW` **non** significa:
provider reale verificato · provider ready · production ready · credenziali autorizzate ·
spend autorizzato · merge autorizzato · R2 autorizzato.

Serve una Human Review separata.
