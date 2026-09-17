# TEST RESULTS — LEGACY SPEND PATH CLOSURE + LEGACY TEST MIGRATION

MOCK ONLY · ZERO PROVIDER REALI · ZERO CREDENZIALI · ZERO CREDITI · NO PRODUZIONE.

| # | verifica | EXPECTED | ACTUAL | EVIDENCE | ESITO |
|---|---|---|---|---|---|
| E00 | Reality Lock | coppia canonica verificata, branch dedicati, P2 invariato | Core 44f9ea29cea1 (harden/legacy-spend-core-2026-09-18) · Runtime ad2f9c072b2a (claude/legacy-spend-path-closure-c50coy) · pin=44f9ea29cea1 · P2=637f3a803ee38d04… · controlli falliti: nessuno | `evidence/E00_reality_lock.json` | PASS |
| E01 | inventario statico dei percorsi di spesa | ogni entry point che tocca la catena di spesa, in Core e Runtime | CORE: 9 file con superficie di spesa, 273 chiamate · RUNTIME: 8 file, 23 chiamate · confine presente nel Core: grant_dispatch/authorize_dispatch | `evidence/E01_spend_path_inventory_static.json` | PASS |
| E02 | riproduzione PRE-FIX sulla coppia canonica | lo spender E' raggiungibile dai percorsi legacy su 9cf9cee1 + fea7b439 | sulla coppia canonica: lo spender e' raggiunto da LEGACY_LAB go, run_job diretto, submit diretto, authorize_payload diretto, reconcile+respend e hf_batch · non riprodotto: nessuno | `evidence/E02_pre_fix_reproduction.json` | PASS |
| E03 | classificazione delle primitive del Core + suite unitaria del confine | delta additivo, 11/11 PASS | Core delta additivo (5 file) · suite unitaria del confine: 11/11 PASS, exit 0 | `evidence/E03_core_primitives_classification.json` | PASS |
| E04 | controprove del confine provider (sentinella) | 0 attraversamenti in ogni percorso legacy, 1 nel governato | sentinella a 0 in tutti i percorsi legacy, 1 nel governato · controlli falliti: nessuno | `evidence/E04_provider_boundary_counterproofs.json` | PASS |
| E05 | LEGACY_LAB = LAB_ONLY_NON_PROVIDER_CAPABLE | adapter/modalita'/config non riaprono un percorso di spesa | modalita' ingaggiata/disingaggiata, ambiente, sottoclasse e wrapper che nasconde la capability: tutti rifiutati, sentinella 0 · falliti: nessuno | `evidence/E05_legacy_lab_only_non_provider_capable.json` | PASS |
| E06 | percorsi legacy di envelope/budget | il client non sceglie il prezzo; envelope_units non raggiunge lo spender | client budget grezzo non raggiunge il confine dello spender; importo solo dalla quote fidata · falliti: nessuno | `evidence/E06_legacy_envelope_budget_paths.json` | PASS |
| E07 | migrazione dei test storici | 20/20 equivalenti governati o Core-unit, assert non indeboliti | 20/20 equivalenti migrati PASS (19 GOVERNED_PATH + 1 CORE_UNIT) · falliti: nessuno | `evidence/E07_legacy_test_migration.json` | PASS |
| E08 | regressione R0-R1 T01-T37 | nessuna regressione introdotta da questa fase | T01-T37 sulla coppia candidate: PASS 36/37 · FAIL nessuno (pre-fix nello stesso ambiente: ['T08']) · BLOCKED ['T29'] · regressioni introdotte da questa fase: nessuna | `evidence/E08_regression_r0_r1.json` | PASS |
| E09 | meccanismi approvati + suite del Core sulla coppia candidate | P-B01/P-B02, NG-04, legacy spend paths, orphan lease, suite Core: verdi | meccanismi sul candidate: 4/4 · suite del Core: 9/9 · falliti: nessuno | `evidence/E09_mechanism_and_core_regressions.json` | PASS |
| E10 | Core pin e P2 freeze | pin sul candidate, baseline precedente STALE, P2 before == after | pin 44f9ea29cea1 == Core HEAD · 9cf9cee1a751 ora STALE · P2 before==after==637f3a803ee38d04… · falliti: nessuno | `evidence/E10_core_pin_and_p2_freeze.json` | PASS |
| E11 | integrita' della catena di evidenza | code SHA / evidence-head / base canonica / branch distinti, 0 .pyc | nessun .pyc/__pycache__ · code SHA Core 44f9ea29cea1 / Runtime ad2f9c072b2a distinti da evidence-head · bundle approvati intatti · falliti: nessuno | `evidence/E11_evidence_chain_integrity.json` | PASS |
| E12 | reporting: esito della suite vs readiness del requisito | due oggetti separati; nessun requisito chiuso per errore | stato massimo: LEGACY_SPEND_PATHS_CLOSED — READY_FOR_HUMAN_REVIEW · suite: 12/12 · requisiti aperti: 9 · falliti: nessuno | `evidence/E12_reporting_test_result_vs_readiness.json` | PASS |

**13/13 PASS** · falliti: nessuno

Un PASS qui e' un ESITO DI SUITE, non una readiness: vedi `READINESS.json` e `OPEN_REQUIREMENTS.md`.
