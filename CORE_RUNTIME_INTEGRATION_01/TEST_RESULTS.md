# TEST RESULTS — COORDINATED CORE + RUNTIME INTEGRATION (NG-05, 2026-09-17)

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO MERGE.

| ID | TEST | ATTESO | OSSERVATO | ESITO | EVIDENZA |
|---|---|---|---|---|---|
| D00 | Reality Lock sugli input approvati | Core main/candidate, Runtime main/reviewed, P2, tree puliti | Core main 740ee979300f · candidate 9cf9cee1a751 (harden/provider-boundary-core-atomicity-2026-09-17) · Runtime main 0698279703ab · reviewed 4a73cdad1803 · HEAD 4a73cdad1803 su integrate/provider-boundary-core-runtime-2026-09-17 · P2 637f3a803ee38d04 · check falliti: nessuno | **PASS** | `evidence/D00_reality_lock_approved_inputs.json` |
| D01 | Core pin al candidate e consumo reale dell'API | CORE_PIN_OK solo sul candidate pulito; baseline/sporco/assente fail-closed; unico call site dell'API atomica | pin 9cf9cee1a751 · candidate -> CORE_PIN_OK · baseline -> STALE_CORE_PIN · sporco -> CORE_WORKTREE_DIRTY · assente -> CORE_PIN_MISMATCH · go() su Core vecchio -> STALE_CORE_PIN senza store · call site dell'API atomica: [('go_candidate.py', '_refuse_pre_submit')] · check falliti: nessuno | **PASS** | `evidence/D01_core_pin_and_api_consumption.json` |
| D02 | NG-05 end-to-end: SERIALIZATION_DRIFT | FAILED + settlement 0 + 1 ledger + 1 anomalia, provenance veritiera, 0 invii | drift_nested: FAILED settled=0 source=RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED · 1 riga SETTLE · runtime atomic=True api=mark_refused_pre_submit · transport_sent=0 · terminal_unsettled=0 | **PASS** | `evidence/D02_ng05_e2e_drift_nested.json` |
| D03 | NG-05 end-to-end: IDENTITY_DRIFT | stesso comportamento di D02 | identity_drift: FAILED settled=0 source=RUNTIME_PRE_SUBMIT_REFUSED_NOT_DISPATCHED · 1 riga SETTLE · runtime atomic=True api=mark_refused_pre_submit · transport_sent=0 · terminal_unsettled=0 | **PASS** | `evidence/D03_ng05_e2e_identity_drift.json` |
| D04 | NG-05 end-to-end: crash prima del COMMIT del Core | nulla di parziale; retry senza crash riesce | morte reale prima del COMMIT (exit 13): stato RESERVED, settled None, 0 righe SETTLE, anomalie [] · nulla di parziale=True · retry senza crash -> FAILED settled 0, 1 riga SETTLE | **PASS** | `evidence/D04_ng05_e2e_crash_before_core_commit.json` |
| D05 | NG-05 end-to-end: CAS, non-RESERVED, identita' remota, provenance vietata | tutti rifiutati fail-closed, nessun doppio settlement | vista obsoleta -> rifiutata (TransitionRefused), nessun doppio settlement=True · job non piu' RESERVED -> TransitionRefused · identita' remota persistita -> TransitionRefused + anomalia PRE_SUBMIT_REFUSAL_NOT_APPLICABLE=True · provenance del trasporto su questo percorso -> ReconciliationEvidenceRequired | **PASS** | `evidence/D05_ng05_e2e_cas_and_not_applicable.json` |
| D06 | NG-03 preservation: provenance del trasporto confinata | mark_refused_before_send invariata e mai chiamata dal runtime | mark_refused_before_send invariata (True) e mai chiamata dal runtime (True) · call sites: {'mark_refused_pre_submit': [('go_candidate.py', '_refuse_pre_submit')], 'reconcile': [('orphan_lease.py', 'reclaim_orphan_reserved'), ('reconciliation.py', 'reconcile_authenticated')], 'settle': [('orphan_lease.py', 'reclaim_orphan_reserved')]} | **PASS** | `evidence/D06_ng03_preservation.json` |
| D07 | NG-03 controprova positiva: percorso transport-attested | TRANSPORT_ATTESTED_NOT_SENT ancora registrata dove e' vera | percorso con attestazione reale del trasporto -> FAILED settled 0 source TRANSPORT_ATTESTED_NOT_SENT · evidenza TRANSPORT_ATTESTED_NOT_SENT | **PASS** | `evidence/D07_ng03_transport_attested_still_works.json` |
| D08 | SUBMIT_UNKNOWN: nessun settlement zero, nessun blind retry | resta SUBMIT_UNKNOWN; API atomica rifiutata; 1 solo attempt | invio incerto -> SUBMIT_UNKNOWN, settled None, 0 righe SETTLE · resume -> SUBMIT_UNKNOWN submits 0, attempt per l'operazione: 1 · API atomica su SUBMIT_UNKNOWN -> TransitionRefused | **PASS** | `evidence/D08_submit_unknown_no_zero_settlement.json` |
| D09 | Regressioni dei meccanismi sul Core candidate | P-B01+P-B02, NG-04, legacy, orphan, P-B04 invariati | sul Core candidate: P-B01+P-B02 composition, NG-04 freshness, legacy spend paths, orphan lease, P-B04 snapshot · falliti: nessuno | **PASS** | `evidence/D09_mechanism_regressions_on_candidate.json` |
| D10 | Regressione R0-R1 (T01-T37) contro il Core candidate | 36/37 PASS, 0 FAIL, T29 BLOCKED per policy | T01-T37 contro il Core candidate: exit 0 · PASS 36/37 · FAIL nessuno · BLOCKED ['T29/BLOCKED_ENVIRONMENT'] · decisione LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED | **PASS** | `evidence/D10_regression_r0_r1_on_candidate.json` |
| D11 | P2 freeze, baseline intatte, bundle approvati non toccati | P2 before==after; Core/Runtime main invariati; 0 tag; 0 credenziali | P2 637f3a803ee38d04 before==after · Core main 740ee979300f pulito · candidate 9cf9cee1a751 invariato · bundle approvato v2 e v3 non toccati · 0 tag · 0 credenziali · check falliti: nessuno | **PASS** | `evidence/D11_p2_freeze_and_baselines_untouched.json` |
| D12 | Catena di provenance: struttura approvata preservata | 5 controprove del verificatore | catena approvata preservata · 5 controprove · scarti: nessuno | **PASS** | `evidence/D12_evidence_chain_integrity.json` |

