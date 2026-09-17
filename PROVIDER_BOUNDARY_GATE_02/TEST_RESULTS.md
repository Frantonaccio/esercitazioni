# TEST RESULTS — PROVIDER BOUNDARY GATE / OPEN-GAP CLOSURE (2026-09-17)

MOCK ONLY · ZERO PROVIDER REALE · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUCTION.

| ID | TEST | ATTESO | OSSERVATO | ESITO | EVIDENZA |
|---|---|---|---|---|---|
| C00 | Reality Lock canonico (Core/Runtime/pin/P2) | Core 740ee979 clean · Runtime origin/main 0698279 · pin == Core · P2 637f3a80 | Core 740ee979300f (main) clean=True · Runtime origin/main 0698279703ab (HEAD 2b99e28f3e3d discende=True) · pin 740ee979300f · P2 637f3a803ee38d04 | **PASS** | `evidence/C00_reality_lock.json` |
| C01 | PHASE A: gap riprodotti prima di ogni fix | 5/5 REPRODUCED su Runtime canonico; premessa Core falsificata | riproduzioni pre-fix: {'ng04_freshness': 'REPRODUCED', 'ng05_atomicity': 'REPRODUCED', 'orphan_lease': 'REPRODUCED', 'legacy_spend_paths': 'REPRODUCED', 'pb01_pb02_composition': 'REPRODUCED'} · premessa «il Core offre gia' una primitive atomica» verificata FALSA (core_change_required=True) | **PASS** | `evidence/C01_phase_a_reproductions.json` |
| C02 | P-B02 + P-B01: composizione dentro lo spender isolato | segreto e chiave confinati; forge/replay/binding/UID non autorizzato fail-closed; report dello spender applicato | orchestrator uid 65531 vs spender 65532 · segreto di riconciliazione BLOCKED (PermissionError) · chiave: /proc/mem BLOCKED (PermissionError), ready-file senza chiave True, 0 hex64 estranei sul canale · forge -> UNAUTHENTICATED · terzo uid -> PEER_UID_NOT_AUTHORIZED · report dello spender -> SUCCEEDED · replay: orchestrator -> NOT_RECONCILABLE, nonce dentro lo spender -> REPLAY · binding {'wrong_provider': 'PROVIDER_MISMATCH', 'wrong_account': 'ACCOUNT_MISMATCH', 'wrong_job': 'JOB_UNKNOWN', 'wrong_operation': 'OPERATION_MISMATCH', 'wrong_attempt': 'ATTEMPT_TOKEN_MISMATCH', 'wrong_payload_digest': 'PAYLOAD_DIGEST_MISMATCH', 'stale': 'REPORT_STALE', 'from_future': 'REPORT_FROM_FUTURE', 'replay': 'REPLAY'} · check falliti: nessuno | **PASS** | `evidence/C02_pb01_pb02_composition.json` |
| C03 | NG-04: meccanismo di freshness fail-closed e parametrico | policy obbligatoria; stale/futuro/malformato/assente/replay rifiutati; confini esatti | 18 controprove fail-closed (scarti: nessuno) · casi che devono passare: tutti · policy omessa -> FRESHNESS_POLICY_REQUIRED · 1970 -> REPORT_STALE · futuro -> REPORT_FROM_FUTURE · confine age==max -> applicato=True · nonce non bruciato da un rifiuto -> applicato=True · replay -> REPLAY · journal invariato sui rifiuti: True | **PASS** | `evidence/C03_ng04_freshness_mechanism.json` |
| C04 | Legacy spend paths: inventario + modalita' Provider Boundary | percorsi non governati del Runtime chiusi fail-closed; primitive del Core dichiarate aperte | modalita' disingaggiata: legacy #2 spende (SUCCEEDED), helper #7 ok · ingaggiata: #2 -> LEGACY_SPEND_PATH_DISABLED, #7 -> PROVIDER_BOUNDARY_MODE_ENGAGED (store non creato), #1 governato -> SUCCEEDED · primitive del Core #10/#11 raggiungibili in ENTRAMBE le modalita' (CORE_CHANGE_REQUIRED) · check falliti: nessuno | **PASS** | `evidence/C04_legacy_spend_paths_v2.json` |
| C05 | Orphan lease: meccanismo parametrico, policy non decisa | policy obbligatoria; authority/evidenza/lease/fence/classe fail-closed; reclaim legittimo senza nuovi attempt; crash riparabile | policy omessa -> POLICY_DECISION_REQUIRED · attore errato -> RECLAIM_NOT_AUTHORIZED · evidenza incompleta -> RECLAIM_EVIDENCE_INCOMPLETE · lease non scaduto -> LEASE_NOT_EXPIRED · fence stantio -> FENCING_TOKEN_STALE · classe non ammessa -> RECLAIM_CLASS_NOT_ALLOWED · corsa persa dal reclaim -> RECLAIM_CLASS_NOT_ALLOWED (riga intatta) · fence dopo scrittura neutra -> FENCING_TOKEN_STALE · corsa vinta dal reclaim -> mark_submitting successivo StaleWrite · reclaim legittimo -> FAILED settled 0 · zero nuovi attempt · crash durante il reclaim (exit 11): terminale non regolato VISIBILE e riparato idempotentemente · RECLAIM_POLICY = NOT_AUTHORIZED (requisito NON chiuso) | **PASS** | `evidence/C05_orphan_lease_mechanism_policy.json` |
| C06 | NG-05: decisione e delta additivo del Core su branch dedicato | Core main senza API nuova; Runtime conservativo; branch dedicato 9/9 suite PASS | Core main: nessuna API nuova (pin 740ee979300f) · Runtime: percorso conservativo invariato (reconcile->settle, mai mark_refused_before_send) · branch harden/provider-boundary-core-atomicity-2026-09-17 @ 9cf9cee1a751 su base 740ee979300f: 9/9 suite PASS ·  3 files changed, 436 insertions(+), 3 deletions(-) · check falliti: nessuno | **PASS** | `evidence/C06_ng05_decision_and_core_delta.json` |
| C07 | Regressione R0-R1 (T01-T37) sul Runtime modificato | 0 FAIL | tests/run_gate.py T01-T37: exit 0 · PASS 36/37 · FAIL nessuno · BLOCKED ['T29/BLOCKED_ENVIRONMENT'] (fuori policy: nessuno) · decisione LAB_GATE_COMPLETE_WITH_ALLOWED_BLOCKED | **PASS** | `evidence/C07_regression_r0_r1.json` |
| C08 | P2 freeze e Core pin invariati a fine fase | P2 before == after == canonico; Core main pulito a 740ee979 | P2 637f3a803ee38d04 (before == after == canonico: True) · Core main 740ee979300f clean=True · pin 740ee979300f | **PASS** | `evidence/C08_p2_freeze_core_pin_after.json` |
| C09 | Reporting: test suite result e phase readiness separati | 6 controprove sollevano; all_requirements_verified=false con gap aperti | 11 controprove del reporting tutte sollevate: True · report reale: all_requirements_verified=False, decisione LAB_GATE_COMPLETE_WITH_OPEN_GAPS, stato massimo PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW · POLICY_DECISION_REQUIRED ['RECONCILIATION_FRESHNESS_NG04_POLICY', 'ORPHAN_RESERVED_LEASE_POLICY'] · REAL_PROVIDER_REQUIRED ['REAL_AUTHORIZATION_AND_PRICING', 'REAL_PROVIDER_RECONCILIATION'] · CORE_CHANGE_REQUIRED ['LEGACY_SPEND_PATHS_CORE_PRIMITIVES', 'NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY'] | **PASS** | `evidence/C09_reporting_phase_readiness.json` |
| C10 | Catena di provenance del bundle: verificatore fail-closed | 12 controprove: copertura, extra, mismatch, MANIFEST non coperto, chiave ambigua, code_sha == evidence_head, HEAD divergente, merge_readiness | 12 controprove della catena di provenance · scarti: nessuno · bundle valido -> 0 problemi · MANIFEST non coperto -> ['MANIFEST_NOT_COVERED', 'MISSING_FROM_SUMS'] · code_sha == evidence_head -> ['CODE_SHA_EQUALS_EVIDENCE_HEAD'] · HEAD != evidence_head -> ['HEAD_NOT_EVIDENCE_HEAD'] · merge_authorized senza coppia -> ['MERGE_AUTHORIZED_WITHOUT_PAIR'] | **PASS** | `evidence/C10_evidence_chain_verifier.json` |
| C11 | Regressione del delta correttivo (reporting/evidence-only) | diff funzionale Runtime invariato, Core candidate identico, main e P2 invariati, 0 tag, 0 credenziali | runtime_code_sha e845b744a4af · diff funzionale Runtime dopo quel commit: 0 byte (invariato=True) · Core candidate 9cf9cee1a751 == atteso · Core main 740ee979300f pulito · Runtime origin/main 0698279703ab · P2 637f3a803ee38d04 · 0 tag · provider reale disabilitato · 0 credenziali nel bundle · check falliti: nessuno | **PASS** | `evidence/C11_corrective_delta_regression.json` |

