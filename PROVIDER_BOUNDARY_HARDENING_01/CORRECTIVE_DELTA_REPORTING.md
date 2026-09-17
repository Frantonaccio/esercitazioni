# CORRECTIVE DELTA — REPORTING (HUMAN REVIEW 02, `PHASE_READINESS_REPORTING_INCONSISTENT`)

Verdetto ricevuto: HOLD **esclusivamente di reporting/classificazione**; il delta NG-03 e' approvato sul piano
funzionale. Questo delta e' reporting-only: **nessuna modifica** a `runtime/go_candidate.py`,
`runtime/payload_snapshot.py`, `runtime/reconciliation.py`, al Core, a P2 o alla logica P-B01/P-B02/P-B04
(verificabile: il diff del runtime rispetto alla baseline canonica e' **identico** a quello del bundle v2).

## 1. Il difetto
`RESULTS.json` affermava nello stesso documento `all_requirements_verified = true` e
`gate_decision = LAB_GATE_COMPLETE_ALL_VERIFIED`, mentre lo stesso file dichiarava orphan lease `STILL_OPEN`,
legacy path `RESIDUAL_BLOCKED_PROVIDER_GATE`, P-B02 verificata solo per binding/auth, e piu' gap `NOT_VERIFIED`.
La causa: una sola struttura rispondeva a due domande diverse. `13/13 PASS` e' un fatto sui **test**; "i requisiti
della fase sono chiusi" e' un fatto sui **requisiti**. `B08 PASS` significa che il gate ha verificato che l'orphan
lease **resta aperto**: e' un test superato su un requisito aperto, non una chiusura.

## 2. La correzione — una sola authority, due sezioni
`pbgate/phase_readiness.py` e' ora l'unica sede in cui nasce la classificazione. Console, `evidence/RESULTS.json`,
`TEST_RESULTS.md`, `MANIFEST.json` (via `pbgate/make_manifest.py`) e il blocco di stato del `README.md` **derivano**
da `build(...)`: nessuno di essi ricalcola o riformula.

**A. TEST SUITE RESULT** — `all_tests_passed`, `test_suite_decision` ∈ {`ALL_TESTS_PASS`, `TESTS_FAILED`,
`TESTS_BLOCKED_BY_ENVIRONMENT`, `TEST_INVENTORY_INVALID`}, inventario e conteggi. Puo' essere verde.

**B. PHASE / REQUIREMENT READINESS** — `all_requirements_verified`, `phase_gate_decision` ∈
{`LAB_GATE_COMPLETE_WITH_OPEN_GAPS`, `LAB_GATE_COMPLETE_ALL_VERIFIED`, `PHASE_GATE_NOT_FAVORABLE`,
`PHASE_GATE_INVALID`}, elenco strutturato dei requisiti con stato ∈ {`VERIFIED_LAB`, `STILL_OPEN`,
`BLOCKED_PROVIDER_GATE`, `OPEN_CONSERVATIVE_LIMITATION`, `NOT_VERIFIED`, `NOT_RUN`}.

Regole applicate:
- lo stato di un requisito **non e' scritto a mano**: e' quello dichiarato solo se i test che lo sostengono sono
  PASS, altrimenti degrada a uno stato aperto (`EVIDENCE_TESTS_NOT_PASSED`). Un test che fallisce non puo'
  lasciare in piedi una classificazione "verificata";
- `all_requirements_verified` e' vero **solo** se tutti i test sono PASS **e** nessun requisito di questa fase o
  del Provider Boundary Gate e' aperto. Un `BLOCKED_PROVIDER_GATE` lo impedisce (il primo modello non lo faceva:
  il difetto e' stato trovato dalla controprova 2 e corretto);
- `validate()` e' fail-closed: un report che afferma `all_requirements_verified` con un requisito `STILL_OPEN` o
  `BLOCKED_PROVIDER_GATE` imputabile alla fase solleva `ReportingInconsistent` e non viene prodotto;
- `cross_check_written_files()` rilegge i file scritti e li confronta con il report: una divergenza e' un errore.

Lo **stato massimo resta** `PROVIDER_EXECUTION_BOUNDARY_HARDENING_READY_FOR_HUMAN_REVIEW` anche con gap aperti:
il lavoro della fase puo' essere completo mentre alcuni requisiti sono esplicitamente rinviati.

## 3. P-B02 allineata anche a macchina
| Chiave | Valore |
|---|---|
| `P_B02_BINDING_AUTHENTICATION` | `VERIFIED_LAB` (nota: *binding e autenticazione soltanto*) |
| `P_B02_P_B01_COMPOSITION` | `NOT_VERIFIED` |
| `REAL_PROVIDER_RECONCILIATION` | `NOT_VERIFIED` |
| `RECONCILIATION_FRESHNESS_NG04` | `STILL_OPEN` |

Non esiste piu' una chiave che possa essere letta come "P-B02 interamente chiusa".

## 4. Esito sul report reale di questa esecuzione
| | |
|---|---|
| A — test | 14/14 PASS, 0 FAIL, 0 BLOCKED, inventario 14/14 · `all_tests_passed = true` · `ALL_TESTS_PASS` |
| B — requisiti | `all_requirements_verified = false` · `LAB_GATE_COMPLETE_WITH_OPEN_GAPS` · stato massimo raggiunto |
| Aperti (questa fase) | `ORPHAN_RESERVED_LEASE`, `P_B02_P_B01_COMPOSITION`, `NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY` |
| Aperti (Provider Boundary Gate) | `LEGACY_SPEND_PATHS_PROVIDER_GATE`, `RECONCILIATION_FRESHNESS_NG04`, `REAL_AUTHORIZATION_AND_PRICING`, `REAL_PROVIDER_RECONCILIATION` |
| Elencati, altre fasi | `RUN_CONTAMINATION`, `G_N02_SEMANTIC_CLAIM_PARAPHRASE`, `RV07_SCHEDULER_RECOVERY_RESIDUAL`, `INDEPENDENT_CI_STATUS_CHECKS` |
| Verificati in LAB | P-B01, P-B02 binding/auth, P-B04, NG-03, legacy inventory+switch, P2/Core pin, nessuna regressione R0-R1 |

## 5. Controprove (B13, `evidence/B13_reporting_phase_readiness.json`) — le cinque richieste
| # | Caso | Esito |
|---|---|---|
| 1 | test tutti PASS + orphan lease `STILL_OPEN` | `all_tests_passed = true`, `all_requirements_verified = false`, decisione `LAB_GATE_COMPLETE_WITH_OPEN_GAPS` |
| 2 | test tutti PASS + legacy `BLOCKED_PROVIDER_GATE` | **NON** ALL_VERIFIED (il requisito compare fra quelli che lo impediscono) |
| 3 | P-B02 binding/auth `VERIFIED_LAB` + composizione `NOT_VERIFIED` | P-B02 non e' rappresentata come chiusa: la composizione resta fra gli aperti |
| 4 | nessun requisito aperto (caso sintetico) | **solo allora** `all_requirements_verified = true` e `LAB_GATE_COMPLETE_ALL_VERIFIED`; con un test FAIL non accade comunque |
| 5 | console / JSON / Markdown / MANIFEST | stessi conteggi e stessa decisione; il manifest non contiene mai `"all_requirements_verified": true` quando e' falso |
| + | report forgiato a mano (`all_requirements_verified` forzato a true) | **rifiutato** da `validate()` |

Piu' le verifiche sul report reale: test verdi, requisiti non tutti verificati, decisione con gap aperti, stato
massimo ancora raggiungibile, i quattro id richiesti dal review presenti fra gli aperti, NG-05 classificato
`OPEN_CONSERVATIVE_LIMITATION`, orphan `STILL_OPEN` nonostante `B08` PASS.