## A. TEST SUITE RESULT

| inventario | PASS | FAIL | BLOCKED | all_tests_passed | decisione |
|---|---|---|---|---|---|
| 13/13 (valido: True) | 13 | 0 | 0 | **true** | `ALL_TESTS_PASS` |

_i test hanno prodotto l'esito atteso. NON significa che i requisiti siano chiusi ne' che il merge sia autorizzato._

## B. PHASE / REQUIREMENT READINESS

**`all_requirements_verified = false`** · **`phase_gate_decision = LAB_GATE_COMPLETE_WITH_OPEN_GAPS`** · stato massimo: `CORE_RUNTIME_PAIR_READY_FOR_HUMAN_REVIEW`

| REQUISITO | SCOPE | STATO | EVIDENZA | NOTA |
|---|---|---|---|---|
| APPROVED_INPUT_REALITY_LOCK | this_phase | **`VERIFIED_LAB`** | D00 | 8/8 verifiche. Nessun APPROVED_INPUT_DRIFT. |
| CORE_PIN_POINTS_TO_CANDIDATE | this_phase | **`VERIFIED_LAB`** | D01 | Candidate pulito -> CORE_PIN_OK. Baseline vecchia -> STALE_CORE_PIN (non MISMATCH generico: e' un Core VECCHIO, e il runtime lo dice). Candidate sporco -> CORE_WORKTREE_DIRTY. Path assente / SHA sbagliato -> CORE_PIN_MISMATCH. `go()` contro la baseline si ferma PRIMA dell'import e senza creare lo store. |
| RUNTIME_CONSUMES_CORE_CANDIDATE | this_phase | **`VERIFIED_LAB`** | D01, D06 | Unico call site: go_candidate._refuse_pre_submit. Il percorso a due transazioni reconcile -> settle e' RIMOSSO dal caso pre-submit; `settle` non e' piu' chiamata dal runtime; `reconcile` resta solo per il report autenticato P-B02. |
| NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY | this_phase | **`VERIFIED_LAB`** | D02, D03, D04, D05 | SERIALIZATION_DRIFT e IDENTITY_DRIFT: FAILED + settlement 0 + 1 riga di ledger + 1 anomalia, in UNA transazione, con provenance veritiera. Crash prima del COMMIT del Core: nulla di parziale, e la chiusura ritentata riesce. Vista obsoleta: CAS fail-closed, nessun doppio settlement. Non-RESERVED e identita' remota persistita: rifiutati. Era CORE_CHANGE_REQUIRED. |
| NG03_PRE_SUBMIT_SETTLEMENT_PROVENANCE | this_phase | **`VERIFIED_LAB`** | D06, D07 | `TRANSPORT_ATTESTED_NOT_SENT` resta esclusiva del percorso con attestazione reale (controprova positiva: quel percorso la registra ancora). Il Core la RIFIUTA come `source` del percorso pre-submit, quindi l'invariante e' ora imposta da entrambi i lati. |
| SUBMIT_UNKNOWN_NO_ZERO_SETTLEMENT | this_phase | **`VERIFIED_LAB`** | D08 | L'API atomica rifiuta un job non RESERVED: un invio che puo' essere avvenuto non diventa gratis. RESUME non crea un nuovo attempt ne' un nuovo submit. |
| MECHANISM_REGRESSIONS_ON_CANDIDATE | this_phase | **`VERIFIED_LAB`** | D09 | Nessun test storico indebolito: stessi asserti, Core diverso. |
| R0_R1_NO_REGRESSION | this_phase | **`VERIFIED_LAB`** | D10 | Stessa forma della baseline: 36/37 PASS, 0 FAIL, T29 BLOCKED_ENVIRONMENT per policy. |
| P2_FREEZE_AND_BASELINE_UNTOUCHED | this_phase | **`VERIFIED_LAB`** | D11 | Il Core candidate non e' stato modificato oltre il commit approvato. |
| EVIDENCE_CHAIN_INTEGRITY | this_phase | **`VERIFIED_LAB`** | D12 | Stessa struttura approvata dalla Human Review: nessun `runtime_commit`, SHA256SUMS copre MANIFEST.json, nessun .pyc nel package. |
| RECONCILIATION_FRESHNESS_NG04_POLICY | future_gate | **`POLICY_DECISION_REQUIRED`** | D09 | Meccanismo verificato anche sul Core candidate. Nessun valore scelto: servono clock semantics, latenza e timing reali del provider. |
| ORPHAN_RESERVED_LEASE_POLICY | this_phase | **`POLICY_DECISION_REQUIRED`** | D09 | Meccanismo verificato anche sul Core candidate. `RECLAIM_POLICY = NOT_AUTHORIZED`. |
| LEGACY_SPEND_PATHS_CORE_PRIMITIVES | future_gate | **`CORE_CHANGE_REQUIRED`** | D09 | PROBLEMA DISTINTO da NG-05. Il Core candidate aggiunge una primitive, non ne governa l'accesso: `transport.pipeline.run_job`, `adapter.submit` e `store.reconcile` raw restano raggiungibili. Non chiuso da questa integrazione. |
| LEGACY_TESTS_MIGRATION_TO_GOVERNED | future_gate | **`STILL_OPEN`** | D09 | PROBLEMA DISTINTO da NG-05. Invariato. |
| REAL_AUTHORIZATION_AND_PRICING | future_gate | **`REAL_PROVIDER_REQUIRED`** | — | Fuori scope: nessun provider reale, nessuna credenziale, 0 crediti. |
| REAL_PROVIDER_RECONCILIATION | future_gate | **`REAL_PROVIDER_REQUIRED`** | — | Fuori scope. |
| CORE_RUNTIME_MERGE_AUTHORIZATION | this_phase | **`STILL_OPEN`** | D11 | Non e' un fatto tecnico e il codice non se la concede: serve una Human Merge Authorization separata. `merge_authorized = false` finche' non arriva. |
| RUN_CONTAMINATION | other_phase | **`NOT_RUN`** | — | Input Tenant assente. |
| G_N02_SEMANTIC_CLAIM_PARAPHRASE | other_phase | **`STILL_OPEN`** | — | Non toccato. |
| RV07_SCHEDULER_RECOVERY_RESIDUAL | other_phase | **`STILL_OPEN`** | — | Non toccato. |
| INDEPENDENT_CI_STATUS_CHECKS | other_phase | **`NOT_RUN`** | — | Assenti sul branch. |

## C. PAIR READINESS

| campo | valore |
|---|---|
| `core_candidate_ready` | **`true`** |
| `runtime_candidate_ready` | **`true`** |
| `pin_points_to_core_candidate` | **`true`** |
| `runtime_consumes_core_candidate` | **`true`** |
| `core_runtime_pair_ready` | **`true`** |
| `merge_authorized` | **`false`** |
| `core_review_state` | `APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED` |
| `required_core_sha` | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` |
| `core_candidate_sha` | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` |
| `human_merge_authorization` | `false` |

Pair blockers: nessuno. Merge blockers: `OPEN_REQUIREMENTS`, `HUMAN_MERGE_AUTHORIZATION_ABSENT`.

_la coppia Core+Runtime e' COERENTE e promuovibile? Vero quando il Runtime consuma davvero l'API del Core candidate, il pin vi punta, NG-05 e' dimostrato end-to-end e NG-03 e' preservato. NON implica la chiusura degli altri open requirements, e NON e' un'autorizzazione al merge._

`core_runtime_pair_ready` **non implica**: chiusura degli altri open requirements, merge autorizzato, provider reale, production ready.

Nulla di quanto sopra significa provider reale verificato, provider ready, production ready, credenziali autorizzate, spend autorizzato, merge autorizzato, R2 autorizzato, chiusura degli altri open requirements.