## A. TEST SUITE RESULT

| inventario | PASS | FAIL | BLOCKED | all_tests_passed | test_suite_decision |
|---|---|---|---|---|---|
| 12/12 (valido: True) | 12 | 0 | 0 | **true** | `ALL_TESTS_PASS` |

_i test del gate hanno prodotto l'esito atteso. NON significa che i requisiti di fase siano chiusi: un test PASS puo' verificare che un requisito resta APERTO._

## B. PHASE / REQUIREMENT READINESS

**`all_requirements_verified = false`** · **`phase_gate_decision = LAB_GATE_COMPLETE_WITH_OPEN_GAPS`** · stato massimo: `PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW`

_i requisiti della fase sono chiusi? `all_requirements_verified` e' vero SOLO se nessun requisito di questa fase o del Provider Boundary Gate e' aperto e tutti i test sono PASS._

| REQUISITO | SCOPE | STATO | EVIDENZA | NOTA |
|---|---|---|---|---|
| REALITY_LOCK_CANONICAL | this_phase | **`VERIFIED_LAB`** | C00 | Core 740ee979 · Runtime origin/main 0698279 · REQUIRED_CORE_SHA == Core · P2 637f3a80. |
| GAP_MATRIX_PHASE_A | this_phase | **`VERIFIED_LAB`** | C01 | 5/5 REPRODUCED con processi reali. Una premessa del mandato (il Core offrirebbe gia' una primitive atomica) e' risultata FALSA ed e' documentata come tale. |
| P_B02_P_B01_COMPOSITION | this_phase | **`VERIFIED_LAB`** | C02 | Segreto di riconciliazione e chiave derivata vivono solo nel daemon spender (UID distinto, DAC del kernel, SO_PEERCRED); l'orchestrator non li legge, non forgia un report e non si sostituisce allo spender. NON copre il provider reale. |
| RECONCILIATION_FRESHNESS_NG04_MECHANISM | this_phase | **`VERIFIED_LAB`** | C03 | `FreshnessPolicy` obbligatoria: assenza = rifiuto. Copre eta' massima, timestamp nel futuro (clock skew), issued_at assente/malformato, replay nonce e i confini della finestra. |
| RECONCILIATION_FRESHNESS_NG04_POLICY | future_gate | **`POLICY_DECISION_REQUIRED`** | C03 | Nessun valore scelto né suggerito dal codice: nessun 30s/60s/5min. Serve una decisione umana, vedi NG04_FRESHNESS.md. |
| LEGACY_SPEND_PATHS_RUNTIME_CLOSURE | this_phase | **`VERIFIED_LAB`** | C04 | #2/#4 (go authorization=None e Batch.run_job) e #7 (helper same-UID sullo store) rifiutati PRIMA di ogni effetto quando la modalita' e' ingaggiata. Inventario riverificato su Runtime 0698279. |
| LEGACY_SPEND_PATHS_CORE_PRIMITIVES | future_gate | **`CORE_CHANGE_REQUIRED`** | C04 | `transport.pipeline.run_job`, `adapter.submit` e `store.reconcile` raw sono invocabili da qualunque codice con il Core in sys.path. Nessun interruttore del Runtime li governa: la sola mitigazione e' il confine di processo P-B01. Chiusura = modifica del Core, non autorizzata da questo mandato. Vedi LEGACY_SPEND_PATHS_V2.md. |
| LEGACY_TESTS_MIGRATION_TO_GOVERNED | future_gate | **`STILL_OPEN`** | C04 | Con la modalita' ingaggiata la suite storica non puo' girare: dipende da LEGACY_LAB. Chiudere il percorso in modo definitivo richiede prima la migrazione dei test. |
| ORPHAN_RESERVED_LEASE_MECHANISM | this_phase | **`VERIFIED_LAB`** | C05 | Ownership, lease timestamp, lease identity, authority, fencing token + CAS, recovery, zero blind retry, concorrenza e crash durante il reclaim. Il meccanismo NON sceglie la policy. |
| ORPHAN_RESERVED_LEASE_POLICY | this_phase | **`POLICY_DECISION_REQUIRED`** | C05 | `RECLAIM_POLICY = NOT_AUTHORIZED`. Il requisito NON e' chiuso dal fatto che il meccanismo esista. Vedi ORPHAN_LEASE_MECHANISM_POLICY.md. |
| NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY | this_phase | **`CORE_CHANGE_REQUIRED`** | C06 | Il Core canonico NON offre una primitive a transazione singola con provenance parametrica (verificato leggendo il contratto reale). Delta additivo `mark_refused_pre_submit` prodotto e verificato 8/8 su branch Core dedicato. Human Review 01: APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED. Il Runtime candidate resta pinnato alla baseline e usa ancora reconcile -> settle: non esiste ancora una coppia Core+Runtime coerente, quindi portare Core main al candidate renderebbe la baseline incoerente per costruzione. Chiusura = delta coordinato separato, vedi `merge_readiness.next_integration_required`. |
| REAL_AUTHORIZATION_AND_PRICING | future_gate | **`REAL_PROVIDER_REQUIRED`** | C09 | Fuori scope per mandato: nessun provider reale, nessuna credenziale, 0 crediti. Prerequisiti documentati in REAL_PROVIDER_PREREQUISITES.md. |
| REAL_PROVIDER_RECONCILIATION | future_gate | **`REAL_PROVIDER_REQUIRED`** | C09 | Fuori scope per mandato. Il perimetro LAB dimostra binding, autenticazione, freshness e composizione con il confine di privilegio: nessuno di questi e' un claim sul provider reale. |
| R0_R1_NO_REGRESSION | this_phase | **`VERIFIED_LAB`** | C07 | Suite storica eseguita con la modalita' Provider Boundary DISINGAGGIATA, come a baseline. |
| P2_FREEZE_AND_CORE_PIN | this_phase | **`VERIFIED_LAB`** | C08 | Core main 740ee979 e working tree puliti a fine fase; il branch Core vive in un worktree separato e non tocca il tree canonico. |
| PHASE_READINESS_REPORTING | this_phase | **`VERIFIED_LAB`** | C09 | L'invariante della fase precedente e' preservata ed estesa ai nuovi stati (POLICY_DECISION_REQUIRED, REAL_PROVIDER_REQUIRED, CORE_CHANGE_REQUIRED). |
| RUN_CONTAMINATION | other_phase | **`NOT_RUN`** | — | Input Tenant assente: non eseguito (fuori scope). |
| G_N02_SEMANTIC_CLAIM_PARAPHRASE | other_phase | **`STILL_OPEN`** | — | Fuori scope, non toccato. |
| RV07_SCHEDULER_RECOVERY_RESIDUAL | other_phase | **`STILL_OPEN`** | — | Non toccato. P-B02 offre l'uscita autenticata da SUBMIT_UNKNOWN, ora dimostrata dentro lo spender, ma nessuno scheduler la invoca. |
| INDEPENDENT_CI_STATUS_CHECKS | other_phase | **`NOT_RUN`** | — | Assenti sul branch, come nelle fasi precedenti. |

Requisiti aperti che impediscono `all_requirements_verified`: ['RECONCILIATION_FRESHNESS_NG04_POLICY', 'LEGACY_SPEND_PATHS_CORE_PRIMITIVES', 'LEGACY_TESTS_MIGRATION_TO_GOVERNED', 'ORPHAN_RESERVED_LEASE_POLICY', 'NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY', 'REAL_AUTHORIZATION_AND_PRICING', 'REAL_PROVIDER_RECONCILIATION'] (di questa fase: ['ORPHAN_RESERVED_LEASE_POLICY', 'NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY']; rinviati al Provider Boundary Gate: ['RECONCILIATION_FRESHNESS_NG04_POLICY', 'LEGACY_SPEND_PATHS_CORE_PRIMITIVES', 'LEGACY_TESTS_MIGRATION_TO_GOVERNED', 'REAL_AUTHORIZATION_AND_PRICING', 'REAL_PROVIDER_RECONCILIATION']). Di altre fasi, elencati ma non imputati: ['RUN_CONTAMINATION', 'G_N02_SEMANTIC_CLAIM_PARAPHRASE', 'RV07_SCHEDULER_RECOVERY_RESIDUAL', 'INDEPENDENT_CI_STATUS_CHECKS'].

- `POLICY_DECISION_REQUIRED`: ['RECONCILIATION_FRESHNESS_NG04_POLICY', 'ORPHAN_RESERVED_LEASE_POLICY']
- `REAL_PROVIDER_REQUIRED`: ['REAL_AUTHORIZATION_AND_PRICING', 'REAL_PROVIDER_RECONCILIATION']
- `CORE_CHANGE_REQUIRED`: ['LEGACY_SPEND_PATHS_CORE_PRIMITIVES', 'NG05_PRE_SUBMIT_TERMINALIZATION_ATOMICITY']

## C. MERGE READINESS

| campo | valore |
|---|---|
| `runtime_candidate_ready` | **`true`** |
| `core_candidate_ready` | **`true`** |
| `core_runtime_pair_ready` | **`false`** |
| `merge_authorized` | **`false`** |
| `core_review_state` | `APPROVED_PROPOSAL — NOT_MERGE_AUTHORIZED` |
| `runtime_consumes_core_candidate` | `false` |
| `pin_points_to_core_candidate` | `false` |
| `required_core_sha` | `740ee979300fe20a9382992528604dee70cb2fcf` |
| `core_candidate_sha` | `9cf9cee1a751f7a2ad6c768574ff5aa38d8db515` |
| `human_merge_authorization` | `false` |

Blockers: `RUNTIME_DOES_NOT_CONSUME_CORE_CANDIDATE`, `REQUIRED_CORE_SHA_PINNED_TO_BASELINE_NOT_CANDIDATE`, `OPEN_REQUIREMENTS`, `HUMAN_MERGE_AUTHORIZATION_ABSENT`.

_la coppia Core+Runtime e' promuovibile? Il Runtime candidate resta pinnato alla baseline e usa ancora reconcile -> settle; il Core candidate introduce mark_refused_pre_submit ma non e' consumato. Non esiste ancora una coppia coerente: portare Core main al candidate renderebbe la baseline incoerente per costruzione._

Integrazione coordinata necessaria prima di qualunque merge (NON iniziata in questo delta):

1. partire dal Core candidate approvato
2. aggiornare il Runtime perche' consumi mark_refused_pre_submit
3. aggiornare REQUIRED_CORE_SHA al nuovo Core candidate SHA
4. rimuovere il percorso reconcile -> settle per il caso NG-05
5. dimostrare atomicita' end-to-end Runtime -> Core
6. rieseguire NG-03, NG-05, P-B04, P-B01/P-B02, R0-R1, P2 freeze
7. produrre una coppia candidate Core+Runtime indivisibile per Human Review

`PROVIDER_BOUNDARY_GATE_PRE_REAL_READY_FOR_HUMAN_REVIEW` e' uno stato di LAVORO con open gaps. **Non e' un'autorizzazione al merge.**

Nulla di quanto sopra significa provider reale verificato, provider ready, production ready, credenziali autorizzate, spend autorizzato, merge autorizzato, R2 autorizzato.

